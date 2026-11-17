#!/usr/bin/env python3
"""
11_run_tests.py   VALIDATION & DEMO  -  the POC test plan as executable assertions

Run after 00..10. Each check prints PASS / FAIL / SKIP (SKIP = GraphDB not reachable). Exit code 1 if anything FAILs.
The checks mirror the "what success looks like" list in the guide:
  L1 parsing        PDFs exist with 2-3 pages; every document yields clauses; exceptions are kept with their parent
  L2 classification known clauses carry the expected deontic label; pass-2 share stays below 40 %
  L3 grounding      B.1 is hard-grounded to EXCL-FLD and COV-A; soft grounding returns exactly 3 terms
  L4 compiler       12 typed rules compiled, 0 rejected, every rule has a shape file; R08 carries the cross-document warning
  L5 conflicts      R01 scoped by R02 (flood grant beats exclusion); R03 scoped by R04 (FL 14 days beats 72 h); R02/R11 compatible
  RDF / SHACL       generated graph conforms locally; bad records produce >= 8 results; fixed records conform
  GraphDB           repository has 6 named graphs + shapes graph; q01 returns exactly E101/E205/E310/E415; inference returns endorsements as pc:Form
  Graph RAG         each demo answer carries citations of the form [doc | section | p.N] and names the expected entities
  L6 enforcement    coastal bind rejected with R07/R08/R09 to Underwriter; unscheduled flood FNOL -> R01 to Adjuster; clean bind accepted
"""
import json
import re
import sys
import pdfplumber
from common import ROOT, SOURCES, OUTPUT, DOCS, COMPILED_SHAPES_DIR, read_json
from graphdb_client import GraphDB

results = []


def check(name, cond, detail=""):
    results.append((name, "PASS" if cond else "FAIL", detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"   ({detail})" if detail else ""))


def skip(name, why):
    results.append((name, "SKIP", why)); print(f"SKIP  {name}   ({why})")


def clause(doc, ref, stage="03_grounded"):
    t = read_json(OUTPUT / stage / f"{doc}.json")
    return next(c for s in t["sections"] for c in s["clauses"] if c["ref"] == ref)


# ---- L1
for doc_id, (fn, _, _) in DOCS.items():
    p = SOURCES / fn
    n = len(pdfplumber.open(p).pages) if p.exists() else 0
    check(f"L1 PDF {fn} exists with 2-3 pages", 2 <= n <= 3, f"{n} pages")
    tree = read_json(OUTPUT / "01_clause_tree" / f"{doc_id}.json")
    check(f"L1 {doc_id} yields clauses", sum(len(s["clauses"]) for s in tree["sections"]) >= 5)
check("L1 exception kept with parent (E415 4.2 'except when ... maintenance')",
      any("maintenance" in x["text"] for x in clause("MM-CP-E-SERIES", "4.2", "01_clause_tree")["exceptions"]))
check("L1 tables lifted (endorsement availability matrix present)",
      any(tb["header"][0] == "Endorsement" for s in read_json(OUTPUT / "01_clause_tree" / "MM-CP-E-SERIES.json")["sections"] for tb in s["tables"]))

# ---- L2
summ = read_json(OUTPUT / "02_classified" / "_summary.json")
check("L2 E.3 duties clause = Obligation", clause("MM-CP-0010", "E.3")["classification"]["deontic"] == "Obligation")
check("L2 D.1 exclusion/limit clause = Prohibition", clause("MM-CP-0010", "D.1")["classification"]["deontic"] == "Prohibition")
check("L2 A.1 coverage grant = Permission", clause("MM-CP-0010", "A.1")["classification"]["deontic"] == "Permission")
share = (summ["routes"]["pass2-rules"] + summ["routes"]["pass2-llm"]) / sum(summ["routes"].values())
check("L2 pass-2 adjudication share < 40 %", share < 0.40, f"{share:.0%}")

# ---- L3
b1 = clause("MM-CP-0010", "B.1")
hard = {h["code"] for h in b1["grounding"]["hard"]}
check("L3 B.1 hard-grounded to EXCL-FLD and COV-A", {"EXCL-FLD", "COV-A"} <= hard, ", ".join(sorted(hard))[:80])
check("L3 soft grounding returns top-3", len(b1["grounding"]["soft_top3"]) == 3)

# ---- L4
rules = read_json(OUTPUT / "04_rules" / "rules.json")
check("L4 12 rules compiled, 0 rejected", len(rules["compiled"]) == 12 and not rules["rejected"])
check("L4 one shape file per rule", all((COMPILED_SHAPES_DIR / f"{r['rule_id']}.ttl").exists() for r in rules["compiled"]))
r08 = next(r for r in rules["compiled"] if r["rule_id"] == "R08")
check("L4 R08 carries cross-document identifier warning (FL-T03)", any("FL-T03" in w for w in r08.get("warnings", [])))

# ---- L5
dec = read_json(OUTPUT / "05_active_rules" / "decisions.json")["decisions"]
def decision(a, b):
    return next((d for d in dec if set(d["collision"]["rules"]) == {a, b}), None)
