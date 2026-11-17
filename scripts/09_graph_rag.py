#!/usr/bin/env python3
"""
09_graph_rag.py   GRAPH RAG  -  structured (SPARQL) + unstructured (vector search over clause chunks) + LLM answer

Flow for one question
  1. Entity linking   : identifiers by regex (MM-CP-E101, COV-A, FL ...) + ontology labels/altLabels ("Coverage A",
                        "flood", "Florida") + MiniLM nearest ontology terms (same Embedder as Layer 3)
  2. Intent           : pick a SPARQL template (T1 endorsement availability, T2 peril coverage path, T3 duties & deadlines,
                        T0 generic neighbourhood) and fill it with the linked IRIs
  3. Structured facts : run the template(s) in GraphDB -> human-readable facts, each with a provenance tag
  4. Vector retrieval : cosine similarity between the question and every pc:Chunk's chunkText (embedded once at start),
                        boosted when the chunk pc:mentions a linked entity  -> top-k chunks with [doc | section | page]
  5. Answer           : LLM (if OPENAI_API_KEY is set) or a deterministic extractive composer (offline mode) that
                        writes the answer from the facts + chunks. Every statement cites [document | section | p.N].

Outputs: output/09_graph_rag/answers.md , answers.json (includes the retrieval trace for each question)
Usage  : python scripts/09_graph_rag.py                     (runs the 3 demo questions)
         python scripts/09_graph_rag.py "your question"      (ad hoc)
Vector search here is in-process (numpy). In GraphDB the equivalent is the Similarity plugin or the Elasticsearch /
OpenSearch connector vector search; both are optional components, so the POC keeps the index in Python.
"""
import json
import os
import re
import sys
import numpy as np
import requests
from rdflib import Graph
from common import OUTPUT, PC, PCD, ID_PATTERNS, read_json, write_json
from graphdb_client import GraphDB

sys.path.insert(0, os.path.dirname(__file__))
Embedder = __import__("03_ground_ontology").Embedder

OUT_DIR = OUTPUT / "09_graph_rag"
TERM_INDEX = OUTPUT / "03_grounded" / "_term_index.json"
EXTRA_ALIASES = {"florida": "FL", "texas": "TX", "new york": "NY", "coverage a": "COV-A", "coverage b": "COV-B",
                 "coverage c": "COV-C", "coverage d": "COV-D", "building": "COV-A", "flood": "Flood", "wind": "Windstorm",
                 "hail": "Hail", "fire": "Fire", "earthquake": "EarthMovement", "equipment breakdown": "MechanicalBreakdown"}

DEMO_QUESTIONS = [
    "Which endorsements modify Coverage A (Building) and are approved for use in Texas?",
    "A Florida policy has a scheduled location in flood zone AE. Is flood damage to the building covered, and what is required?",
    "What must the insured do after a loss, and how quickly must a Florida claim be acknowledged?",
]


def cite(doc, section, page):
    return f"[{doc} | {section} | p.{page}]"


