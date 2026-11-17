#!/usr/bin/env python3
"""
08_graphdb_load.py   GRAPH LOAD + SHACL GATE #2 (commit-time, GraphDB ShaclSail) + SPARQL verification

1. Create repository 'pc-poc' from config/graphdb-repo-config.ttl  (ShaclSail + rdfsplus-optimized)
2. Load named graphs:  ontology, data, clauses, rules, operational
3. Load shapes (core + Layer-5 active shapes) into the ShaclSail reserved graph
      <http://rdf4j.org/schema/rdf4j#SHACLShapeGraph>   -> this commit validates everything already loaded
4. Demonstrate commit-time rejection: POST bad_records.ttl  -> HTTP 500 + validation report, nothing stored
   then POST fixed_records.ttl -> HTTP 204
5. Run queries/q*.rq and save results to output/08_graphdb/query_results.json

Usage:  python scripts/08_graphdb_load.py [--reset]        (GRAPHDB_URL / GRAPHDB_REPO env vars override defaults)
"""
import argparse
import json
import re
import sys
from common import (ROOT, OUTPUT, ONTOLOGY_TTL, CORE_SHAPES_TTL, COMPILED_SHAPES_DIR, QUERIES, GRAPH_ONTOLOGY, GRAPH_DATA,
                    GRAPH_CLAUSES, GRAPH_RULES, GRAPH_OPS, SHACL_SHAPE_GRAPH, write_json)
from graphdb_client import GraphDB, print_table

RDF_DIR = OUTPUT / "06_rdf"
VAL_DIR = OUTPUT / "07_validation"
OUT_DIR = OUTPUT / "08_graphdb"
CONFIG = ROOT / "config" / "graphdb-repo-config.ttl"


def summarize_report(body):
    """ShaclSail returns the validation report inside the error text. Pull out the useful lines."""
    msgs = re.findall(r'sh:resultMessage\s+"([^"]+)"', body) or re.findall(r'resultMessage[^"]*"([^"]+)"', body)
    focus = re.findall(r'sh:focusNode\s+<([^>]+)>', body)
    return {"messages": sorted(set(msgs)), "focusNodes": sorted(set(focus)), "raw_head": body[:600]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--reset", action="store_true"); args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = GraphDB()
    if not db.alive():
        sys.exit(f"GraphDB not reachable at {db.base}. Start it (docker run -p 7200:7200 ontotext/graphdb:10.8.11) and retry.")

    # 1. repository
    if args.reset and db.repo in db.repositories():
        print("deleting repository", db.repo, db.delete_repository())
    if db.repo not in db.repositories():
        print("creating repository", db.repo, "->", db.create_repository(CONFIG))
    else:
        print("repository exists:", db.repo)

    # 2. named graphs (PUT = replace, so the script is idempotent)
    loads = [(ONTOLOGY_TTL, GRAPH_ONTOLOGY), (RDF_DIR / "data.ttl", GRAPH_DATA), (RDF_DIR / "clauses.ttl", GRAPH_CLAUSES),
             (RDF_DIR / "rules.ttl", GRAPH_RULES), (RDF_DIR / "operational.ttl", GRAPH_OPS)]
    for path, graph in loads:
        code, body = db.load_turtle(path, graph, replace=True)
        print(f"load {path.name:<18} -> {graph.split('/')[-1]:<12} HTTP {code}")
        if code >= 400:
            print(body[:800]); sys.exit(1)

    # 3. shapes -> reserved ShaclSail graph (validates all existing data on commit)
    db.clear_graph(SHACL_SHAPE_GRAPH)
    for p in (CORE_SHAPES_TTL, COMPILED_SHAPES_DIR / "active_shapes.ttl"):
        code, body = db.load_turtle(p, SHACL_SHAPE_GRAPH)
        print(f"load shapes {p.name:<22} -> SHACLShapeGraph HTTP {code}")
        if code >= 400:
            print(body[:1500]); sys.exit(1)
    print("repository size (explicit + inferred statements):", db.size())

    # 4. commit-time rejection demo
    demo = {}
    code, body = db.load_turtle(VAL_DIR / "bad_records.ttl", GRAPH_OPS)
    demo["bad_records"] = {"http": code, "report": summarize_report(body)}
    print(f"\nPOST bad_records.ttl -> HTTP {code}  (expected 500: ShaclSail rejected the transaction)")
    for m in demo["bad_records"]["report"]["messages"]:
        print("   violation:", m[:110])
    code, body = db.load_turtle(VAL_DIR / "fixed_records.ttl", GRAPH_OPS)
    demo["fixed_records"] = {"http": code}
    print(f"POST fixed_records.ttl -> HTTP {code}  (expected 204: accepted)")
    # keep the repository in its reference state for the next scripts: remove the demo records again in ONE transaction
    # (ShaclSail validates deletes as well - removing a Location before its Policy would violate sh:class pc:Location)
    ids = ["policy/POL-NY-0099", "policy/POL-FL-0002", "policy/POL-TX-0003", "location/LOC-0099", "location/LOC-0002",
           "location/LOC-0003", "claim/CLM-0002", "claim/CLM-0003", "MM-CP-E999"]
    vals = " ".join(f"<https://example.org/pc/id/{i}>" for i in ids)
    code, body = db.update(f"DELETE {{ GRAPH <{GRAPH_OPS}> {{ ?s ?p ?o }} }} WHERE {{ VALUES ?s {{ {vals} }} GRAPH <{GRAPH_OPS}> {{ ?s ?p ?o }} }}")
    print(f"cleanup of demo records -> HTTP {code}; operational graph size now "
          f"{db.select(f'SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{GRAPH_OPS}> {{ ?s ?p ?o }} }}')[1][0]['n']} (expected 44)")

    # 5. verification queries
    results = {}
    for q in sorted(QUERIES.glob("q*.rq")):
        text = q.read_text()
        title = next((l[2:] for l in text.splitlines() if l.startswith("# ")), q.stem)
        try:
            cols, rows = db.select(text)
            results[q.stem] = {"title": title, "columns": cols, "rows": rows}
            print(f"\n### {q.stem}: {title}\n")
            print_table(cols, rows)
        except Exception as e:
            results[q.stem] = {"title": title, "error": str(e)[:300]}
            print(f"\n### {q.stem}: ERROR {str(e)[:200]}")
    write_json(OUT_DIR / "query_results.json", results)
    write_json(OUT_DIR / "shacl_commit_demo.json", demo)
