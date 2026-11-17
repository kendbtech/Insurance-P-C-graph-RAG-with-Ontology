#!/usr/bin/env python3
"""
01_parse_clause_tree.py   LAYER 1 - Hierarchical Perception

PDF  ->  clause tree with exceptions kept next to their parent  ->  output/01_clause_tree/<doc>.json

Steps (mirrors the design):
  1. Layout-aware parsing : pdfplumber reads text per page, tables are detected and lifted out
                            of the text stream so they are kept intact (rows), not flattened.
  2. Build the clause tree: headings (SECTION A - ..., RULE 3 - ..., FILING 1 - ..., "1. MM-CP-E101 - ...")
                            become section nodes; numbered clauses (A.1, 2.3, E.3) become clause nodes;
                            sentences that start with an exception cue ("except", "unless", "does not apply",
                            "other than", "but not less than") become child nodes of the clause they belong to.
  3. Linguistic gatekeeper: a rule-based filter drops clauses that carry no rule signal and no identifier
                            (preamble, synthetic-document notice, pure descriptions). Zero model cost.

No LLM is used in this layer.
"""
import re
import sys
import pdfplumber
from common import SOURCES, OUTPUT, DOCS, ID_PATTERNS, write_json

OUT_DIR = OUTPUT / "01_clause_tree"

HEADING_RE = re.compile(
    r"^(SECTION\s+[A-Z0-9]+\s+-\s+.+|RULE\s+\d+\s+-\s+.+|FILING\s+\d+\s+-\s+.+|\d\.\s+MM-CP-[A-Z0-9-]+\s+-\s+.+|\d\.\s+[A-Z][A-Z\s]+)$")
EDITION_TAIL_RE = re.compile(r"^\(Ed\.\s+\d{2}/\d{4}\)$")
# clause ids:  A.1   E.3   1.2   8.1   (followed by a capital letter or quote)
# split only where a clause id starts the stream or follows a sentence end ("... form. E.3 Duties")
CLAUSE_SPLIT_RE = re.compile(r"(?:^|(?<=[.:]\s))(?=(?:[A-H]\.\d{1,2}|\d{1,2}\.\d{1,2})\s+(?=[A-Z'\"]))")
CLAUSE_ID_RE = re.compile(r"^((?:[A-H]\.\d{1,2}|\d{1,2}\.\d{1,2}))\s+")
SUBITEM_SPLIT_RE = re.compile(r"\s(?=\([a-e]\)\s)")
EXCEPTION_CUES = re.compile(
    r"\b(except|unless|does not apply|do not apply|other than|but not less than|but not|however|"
    r"is not extended|not covered unless|only if|only for|only to)\b", re.I)
RULE_SIGNALS = re.compile(
    r"\b(must|shall|there can be no|will pay|will not pay|may not|may be|may cancel|may|required|require|prohibited|mandatory|"
    r"not covered|does not include|is deleted|replaces|controls|eligible|refer|applies|apply|deductible|"
    r"within \d+ (?:hours|days|business days|calendar days)|is amended|supersedes|not be used|cannot|only)\b", re.I)

SENT_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(])")


def page_items(page):
    """Return page content as a list of items ordered top-to-bottom:
       ("line", text) for prose lines outside tables, ("table", {...}) for detected tables.
       Lifting tables out of the text stream keeps rows intact instead of flattening them into prose."""
    tables = page.find_tables()
    bboxes = [t.bbox for t in tables]

    def outside(obj):
        cx = (obj["x0"] + obj["x1"]) / 2
        cy = (obj["top"] + obj["bottom"]) / 2
        return not any(x0 <= cx <= x1 and top <= cy <= bottom for (x0, top, x1, bottom) in bboxes)

    items = [(l["top"], "line", l["text"].strip()) for l in page.filter(outside).extract_text_lines() if l["text"].strip()]
    for t in tables:
        rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in t.extract()]
        rows = [r for r in rows if any(r)]
        if rows:
            items.append((t.bbox[1], "table", {"header": rows[0], "rows": rows[1:]}))
    items.sort(key=lambda x: x[0])
    return [(kind, payload) for _, kind, payload in items]


def split_sentences(text):
    return [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]


