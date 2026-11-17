#!/usr/bin/env python3
"""
05_resolve_conflicts.py   LAYER 5 - Normative Conflict Reasoner

compiled rules (ASTs)  ->  collision detection  ->  precedence  ->  scoped, conflict-free ACTIVE rule set
      ->  output/05_active_rules/active_rules.json , decisions.json , shapes/compiled/active_shapes.ttl

Step 1  Detect collisions
        - opposite deontics on the same (subject, action) whose objects overlap, using SUBSUMPTION
          (skos:broader in the ontology: Flood is a kind of Water)           e.g. R01 (exclude Flood) vs R02 (grant Flood)
        - same deontic + same action but different deadline values            e.g. R03 (72 h) vs R04 (14 days)
Step 2  Apply precedence
        - lex specialis  : state amendatory > endorsement > base form > manual   (more specific source wins)
        - lex posterior  : later edition beats earlier edition of the same form family
Step 3  Scope and log
        - the losing rule is NOT deleted; it gets the winner's applicability carved out as an exception / condition,
          is re-compiled, and the decision is logged with both sources.

The POC uses a small deterministic resolver. A production system would hand the same decision table to an SMT /
defeasible-logic solver (e.g. Z3) so that transitive and multi-rule interactions are checked exhaustively.
"""
import copy
import json
import re
from rdflib import Graph, Namespace, SKOS
from common import OUTPUT, COMPILED_SHAPES_DIR, ONTOLOGY_TTL, PCD, read_json, write_json
from rulec import compile_shape

IN = OUTPUT / "04_rules" / "rules.json"
OUT_DIR = OUTPUT / "05_active_rules"

# ----- precedence table (source specificity). Higher wins.
SPECIFICITY = [("MM-CP-FL-01", 4, "state amendatory endorsement"),
               ("MM-CP-E", 3, "endorsement"),
               ("MM-CP-0010", 2, "base policy form"),
               ("MM-CP-1030", 2, "base causes-of-loss form"),
               ("MM-UW", 1, "manual"), ("MM-CM", 1, "manual"), ("MM-RM", 1, "manual"), ("MM-FILINGS", 1, "register")]
# conditions on these attributes only delimit WHERE a rule applies (form / state / territory), they are not
# substantive restrictions like 'vacant > 60 days'
SCOPE_ATTRS = {"hasForm", "inState", "hasEndorsement", "inTerritory"}
EDITIONS = {"MM-CP-FL-01": "2025-07", "MM-CP-E101": "2025-06", "MM-CP-E310": "2025-03", "MM-CP-E205": "2025-01",
            "MM-CP-E415": "2025-01", "MM-CP-0010": "2025-01", "MM-CP-1030": "2025-01"}


def source_rank(rule):
    src = rule["source_clause"]
    m = re.search(r"MM-CP-(?:E\d{3}|FL-01|\d{4})", src.split("#")[1]) or re.search(r"MM-CP-(?:E\d{3}|FL-01|\d{4})", src)
    form = m.group(0) if m else src.split("#")[0]
    for prefix, rank, label in SPECIFICITY:
        if form.startswith(prefix) or src.startswith(prefix):
            return rank, EDITIONS.get(form, "0000-00"), label, form
    return 0, "0000-00", "unknown", form


def broader_closure():
    g = Graph().parse(ONTOLOGY_TTL, format="turtle")
    up = {}
    for s, o in g.subject_objects(SKOS.broader):
        up.setdefault(str(s).replace(PCD, ""), set()).add(str(o).replace(PCD, ""))
    return up


def overlaps(ids_a, ids_b, up):
    """True if any object in a equals or is subsumed by (or subsumes) an object in b."""
    def anc(x):
        seen, stack = set(), [x]
        while stack:
            cur = stack.pop()
            for p in up.get(cur, ()):
                if p not in seen:
                    seen.add(p); stack.append(p)
        return seen
    for a in ids_a:
        for b in ids_b:
            if a == b or b in anc(a) or a in anc(b):
                return True, (a, b)
    return False, None


def conditions_entailed(narrow, wide):
    """Do the conditions of `wide` all appear in `narrow`? (cheap syntactic entailment for the POC)"""
    w = [json.dumps(c, sort_keys=True) for c in wide["ast"]["when"]]
    n = [json.dumps(c, sort_keys=True) for c in narrow["ast"]["when"]]
    return all(c in n for c in w)


def detect(rules, up):
    found = []
    for i, a in enumerate(rules):
        for b in rules[i + 1:]:
            A, B = a["ast"], b["ast"]
            if A["subject"] != B["subject"] or A["action"] != B["action"]:
                continue
            da, db = A["deontic"], B["deontic"]
            if {da, db} == {"PERMISSION", "PROHIBITION"}:
                ia = A["object"]["ids"] if A["object"] else []
                ib = B["object"]["ids"] if B["object"] else []
                ov, pair = overlaps(ia, ib, up)
                if ov:
                    found.append({"type": "grant-vs-exclusion", "rules": [a["rule_id"], b["rule_id"]], "overlap": pair})
            elif da == db == "OBLIGATION" and A["within"] and B["within"] and A["within"] != B["within"]:
                found.append({"type": "deadline-value-conflict", "rules": [a["rule_id"], b["rule_id"]],
                              "values": [A["within"], B["within"]]})
    return found


