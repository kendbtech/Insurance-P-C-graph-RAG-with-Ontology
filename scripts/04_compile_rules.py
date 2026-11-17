      #!/usr/bin/env python3
"""
04_compile_rules.py   LAYER 4 - Formal Logic Compiler

grounded clauses  +  typed rules (JSON that fits rulec.TypedRule)
      ->  rule DSL  ->  Lark AST  ->  SHACL shapes (one per rule)
      ->  output/04_rules/rules.json , shapes/compiled/<rule_id>.ttl , shapes/compiled/all_compiled_shapes.ttl

Step 1 (constrained decoding) is the ONLY model step and is pluggable:
   default      : read config/typed_rules_seed.json  (the JSON a constrained LLM must emit; curated for the POC)
   --llm        : ask an LLM to emit TypedRule JSON for each rule-bearing clause, validated by the Pydantic schema
                  (needs OPENAI_API_KEY; uses structured outputs with the JSON schema from TypedRule.model_json_schema()).
Steps 2 and 3 are deterministic and run in milliseconds.

Grounding consistency check: every identifier in a typed rule must be either a hard-grounded entity of the
source clause (Layer 3) or a known ontology individual. Otherwise the rule is rejected and reported.
"""
import argparse
import json
import os
import sys
from lark.exceptions import LarkError
from rdflib import Graph
from common import ROOT, OUTPUT, DOCS, COMPILED_SHAPES_DIR, PCD, ID_PATTERNS, read_json, write_json
from rulec import TypedRule, to_dsl, parse, compile_shape

IN_DIR = OUTPUT / "03_grounded"
OUT_DIR = OUTPUT / "04_rules"
SEED = ROOT / "config" / "typed_rules_seed.json"
KNOWN_INDIVIDUALS = {"Flood", "Water", "Windstorm", "Hail", "Fire", "EarthMovement", "MechanicalBreakdown", "Theft",
                     "Vandalism", "Mold", "SprinklerLeakage", "FL", "TX", "NY", "COV-A", "COV-B", "COV-C", "COV-D",
                     "A", "AE", "V", "VE", "Approved", "Pending", "NotFiled", "ANY"}


CORPUS_IDS = set()   # identifiers that occur in any table of the corpus (territories, forms, codes...)


def load_clauses():
    idx = {}
    for d in DOCS:
        t = read_json(IN_DIR / f"{d}.json")
        for s in t["sections"]:
            for c in s["clauses"]:
                idx[c["clause_id"]] = c
            for tb in s["tables"]:
                for row in [tb["header"]] + tb["rows"]:
                    for cell in row:
                        for rx in ID_PATTERNS.values():
                            CORPUS_IDS.update(m if isinstance(m, str) else m[0] for m in rx.findall(cell))
    return idx


def ids_in_rule(r: TypedRule):
    out = set(r.object_ids)
    for c in r.conditions + r.requirements + r.exceptions:
        if isinstance(c.value, list):
            out |= set(c.value)
        elif isinstance(c.value, str) and not c.value[0].isupper() is False and "." not in c.value:
            out.add(c.value)
    return out


def consistency_check(r: TypedRule, clause):
    """Return (rejected_ids, warnings).
    Accepted silently : known ontology individuals, identifiers hard-grounded in the clause, the clause's own
                        document / section identifiers (a form rarely names itself inside its own clauses).
    Accepted + warned : identifiers that exist elsewhere in the corpus (e.g. FL-T03 named only in the rate manual
                        while the UW clause says 'Florida Tier 1 coastal counties'). A reviewer should confirm these.
    Rejected          : anything else - the model invented an identifier."""
    hard = {h["code"] for h in clause["grounding"]["hard"]} | {h["iri"].replace(PCD, "") for h in clause["grounding"]["hard"]}
    own = {clause["doc_id"]} | set(ID_PATTERNS["form"].findall(clause["section"]))
    bad, warnings = [], []
    for i in ids_in_rule(r):
        plain = i.replace("CC-", "")
        if i in KNOWN_INDIVIDUALS or i in hard or plain in hard or i in own:
            continue
        if i.startswith("CC-") and plain in clause["text"]:
            continue
        if i in CORPUS_IDS or plain in CORPUS_IDS:
            warnings.append(f"cross-document identifier {i}: not in clause text, resolved from corpus tables; confirm in review")
            continue
        bad.append(i)
    return bad, warnings