def build_clause(doc_id, section, cid, body, page):
    """A clause node. Exception sentences become children; sub-items (a)...(e) are kept inside the text."""
    sentences = split_sentences(body)
    main, exceptions = [], []
    for s in sentences:
        low = s.lower()
        if low.startswith(("except", "unless", "however", "with respect to covered causes of loss other")):
            # whole sentence is an exception to the previous sentence(s)
            exceptions.append(s)
            continue
        main.append(s)                                   # the rule sentence stays with the parent...
        m = re.search(r",?\s+\b(except|unless|but not less than|but not|other than|does not apply|is not extended)\b", s, re.I)
        if m:                                             # ...and the exception fragment is ALSO kept as a child
            exceptions.append(s[m.start():].strip(" ,"))
    node = {
        "clause_id": f"{doc_id}#{section['id']}/{cid}",
        "doc_id": doc_id, "section": section["id"], "section_title": section["title"],
        "ref": cid, "page": page,
        "text": " ".join(main) if main else body,
        "full_text": body,
        "exceptions": [{"clause_id": f"{doc_id}#{section['id']}/{cid}/x{i+1}", "text": e, "exception_to": f"{doc_id}#{section['id']}/{cid}"}
                       for i, e in enumerate(exceptions)],
        "ids": {k: sorted(set(m if isinstance(m, str) else m for m in p.findall(body))) for k, p in ID_PATTERNS.items()},
    }
    node["ids"] = {k: v for k, v in node["ids"].items() if v}
    return node


def gatekeeper(node):
    """Rule-based filter: keep if it looks like a rule or carries an identifier."""
    txt = node["full_text"]
    if "SYNTHETIC DOCUMENT" in txt or node["section"] == "FRONT":
        return False, "front-matter"
    if RULE_SIGNALS.search(txt):
        return True, "rule-signal"
    if node["ids"]:
        return True, "identifier"
    return False, "no-rule-signal"


def parse_document(doc_id):
    fname, dtype, title = DOCS[doc_id]
    sections, dropped = [], []
    current = {"id": "FRONT", "title": "Front matter", "clauses": [], "tables": []}
    sections.append(current)
    with pdfplumber.open(SOURCES / fname) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            items = page_items(page)
            # Reportlab wraps lines; glue lines back into a stream, but keep headings on their own line.
            buffer = []

            def flush():
                nonlocal buffer
                if not buffer:
                    return
                blob = " ".join(buffer)
                buffer = []
                parts = [p.strip() for p in CLAUSE_SPLIT_RE.split(blob) if p.strip()]
                for part in parts:
                    m = CLAUSE_ID_RE.match(part)
                    cid = m.group(1) if m else f"p{len(current['clauses'])+1}"
                    node = build_clause(doc_id, current, cid, part, pno)
                    keep, why = gatekeeper(node)
                    if keep:
                        current["clauses"].append(node)
                    else:
                        dropped.append({"clause_id": node["clause_id"], "reason": why, "text": part[:120]})

            for kind, payload in items:
                if kind == "table":
                    flush()
                    payload["page"] = pno
                    payload["table_id"] = f"{doc_id}#{current['id']}/T{len(current['tables'])+1}"
                    current["tables"].append(payload)
                    continue
                line = payload
                if EDITION_TAIL_RE.match(line) and not buffer:   # wrapped heading tail "(Ed. 06/2025)"
                    current["title"] += " " + line
                    continue
                hm = HEADING_RE.match(line)
                if hm:
                    flush()
                    sid = re.sub(r"\s+-\s+.*$", "", line)          # "SECTION A", "RULE 3", "1. MM-CP-E101"
                    sid = re.sub(r"^(SECTION|RULE|FILING)\s+", r"\1-", sid).replace(". ", "-")
                    current = {"id": sid.replace(" ", ""), "title": line, "clauses": [], "tables": [], "page": pno}
                    sections.append(current)
                else:
                    buffer.append(line)
            flush()
    # Front matter table = document metadata
    meta = {}
    if sections[0]["tables"]:
        for row in sections[0]["tables"][0]["rows"]:
            if len(row) >= 2:
                meta[row[0]] = row[1]
    tree = {"doc_id": doc_id, "file": fname, "doc_type": dtype, "title": title, "metadata": meta,
            "sections": [s for s in sections if s["clauses"] or s["tables"]],
            "dropped_by_gatekeeper": dropped}
    n_clauses = sum(len(s["clauses"]) for s in tree["sections"])
    n_exc = sum(len(c["exceptions"]) for s in tree["sections"] for c in s["clauses"])
    n_tab = sum(len(s["tables"]) for s in tree["sections"])
    print(f"{doc_id}: {len(tree['sections'])} sections, {n_clauses} clauses, {n_exc} exceptions, {n_tab} tables, {len(dropped)} dropped")
    return tree


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for doc_id in DOCS:
        tree = parse_document(doc_id)
        write_json(OUT_DIR / f"{doc_id}.json", tree)