def resolve(collision, by_id, decisions):
    a, b = (by_id[r] for r in collision["rules"])
    ra, rb = source_rank(a), source_rank(b)
    winner, loser = (a, b) if (ra[0], ra[1]) > (rb[0], rb[1]) else (b, a)
    rw, rl = source_rank(winner), source_rank(loser)
    basis = "lex specialis (more specific source)" if rw[0] != rl[0] else "lex posterior (later edition)"

    # Special case: a prohibition whose own conditions are strictly narrower than the permission's is compatible
    # (e.g. vacancy rule R11 vs flood grant R02): both stay active, nothing is carved.
    perm = a if a["ast"]["deontic"] == "PERMISSION" else b if b["ast"]["deontic"] == "PERMISSION" else None
    proh = b if perm is a else a if perm is b else None
    substantive = [c for c in (proh["ast"]["when"] if proh else []) if c["path"][-1] not in SCOPE_ATTRS]
    if perm and proh and substantive and not conditions_entailed(perm, proh):
        decisions.append({"collision": collision, "decision": "compatible", "basis":
                          "prohibition has its own narrower condition; both rules stay active",
                          "winner": None, "loser": None})
        return

    loser["status"] = "scoped"
    loser.setdefault("overridden_by", []).append(winner["rule_id"])
    if collision["type"] == "grant-vs-exclusion":
        # carve the permission's applicability (its WHEN) out of the prohibition as UNLESS
        # and also require the permission's REQUIRES to hold for the carve-out
        carve = [c for c in winner["ast"]["when"] if c["path"][1:] != ["causeOfLoss"]] + winner["ast"].get("requires", [])
        loser["ast"]["unless"].append(carve)            # ONE group: all carve conditions must hold together
        loser["dsl"] += " UNLESS " + " AND ".join(f"{'.'.join(c['path'])} {c['op']} {_v(c['value'])}" for c in carve)
        how = f"{loser['rule_id']} narrowed: exclusion does not apply where {winner['rule_id']} grants coverage"
    else:
        # the winner's condition becomes the complement condition of the loser
        for c in winner["ast"]["when"]:
            neg = dict(c); neg["op"] = {"=": "!=", "IN": "NOT_IN"}.get(c["op"], c["op"])
            loser["ast"]["when"].append(neg)
            loser["dsl"] += f" WHEN {'.'.join(c['path'])} {neg['op']} {_v(c['value'])}"
        how = f"{loser['rule_id']} scoped to the complement of {winner['rule_id']}'s conditions"
    decisions.append({"collision": collision, "decision": how, "basis": basis,
                      "winner": {"rule": winner["rule_id"], "source": winner["source_clause"], "rank": rw[2], "edition": rw[1]},
                      "loser": {"rule": loser["rule_id"], "source": loser["source_clause"], "rank": rl[2], "edition": rl[1]}})


def _v(v):
    if "id" in v: return v["id"]
    if "list" in v: return "(" + ", ".join(v["list"]) + ")"
    if "bool" in v: return str(v["bool"]).lower()
    if "number" in v: return str(v["number"])
    return ".".join(v["path"])


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rules = copy.deepcopy(read_json(IN)["compiled"])
    by_id = {r["rule_id"]: r for r in rules}
    up = broader_closure()

    collisions = detect(rules, up)
    decisions = []
    for col in collisions:
        resolve(col, by_id, decisions)

    # re-compile every rule with its final status -> active (conflict-free) shape set
    active = Graph()
    for r in rules:
        g = compile_shape(r["rule_id"], r["ast"], r["message"], r["status"])
        g.serialize(COMPILED_SHAPES_DIR / f"{r['rule_id']}.ttl", format="turtle")
        active += g
    active.serialize(COMPILED_SHAPES_DIR / "active_shapes.ttl", format="turtle")

    write_json(OUT_DIR / "active_rules.json", {"rules": rules})
    write_json(OUT_DIR / "decisions.json", {"collisions_detected": collisions, "decisions": decisions})
    print(f"\n{len(collisions)} collisions detected")
    for d in decisions:
        print(" -", d["collision"]["type"], d["collision"]["rules"], "->", d["decision"], "|", d["basis"])
    print(f"\nactive rule set: {len(rules)} rules "
          f"({sum(r['status']=='active' for r in rules)} active, {sum(r['status']=='scoped' for r in rules)} scoped)")
    print("scoped DSL:")
    for r in rules:
        if r["status"] == "scoped":
            print("  ", r["dsl"])