d = decision("R01", "R02"); check("L5 R01 (flood exclusion) narrowed by R02 (E101 grant), lex specialis", bool(d and d["loser"] and d["loser"]["rule"] == "R01" and "specialis" in d["basis"]))
d = decision("R03", "R04"); check("L5 R03 (72 h) scoped by R04 (FL 14 days)", bool(d and d["loser"] and d["loser"]["rule"] == "R03"))
d = decision("R02", "R11"); check("L5 R02 vs R11 (vacancy) judged compatible", bool(d and d["decision"] == "compatible"))
active = read_json(OUTPUT / "05_active_rules" / "active_rules.json")["rules"]
check("L5 scoped R01 DSL has conjunctive UNLESS carve-out", "UNLESS Claim.onPolicy.hasEndorsement = MM-CP-E101 AND" in next(r["dsl"] for r in active if r["rule_id"] == "R01"))

# ---- RDF + local SHACL
v = OUTPUT / "07_validation"
check("SHACL generated graph conforms (pySHACL)", (v / "report_01_generated_graph.txt").read_text().startswith("conforms=True"))
nbad = len((v / "report_02_with_bad_records.txt").read_text().splitlines()) - 1
check("SHACL bad records produce >= 8 results", nbad >= 8, f"{nbad} results")
check("SHACL fixed records conform", (v / "report_03_after_fix.txt").read_text().startswith("conforms=True"))

# ---- GraphDB
db = GraphDB()
if db.alive() and db.repo in db.repositories():
    _, rows = db.select("SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g")
    graphs = {r["g"] for r in rows}
    # the ShaclSail shapes graph is NOT visible to SPARQL; read it through the RDF4J statements endpoint with ?context=
    import requests
    from common import SHACL_SHAPE_GRAPH
    shapes_ttl = requests.get(f"{db.base}/repositories/{db.repo}/statements", params={"context": f"<{SHACL_SHAPE_GRAPH}>"},
                              headers={"Accept": "text/turtle"}, timeout=60).text
    check("GraphDB 5 named graphs + ShaclSail shapes graph present",
          len([g for g in graphs if "example.org" in g]) == 5 and shapes_ttl.count("NodeShape") >= 20,
          f"{len(graphs)} data graphs, {shapes_ttl.count('NodeShape')} node shapes")
    qr = read_json(OUTPUT / "08_graphdb" / "query_results.json")
    got = sorted(r["endorsement"] for r in qr["q01_endorsements_modifying_covA_in_TX"]["rows"])
    check("GraphDB q01 = E101, E205, E310, E415", got == ["MM-CP-E101", "MM-CP-E205", "MM-CP-E310", "MM-CP-E415"], ", ".join(got))
    forms = {r["form"] for r in qr["q08_inference_check"]["rows"]}
    check("GraphDB inference: endorsements returned as pc:Form", {"MM-CP-E101", "MM-CP-FL-01"} <= forms)
    check("GraphDB q08b explicit-only returns 0 rows", qr["q08b_explicit_only"]["rows"] == [])
    demo = read_json(OUTPUT / "08_graphdb" / "shacl_commit_demo.json")
    check("GraphDB ShaclSail rejected bad commit (HTTP 500) and accepted fix (204)", demo["bad_records"]["http"] == 500 and demo["fixed_records"]["http"] == 204)
else:
    for n in ("GraphDB graphs", "GraphDB q01", "GraphDB inference", "GraphDB q08b", "GraphDB commit demo"):
        skip(n, "GraphDB not reachable")

# ---- Graph RAG
ans = read_json(OUTPUT / "09_graph_rag" / "answers.json")
cit = re.compile(r"\[MM-[A-Z0-9-]+ \| [^\]|]+ \| p\.\d+\]")
expect = [["MM-CP-E101", "MM-CP-E205", "MM-CP-E310", "MM-CP-E415"], ["EXCL-FLD", "MM-CP-E101", "250,000", "5%"], ["14 calendar days", "72 hours", "60 days"]]
for a, exp in zip(ans, expect):
    check(f"RAG answer cites sources: {a['question'][:45]}...", len(cit.findall(a["answer"])) >= 3, f"{len(cit.findall(a['answer']))} citations, mode {a['mode']}")
    check(f"RAG answer names expected entities {exp[:2]}...", all(e in a["answer"] for e in exp))

# ---- L6
alerts = read_json(OUTPUT / "10_alerts" / "alerts.json")
b = alerts[0]; check("L6 coastal FL bind rejected -> R07,R08,R09 to Underwriter",
                     b["status"] == "rejected" and {a["rule"] for a in b["alerts"]} == {"R07", "R08", "R09"} and all(a["to"] == "Underwriter" for a in b["alerts"]))
f = alerts[1]; check("L6 unscheduled flood FNOL -> R01 to Adjuster", f["status"] == "rejected" and any(a["rule"] == "R01" and a["to"] == "Adjuster" for a in f["alerts"]))
c = alerts[2]; check("L6 clean TX bind accepted, 0 alerts", c["status"] == "accepted" and not c["alerts"])

# ---- summary
n_fail = sum(1 for r in results if r[1] == "FAIL")
print(f"\n{sum(1 for r in results if r[1]=='PASS')} passed, {n_fail} failed, {sum(1 for r in results if r[1]=='SKIP')} skipped")
(OUTPUT / "11_test_report.md").write_text("| check | result | detail |\n|---|---|---|\n" + "\n".join(f"| {n} | {s} | {d} |" for n, s, d in results))
sys.exit(1 if n_fail else 0)
