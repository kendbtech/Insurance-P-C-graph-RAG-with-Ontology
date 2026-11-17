#!/usr/bin/env python3
"""
03_ground_ontology.py   LAYER 3 - Dynamic Ontology Grounding

tagged clauses  ->  grounded clauses  ->  output/03_grounded/<doc>.json  +  output/03_grounded/_term_index.json

Two kinds of grounding, both recorded separately so downstream code knows how much to trust them:
  HARD  (deterministic)  identifiers found by regex (COV-A, MM-CP-E101, EXCL-FLD, FL, FL-T03, class code 0511...)
                         are resolved straight to instance IRIs  ->  pc:mentions
  SOFT  (embedding)      the clause text is embedded and compared with every ontology term
                         (class / individual: rdfs:label + skos:altLabel + rdfs:comment).
                         Only the TOP-3 terms are kept  ->  pc:groundedTerm
Why top-3?  The prompt that Layer 4 builds stays the same size no matter how big the ontology grows.

Embedding backend:  sentence-transformers  all-MiniLM-L6-v2  if it can be loaded (local or cached),
                    else scikit-learn TF-IDF (character n-grams) so the POC still runs fully offline.
"""
import re
import numpy as np
from rdflib import Graph, RDFS, SKOS, RDF, OWL, Namespace, URIRef
from common import OUTPUT, DOCS, ONTOLOGY_TTL, PC, PCD, ID_PATTERNS, read_json, write_json

IN_DIR = OUTPUT / "02_classified"
OUT_DIR = OUTPUT / "03_grounded"
TOP_K = 3
PCN = Namespace(PC)
PCDN = Namespace(PCD)


# ------------------------------------------------------------------ 1. index the ontology
def build_term_index():
    g = Graph().parse(ONTOLOGY_TTL, format="turtle")
    terms = []
    for s in set(g.subjects(RDF.type, OWL.Class)) | {s for s, _, o in g.triples((None, RDF.type, None))
                                                     if str(s).startswith(PCD)}:
        label = g.value(s, RDFS.label)
        if label is None:
            continue
        alts = [str(a) for a in g.objects(s, SKOS.altLabel)]
        comment = g.value(s, RDFS.comment)
        kind = "class" if (s, RDF.type, OWL.Class) in g else "individual"
        text = "; ".join([str(label)] + alts + ([str(comment)] if comment else []))
        terms.append({"iri": str(s), "label": str(label), "kind": kind, "altLabels": alts, "text": text})
    return terms


class Embedder:
    def __init__(self):
        self.backend = None
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            self.backend = "all-MiniLM-L6-v2"
        except Exception as e:                       # offline fallback
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)
            self.backend = f"tfidf-char (fallback: {type(e).__name__})"

    def fit(self, corpus):
        if self.backend.startswith("tfidf"):
            self.vec.fit(corpus)

    def encode(self, texts):
        if self.backend.startswith("tfidf"):
            m = self.vec.transform(texts).toarray()
        else:
            m = self.model.encode(texts, normalize_embeddings=True)
        m = np.asarray(m, dtype=float)
        n = np.linalg.norm(m, axis=1, keepdims=True); n[n == 0] = 1
        return m / n


# ------------------------------------------------------------------ 2. hard grounding (identifiers -> IRIs)
def hard_ground(ids):
    out = []
    for kind, values in ids.items():
        for v in values:
            if kind == "form":        out.append({"iri": PCD + v, "type": "Form", "code": v})
            elif kind == "coverage":  out.append({"iri": PCD + v, "type": "Coverage", "code": v})
            elif kind == "exclusion": out.append({"iri": PCD + v, "type": "Exclusion", "code": v})
            elif kind == "state":     out.append({"iri": PCD + v, "type": "State", "code": v})
            elif kind == "filing":    out.append({"iri": PCD + v, "type": "StateFiling", "code": v})
            elif kind == "territory": out.append({"iri": PCD + v, "type": "Territory", "code": v})
            elif kind == "classcode": out.append({"iri": PCD + "CC-" + v, "type": "ClassCode", "code": v})
            elif kind == "construction": out.append({"iri": PCD + v, "type": "ConstructionClass", "code": v})
            elif kind == "protection": out.append({"iri": PCD + v, "type": "ProtectionClass", "code": v})
            elif kind == "factor":    out.append({"iri": PCD + v, "type": "RatingFactor", "code": v})
            elif kind == "document":  out.append({"iri": PCD + v, "type": "Document", "code": v})
    return out


PERIL_CUES = {  # cheap lexical peril linking in addition to embeddings (keeps the demo deterministic)
    "Flood": r"\bflood", "Windstorm": r"\bwind(storm)?\b|\bhurricane\b", "Hail": r"\bhail\b", "Fire": r"\bfire\b",
    "EarthMovement": r"\bearth movement\b|\bearthquake\b", "MechanicalBreakdown": r"\bmechanical breakdown\b|\bequipment breakdown\b",
    "Theft": r"\btheft\b", "Vandalism": r"\bvandalism\b", "Mold": r"\bmold\b|\bfungus\b", "Water": r"\bwater\b",
    "SprinklerLeakage": r"\bsprinkler leakage\b",
}


def peril_ground(text):
    return [{"iri": PCD + k, "type": "Peril", "code": k} for k, rx in PERIL_CUES.items() if re.search(rx, text, re.I)]


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    terms = build_term_index()
    emb = Embedder()
    print("embedding backend:", emb.backend, "| ontology terms:", len(terms))

    # gather all clause texts first (TF-IDF fallback needs a corpus to fit)
    docs = {d: read_json(IN_DIR / f"{d}.json") for d in DOCS}
    all_clauses = [c for t in docs.values() for s in t["sections"] for c in s["clauses"]]
    emb.fit([t["text"] for t in terms] + [c["text"] for c in all_clauses])
    T = emb.encode([t["text"] for t in terms])
    C = emb.encode([c["text"] for c in all_clauses])
    sims = C @ T.T

    for i, c in enumerate(all_clauses):
        top = np.argsort(-sims[i])[:TOP_K]
        c["grounding"] = {
            "hard": hard_ground(c.get("ids", {})) + peril_ground(c["text"]),
            "soft_top3": [{"iri": terms[j]["iri"], "label": terms[j]["label"], "kind": terms[j]["kind"],
                           "score": round(float(sims[i, j]), 3)} for j in top],
            "backend": emb.backend,
        }
    for d, t in docs.items():
        write_json(OUT_DIR / f"{d}.json", t)
    write_json(OUT_DIR / "_term_index.json", {"backend": emb.backend, "terms": terms})

    # tiny report
    for c in all_clauses[:6]:
        print(c["clause_id"], "|", [h["code"] for h in c["grounding"]["hard"]], "|",
              [(s["label"], s["score"]) for s in c["grounding"]["soft_top3"]])