class GraphRAG:
    def __init__(self):
        self.db = GraphDB()
        self.online = self.db.alive()
        self.terms = read_json(TERM_INDEX)["terms"]
        self.emb = Embedder()
        self.chunks = self._load_chunks()
        texts = [c["text"] for c in self.chunks]
        self.emb.fit(texts + [t["text"] for t in self.terms])
        self.chunk_vecs = self.emb.encode(texts)
        self.term_vecs = self.emb.encode([t["text"] for t in self.terms])

    # ---------------------------------------------------------------- chunks
    def _load_chunks(self):
        q = """SELECT ?c ?doc ?section ?page ?text (GROUP_CONCAT(DISTINCT STR(?m); separator=" ") AS ?mentions) WHERE {
                 ?c a pc:Chunk ; pc:chunkText ?text ; pc:sourceDocument/pc:documentId ?doc ; pc:sectionRef ?section ; pc:pageNumber ?page .
                 OPTIONAL { ?c pc:mentions ?m } } GROUP BY ?c ?doc ?section ?page ?text"""
        if self.online:
            _, rows = self.db.select(q)
        else:                                      # offline fallback: read the Turtle written by step 06
            g = Graph().parse(OUTPUT / "06_rdf" / "clauses.ttl", format="turtle")
            g.parse(OUTPUT / "06_rdf" / "data.ttl", format="turtle")
            from common import QUERIES
            res = g.query((QUERIES / "_prefixes.rq").read_text() + q)
            rows = [{k: (str(r[k]) if r[k] is not None else None) for k in res.vars.__iter__() and ["c", "doc", "section", "page", "text", "mentions"]} for r in res]
        return [{"iri": r["c"], "doc": r["doc"], "section": r["section"], "page": int(r["page"]), "text": r["text"],
                 "mentions": set((r["mentions"] or "").split())} for r in rows]

    # ---------------------------------------------------------------- 1. entity linking
    def link_entities(self, question):
        found = {}
        for kind, rx in ID_PATTERNS.items():
            for m in rx.findall(question):
                code = m if isinstance(m, str) else m[0]
                if kind == "classcode": code = "CC-" + code
                found[code] = {"iri": PCD + code, "how": f"regex:{kind}"}
        ql = question.lower()
        for alias, code in EXTRA_ALIASES.items():
            if re.search(r"\b" + re.escape(alias) + r"\b", ql):
                found.setdefault(code, {"iri": PCD + code, "how": f"alias:{alias}"})
        for t in self.terms:                       # ontology labels / altLabels
            for lab in [t["label"]] + t.get("altLabels", []):
                if len(lab) > 3 and re.search(r"\b" + re.escape(lab.lower()) + r"\b", ql):
                    found.setdefault(t["iri"].replace(PCD, "").replace(PC, ""), {"iri": t["iri"], "how": f"label:{lab}"})
        qv = self.emb.encode([question])[0]
        sims = self.term_vecs @ qv
        soft = [{"iri": self.terms[i]["iri"], "label": self.terms[i]["label"], "score": round(float(sims[i]), 3)}
                for i in np.argsort(-sims)[:3]]
        return found, soft

    # ---------------------------------------------------------------- 2. intent
    @staticmethod
    def intent(question, ents):
        ql = question.lower()
        perils = [e for e in ents if e in ("Flood", "Windstorm", "Hail", "Fire", "EarthMovement", "MechanicalBreakdown", "Water")]
        if "endorsement" in ql and any(e.startswith("COV-") for e in ents):
            return "T1"
        if perils and re.search(r"cover|excluded|pay", ql):
            return "T2"
        if re.search(r"\bmust\b|duties|how quickly|deadline|within|acknowledg|report", ql):
            return "T3"
        return "T0"

    # ---------------------------------------------------------------- 3. structured facts
    def rule_facts(self, dsl_filter):
        q = f"""SELECT ?rule ?status ?dsl ?message ?doc ?section ?page ?overriddenBy WHERE {{
              ?r a pc:Rule ; rdfs:label ?rule ; pc:ruleStatus ?status ; pc:ruleDSL ?dsl ; rdfs:comment ?message ; pc:compiledFrom ?c .
              ?c pc:sourceDocument/pc:documentId ?doc ; pc:sectionRef ?section ; pc:pageNumber ?page .
              OPTIONAL {{ ?r pc:overriddenBy/rdfs:label ?overriddenBy }}
              FILTER({dsl_filter}) }} ORDER BY ?rule"""
        _, rows = self.db.select(q)
        facts = []
        for r in rows:
            s = f"Rule {r['rule']} ({r['status']}): {r['dsl']}"
            if r["overriddenBy"]: s += f" - narrowed/scoped by {r['overriddenBy']} (Layer 5 precedence)"
            facts.append({"fact": s, "source": cite(r["doc"], r["section"], r["page"]), "kind": "rule"})
        return facts, q

    def facts_T1(self, ents):
        cov = next(e for e in ents if e.startswith("COV-"))
        state = next((e for e in ents if e in ("FL", "TX", "NY")), "TX")
        q = f"""SELECT ?endorsement ?title ?edition ?status ?filing WHERE {{
              ?e a pc:Endorsement ; pc:formNumber ?endorsement ; rdfs:label ?title ; pc:modifiesCoverage pcd:{cov} .
              OPTIONAL {{ ?e pc:editionDate ?edition }}
              OPTIONAL {{ ?f pc:hasFormApproval ?ap ; pc:filingNumber ?filing .
                         ?ap pc:approvalOfForm ?e ; pc:approvalInState pcd:{state} ; pc:approvalStatus/rdfs:label ?status }}
            }} ORDER BY ?endorsement"""
        _, rows = self.db.select(q)
        facts = []
        for r in rows:
            st = r["status"] or "no filing in this state"
            facts.append({"fact": f"{r['endorsement']} ({r['title']}, Ed. {r['edition']}) modifies {cov}; {state} status: {st}"
                                  + (f" per filing {r['filing']}" if r["filing"] else ""),
                          "source": cite("MM-FILINGS-CP-2025" if r["filing"] else "MM-CP-E-SERIES",
                                         "filing table" if r["filing"] else "Endorsement Availability Matrix", 1), "kind": "graph"})
        return facts, [q]

    def facts_T2(self, ents):
        peril = next(e for e in ents if e in ("Flood", "Windstorm", "Hail", "Fire", "EarthMovement", "MechanicalBreakdown", "Water"))
        q = f"""SELECT ?exclusion ?exclLabel ?restoring ?restoringTitle ?sublimit ?dedPct ?dedMin
                       (GROUP_CONCAT(DISTINCT ?covCode; separator=", ") AS ?coverages) (GROUP_CONCAT(DISTINCT ?st; separator=", ") AS ?approvedIn) WHERE {{
              pcd:MM-CP-0010 pc:hasExclusion ?x . ?x pc:exclusionCode ?exclusion ; rdfs:label ?exclLabel ; pc:excludesPeril pcd:{peril} .
              OPTIONAL {{ ?e pc:removesExclusion ?x ; pc:formNumber ?restoring ; rdfs:label ?restoringTitle .
                         OPTIONAL {{ ?e pc:sublimitAmount ?sublimit }} OPTIONAL {{ ?e pc:deductiblePercent ?dedPct }} OPTIONAL {{ ?e pc:deductibleMinimum ?dedMin }}
                         OPTIONAL {{ ?e pc:modifiesCoverage/pc:coverageCode ?covCode }}
                         OPTIONAL {{ ?ap pc:approvalOfForm ?e ; pc:approvalStatus pcd:Approved ; pc:approvalInState/pc:stateCode ?st }} }}
            }} GROUP BY ?exclusion ?exclLabel ?restoring ?restoringTitle ?sublimit ?dedPct ?dedMin"""
        _, rows = self.db.select(q)
        facts = []
        for r in rows:
            facts.append({"fact": f"{peril} is removed from MM-CP-0010 by exclusion {r['exclusion']} ({r['exclLabel']}), which lives in MM-CP-1030 and is pulled in by Section B.1",
                          "source": cite("MM-CP-0010", "SECTION B - EXCLUSIONS / B.1", 2), "kind": "graph"})
            if r["restoring"]:
                facts.append({"fact": f"{r['restoring']} ({r['restoringTitle']}) deletes {r['exclusion']} and restores {peril} for {r['coverages']}; "
                                      f"sublimit {float(r['sublimit']):,.0f}, deductible {float(r['dedPct']):g}% (minimum {float(r['dedMin']):,.0f}); approved in {r['approvedIn']}",
                              "source": cite("MM-CP-E-SERIES", "1-MM-CP-E101 / 1.2-1.4", 1), "kind": "graph"})
        rf, rq = self.rule_facts(f'CONTAINS(?dsl, "{peril}") || CONTAINS(?dsl, "inFloodZone")' if peril == "Flood" else f'CONTAINS(?dsl, "{peril}")')
        return facts + rf, [q, rq]

    def facts_T3(self, ents):
        state = next((e for e in ents if e in ("FL", "TX", "NY")), None)
        q = """SELECT ?clause ?doc ?section ?page ?text ?exception WHERE {
              ?c a pc:Clause ; pc:deonticType pcd:Obligation ; rdfs:label ?clause ; pc:clauseText ?text ;
                 pc:sourceDocument/pc:documentId ?doc ; pc:sectionRef ?section ; pc:pageNumber ?page .
              FILTER(REGEX(?text, "within [0-9]+ (hours|days|business days|calendar days)", "i"))
              OPTIONAL { ?x pc:exceptionTo ?c ; pc:clauseText ?exception } } ORDER BY ?doc ?clause"""
        _, rows = self.db.select(q)
        facts = []
        for r in rows:
            if state and re.search(r"Texas|New York|\bTX\b|\bNY\b", r["text"]) and state not in r["text"] and \
                    {"FL": "Florida", "TX": "Texas", "NY": "New York"}[state] not in r["text"]:
                continue                                   # clause about another state only
            dl = re.search(r"within [0-9]+ (hours|days|business days|calendar days)", r["text"], re.I).group(0)
            facts.append({"fact": f"{r['clause']}: {r['text'][:220]}{'...' if len(r['text']) > 220 else ''} (deadline: {dl})"
                                  + (f" EXCEPTION: {r['exception']}" if r["exception"] else ""),
                          "source": cite(r["doc"], r["section"], r["page"]), "kind": "graph"})
        rf, rq = self.rule_facts('CONTAINS(?dsl, "WITHIN")')
        return facts + rf, [q, rq]

    def facts_T0(self, ents):
        if not ents:
            return [], []
        vals = " ".join(f"<{e['iri']}>" for e in ents.values())
        q = f"""SELECT ?s ?sl ?p ?o ?ol WHERE {{ VALUES ?s {{ {vals} }} ?s ?p ?o . FILTER(?p NOT IN (rdf:type, pc:chunkText, pc:clauseText))
                OPTIONAL {{ ?s rdfs:label ?sl }} OPTIONAL {{ ?o rdfs:label ?ol }} }} LIMIT 60"""
        _, rows = self.db.select("PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n" + q)
        facts = [{"fact": f"{r['sl'] or r['s'].replace(PCD, '')} --{r['p'].split('#')[-1]}--> {r['ol'] or str(r['o']).replace(PCD, '')}",
                  "source": "[knowledge graph | data graph | -]", "kind": "graph"} for r in rows]
        return facts, [q]

    # ---------------------------------------------------------------- 4. vector retrieval (hybrid boost)
    def retrieve(self, question, ents, k=6):
        qv = self.emb.encode([question])[0]
        sims = self.chunk_vecs @ qv
        ent_iris = {e["iri"] for e in ents.values()}
        scored = []
        for i, c in enumerate(self.chunks):
            boost = 0.12 * len(ent_iris & c["mentions"])
            scored.append((float(sims[i]) + boost, float(sims[i]), boost, c))
        scored.sort(key=lambda x: -x[0])
        return [{"score": round(s, 3), "cosine": round(cs, 3), "entity_boost": round(b, 2), "doc": c["doc"], "section": c["section"],
                 "page": c["page"], "text": c["text"]} for s, cs, b, c in scored[:k]]

    # ---------------------------------------------------------------- 5. answer
    @staticmethod
    def build_prompt(question, facts, chunks):
        f = "\n".join(f"- {x['fact']} {x['source']}" for x in facts) or "- (none)"
        c = "\n".join(f"- {cite(x['doc'], x['section'], x['page'])} {x['text']}" for x in chunks)
        return f"""You are a P&C insurance knowledge assistant. Answer ONLY from the facts and passages below.
Every sentence must end with one or more citations in the exact form [document | section | p.N] copied from the material.
If the material does not answer the question, say so.

QUESTION: {question}

STRUCTURED FACTS (from the knowledge graph):
{f}

PASSAGES (retrieved clause chunks):
{c}

ANSWER:"""

    @staticmethod
    def llm(prompt):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            return None
        r = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                          json={"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "temperature": 0,
                                "messages": [{"role": "user", "content": prompt}]}, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    @staticmethod
    def compose_offline(intent, question, facts, chunks):
        """Deterministic extractive answer so the demo runs without an LLM. Same citation discipline."""
        graph = [f for f in facts if f["kind"] == "graph"]
        rules = [f for f in facts if f["kind"] == "rule"]
        lines = []
        if intent == "T1":
            ok = [f for f in graph if "status: Approved" in f["fact"]]
            other = [f for f in graph if f not in ok]
            lines.append("Approved and available: " + "; ".join(f["fact"].split(" modifies")[0] for f in ok) + ". "
                         + " ".join(dict.fromkeys(f["source"] for f in ok)))
            for f in other:
                lines.append(f"Not available: {f['fact']}. {f['source']}")
        elif intent == "T2":
            for f in graph:
                lines.append(f"{f['fact']}. {f['source']}")
            for f in rules:
                lines.append(f"{f['fact']}. {f['source']}")
        else:
            for f in graph[:8]:
                lines.append(f"{f['fact']} {f['source']}")
            for f in rules:
                lines.append(f"{f['fact']}. {f['source']}")
        lines.append("Supporting passages:")
        for c in chunks[:4]:
            body = re.sub(r"^\[[^\]]*\]\s*", "", c["text"])          # drop the embedding prefix, keep the citation tag
            lines.append(f"- \"{body[:260]}{'...' if len(body) > 260 else ''}\" {cite(c['doc'], c['section'], c['page'])}")
        return "\n".join(lines)

    def answer(self, question):
        ents, soft = self.link_entities(question)
        intent = self.intent(question, ents)
        facts, queries = getattr(self, f"facts_{intent}")(ents)
        chunks = self.retrieve(question, ents)
        prompt = self.build_prompt(question, facts, chunks)
        text = self.llm(prompt)
        mode = "llm" if text else "offline-extractive"
        if not text:
            text = self.compose_offline(intent, question, facts, chunks)
        return {"question": question, "mode": mode, "intent": intent, "linked_entities": ents, "nearest_ontology_terms": soft,
                "sparql": queries, "facts": facts, "chunks": chunks, "answer": text}


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rag = GraphRAG()
    print(f"GraphDB online: {rag.online} | chunks indexed: {len(rag.chunks)} | embedder: {rag.emb.backend}")
    questions = sys.argv[1:] or DEMO_QUESTIONS
    results = [rag.answer(q) for q in questions]
    md = ["# Graph RAG answers\n"]
    for r in results:
        md += [f"## Q: {r['question']}", f"mode: {r['mode']} | intent template: {r['intent']} | linked entities: {', '.join(r['linked_entities']) or '-'}",
               "", r["answer"], "", "<details><summary>retrieval trace</summary>\n",
               "Top chunks: " + "; ".join(f"{c['doc']} {c['section'].split(' / ')[-1]} p.{c['page']} (score {c['score']})" for c in r["chunks"]),
               "\nNearest ontology terms: " + ", ".join(f"{t['label']} ({t['score']})" for t in r["nearest_ontology_terms"]), "</details>\n"]
        print("\n" + "=" * 100 + f"\nQ: {r['question']}\n[{r['mode']} | {r['intent']} | entities: {list(r['linked_entities'])}]\n\n{r['answer']}")
    (OUT_DIR / "answers.md").write_text("\n".join(md))
    write_json(OUT_DIR / "answers.json", results)