def llm_typed_rules(clauses):
    """Optional: constrained decoding with an LLM. The schema IS the constraint."""
    from openai import OpenAI
    client = OpenAI()
    schema = TypedRule.model_json_schema()
    rules = []
    for cid, c in clauses.items():
        if c["classification"]["deontic"] not in ("Obligation", "Prohibition", "Permission"):
            continue
        prompt = ("You convert one P&C insurance clause into ONE typed rule that fits the JSON schema exactly. "
                  "Use only identifiers present in the clause or in the grounded entities. If the clause is not "
                  "checkable against a Policy, Location or Claim record, return {\"rule_id\":\"SKIP\"}.\n"
                  f"Clause id: {cid}\nDeontic (Layer 2): {c['classification']['deontic']}\n"
                  f"Grounded entities: {[h['code'] for h in c['grounding']['hard']]}\n"
                  f"Top ontology terms: {[t['label'] for t in c['grounding']['soft_top3']]}\nClause: {c['text']}")
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0,
            response_format={"type": "json_schema", "json_schema": {"name": "TypedRule", "schema": schema}},
            messages=[{"role": "user", "content": prompt}])
        obj = json.loads(r.choices[0].message.content)
        if obj.get("rule_id") != "SKIP":
            rules.append(obj)
    return rules


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="generate typed rules with an LLM instead of the seed file")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    COMPILED_SHAPES_DIR.mkdir(parents=True, exist_ok=True)
    clauses = load_clauses()
    raw_rules = llm_typed_rules(clauses) if args.llm else read_json(SEED)["rules"]

    compiled, rejected, all_shapes = [], [], Graph()
    for raw in raw_rules:
        try:
            r = TypedRule(**raw)                       # schema validation (Pydantic)
        except Exception as e:
            rejected.append({"rule": raw.get("rule_id"), "stage": "schema", "error": str(e)[:200]}); continue
        clause = clauses.get(r.source_clause)
        if clause is None:
            rejected.append({"rule": r.rule_id, "stage": "provenance", "error": f"unknown clause {r.source_clause}"}); continue
        bad, warnings = consistency_check(r, clause)
        if bad:
            rejected.append({"rule": r.rule_id, "stage": "grounding", "error": f"identifiers not grounded in clause: {bad}"}); continue
        dsl = to_dsl(r)
        try:
            ast = parse(dsl)                           # parse guarantee
        except LarkError as e:
            rejected.append({"rule": r.rule_id, "stage": "grammar", "error": str(e)[:200]}); continue
        g = compile_shape(r.rule_id, ast, r.message)   # deterministic SHACL compile
        g.serialize(COMPILED_SHAPES_DIR / f"{r.rule_id}.ttl", format="turtle")
        all_shapes += g
        compiled.append({"rule_id": r.rule_id, "dsl": dsl, "ast": ast, "message": r.message,
                         "source_clause": r.source_clause, "layer2_deontic": clause["classification"]["deontic"],
                         "shape_iri": f"https://example.org/pc/shape/{r.rule_id}", "status": "active",
                         "warnings": warnings})
        print(f"{r.rule_id}  OK   {dsl[:110]}" + (f"\n      WARN {warnings}" if warnings else ""))
    for rj in rejected:
        print("REJECTED", rj)

    all_shapes.serialize(COMPILED_SHAPES_DIR / "all_compiled_shapes.ttl", format="turtle")
    write_json(OUT_DIR / "rules.json", {"compiled": compiled, "rejected": rejected})
    print(f"\n{len(compiled)} rules compiled, {len(rejected)} rejected -> {COMPILED_SHAPES_DIR}")
