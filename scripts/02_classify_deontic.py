#!/usr/bin/env python3
"""
02_classify_deontic.py   LAYER 2 - Confidence-Routed Classification

clause tree  ->  every clause tagged Obligation | Permission | Prohibition with a confidence
             ->  output/02_classified/<doc>.json  and  output/02_classified/_summary.json

Routing (mirrors the design):
  Pass 1  fast classifier   : cheap lexical scorer (stand-in for a small local model such as a
                              fine-tuned MiniLM / Mistral-7B). Produces a label + confidence 0..1.
  Gate    confidence >= 0.60: accept pass-1 label.
  Pass 2  strict adjudicator: only for the uncertain band. Uses an LLM when OPENAI_API_KEY is set
                              (strict few-shot, JSON-only answer); otherwise a deterministic
                              "main verb" rule (the FIRST deontic marker in the clause decides).

Why confidence routing?  Most clauses are easy ("we will not pay" / "you must"). Spending model
tokens only on the ambiguous 10-20% keeps cost near zero and makes the easy path reproducible.
"""
import json
import os
import re
from common import OUTPUT, DOCS, read_json, write_json

IN_DIR = OUTPUT / "01_clause_tree"
OUT_DIR = OUTPUT / "02_classified"
GATE = 0.60

# Weighted lexical cues.  Order matters only for the pass-2 "first marker" rule.
CUES = {
    "Prohibition": [
        (r"\bwill not pay\b", 3), (r"\bmust not\b", 3), (r"\bmay not\b", 3), (r"\bshall not\b", 3),
        (r"\bprohibited\b", 3), (r"\bnot covered\b", 2.5), (r"\bis not covered\b", 3),
        (r"\bdoes not include\b", 2), (r"\bis not extended\b", 2), (r"\bnot be used\b", 3),
        (r"\bnot available\b", 2), (r"\bthere can be no\b", 3), (r"\bno .{0,40} may be issued\b", 3),
        (r"\bcannot\b", 2), (r"\bineligible\b", 2.5), (r"\bwe will reduce\b", 1.5),
        (r"\bnot .{0,25} unless\b", 1),
    ],
    "Obligation": [
        (r"\byou must\b", 3), (r"\bmust\b", 2.5), (r"\bshall\b", 2), (r"\bis required to\b", 3),
        (r"\bare required to\b", 3), (r"\bis required\b", 2), (r"\brequired\b", 1.5), (r"\bmandatory\b", 3),
        (r"\bwithin \d+ (?:hours|days|business days|calendar days)\b", 1.5), (r"\bmust include\b", 3),
        (r"\bhas to\b", 2), (r"\bis amended to read: you must\b", 3),
    ],
    "Permission": [
        (r"\bwe will pay\b", 3), (r"\bwe will give\b", 1), (r"\bmay be attached\b", 3), (r"\bmay be written\b", 3),
        (r"\bmay cancel\b", 2), (r"\bmay extend\b", 2), (r"\bmay\b", 1.5), (r"\bis eligible\b", 3),
        (r"\beligible\b", 1.5), (r"\bis deleted\b", 2.5), (r"\bcovered up to\b", 2.5), (r"\bis covered\b", 2.5),
        (r"\bcoverage grant\b", 3), (r"\bwe will pay for\b", 3), (r"\bapproved\b", 1),
        (r"\bamended to include\b", 2), (r"\bdoes not apply\b", 2),  # an exclusion that does not apply = grant
    ],
}
COMPILED = {k: [(re.compile(p, re.I), w) for p, w in v] for k, v in CUES.items()}


def pass1(text):
    """Fast lexical scorer -> (label, confidence, scores)."""
    scores = {k: 0.0 for k in CUES}
    for label, pats in COMPILED.items():
        for rx, w in pats:
            scores[label] += w * len(rx.findall(text))
    total = sum(scores.values())
    if total == 0:
        return "Permission", 0.34, scores        # descriptive text defaults to a weak grant
    label = max(scores, key=scores.get)
    conf = round(scores[label] / total, 3)
    return label, conf, scores


def pass2_rules(text):
    """Strict adjudicator (deterministic): the FIRST deontic marker in reading order decides.
    Rationale: in insurance drafting the operative verb comes first; later markers are usually
    conditions or exceptions ('...unless you must...')."""
    first = None
    for label, pats in COMPILED.items():
        for rx, _ in pats:
            m = rx.search(text)
            if m and (first is None or m.start() < first[0]):
                first = (m.start(), label)
    return (first[1] if first else "Permission"), "pass2-rules"


def pass2_llm(text):
    """Strict adjudicator (LLM). Only called when OPENAI_API_KEY is set. JSON-only output."""
    from openai import OpenAI
    client = OpenAI()
    prompt = ("Classify the operative deontic force of this P&C insurance clause. Answer ONLY JSON "
              '{"label": "Obligation|Permission|Prohibition"}.\n'
              "Obligation = a party must do something (duties after loss, deadlines, required forms).\n"
              "Permission = a party may do something or coverage is granted (we will pay, may be attached).\n"
              "Prohibition = must not / will not pay / ineligible / not covered.\n"
              f"Clause: {text}")
    r = client.chat.completions.create(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0,
                                       response_format={"type": "json_object"},
                                       messages=[{"role": "user", "content": prompt}])
    return json.loads(r.choices[0].message.content)["label"], "pass2-llm"


def classify(text):
    label, conf, scores = pass1(text)
    route = "pass1"
    if conf < GATE:
        if os.environ.get("OPENAI_API_KEY"):
            try:
                label, route = pass2_llm(text)
            except Exception as e:  # fall back, never block the pipeline
                label, route = pass2_rules(text)
                route += f" (llm-error: {type(e).__name__})"
        else:
            label, route = pass2_rules(text)
    return {"deontic": label, "confidence": conf, "route": route, "scores": scores}


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {"gate": GATE, "docs": {}, "routes": {"pass1": 0, "pass2-rules": 0, "pass2-llm": 0}, "labels": {}}
    for doc_id in DOCS:
        tree = read_json(IN_DIR / f"{doc_id}.json")
        n = 0
        for sec in tree["sections"]:
            for c in sec["clauses"]:
                c["classification"] = classify(c["text"])
                for x in c["exceptions"]:
                    # Exceptions keep their parent's tag context; we still record what they look like on their own.
                    x["classification"] = classify(x["text"])
                r = c["classification"]["route"].split(" ")[0]
                summary["routes"][r] = summary["routes"].get(r, 0) + 1
                lbl = c["classification"]["deontic"]
                summary["labels"][lbl] = summary["labels"].get(lbl, 0) + 1
                n += 1
        summary["docs"][doc_id] = n
        write_json(OUT_DIR / f"{doc_id}.json", tree)
    write_json(OUT_DIR / "_summary.json", summary)
    print(json.dumps(summary, indent=1))
