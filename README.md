# P&C Graph RAG POC on Graphwise GraphDB

Six-layer pipeline (Hierarchical Perception -> Confidence-Routed Classification -> Dynamic Ontology Grounding ->
Formal Logic Compiler -> Normative Conflict Reasoner -> Virtualization & Stream Enforcement) built as twelve
standalone Python scripts over six synthetic P&C documents, loaded into GraphDB with commit-time SHACL validation,
and queried through a hybrid Graph RAG. Everything is synthetic: fictional carrier "Meridian Mutual Insurance Company".

The full walkthrough (Task 1 explanation, Task 2 documents, Task 3 build) is in `GUIDE.md`.

## Folder structure

```
pc-graphrag-poc/
  GUIDE.md                      the mentoring guide (Tasks 1-3)
  README.md                     this file - run order
  requirements.txt
  run_all.sh                    runs 00..11 in order
  config/
    graphdb-repo-config.ttl     repository config: ShaclSail + rdfsplus-optimized + context index + FTS
    typed_rules_seed.json       12 typed rules = stand-in for the constrained-decoding LLM output (Layer 4 step 1)
  ontology/pc_ontology.ttl      P&C ontology (OWL/RDFS + SKOS), ~30 classes, individuals for coverages, perils, states
  shapes/
    core_shapes.ttl             hand-written structural shapes (Form, Endorsement, Filing, Clause, Policy, Claim ...)
    compiled/R01..R12.ttl       Layer 4 output, one shape per rule; active_shapes.ttl = Layer 5 conflict-free set
  queries/_prefixes.rq, q01..q11.rq   verification SPARQL queries
  docs/rml_example.ttl          RML alternative for two of the Python mappings
  scripts/
    common.py                   paths, namespaces, named-graph IRIs, identifier regexes
    rulec.py                    Layer 4 library: Pydantic schema -> DSL -> Lark AST -> SHACL (rdflib)
    graphdb_client.py           RDF4J REST + GraphDB REST (create/delete repository)
    00_generate_source_pdfs.py  Task 2: six synthetic PDFs                       -> sources/*.pdf
    01_parse_clause_tree.py     L1 clause tree with exceptions and tables         -> output/01_clause_tree/
    02_classify_deontic.py      L2 obligation / permission / prohibition           -> output/02_classified/
    03_ground_ontology.py       L3 hard + soft (top-3) grounding                   -> output/03_grounded/
    04_compile_rules.py         L4 typed rules -> DSL -> AST -> SHACL              -> output/04_rules/, shapes/compiled/
    05_resolve_conflicts.py     L5 collisions, precedence, scoping                 -> output/05_active_rules/
    06_build_rdf.py             RDF generation (rdflib mapping functions)          -> output/06_rdf/*.ttl, all.trig
    07_validate_shacl_local.py  SHACL gate #1 (pySHACL) with break/fix demo        -> output/07_validation/
    08_graphdb_load.py          repository, named graphs, shapes, commit rejection, 12 queries -> output/08_graphdb/
    09_graph_rag.py             Graph RAG: SPARQL + vector retrieval + LLM/offline answer -> output/09_graph_rag/
    10_enforce_live_record.py   L6 simulation: events -> RDF -> ShaclSail -> routed alerts -> output/10_alerts/
    11_run_tests.py             test plan as 44 assertions                           -> output/11_test_report.md
  sources/                      the six generated PDFs
  output/                       every intermediate artifact (JSON, Turtle, reports)
```

## Run order

```bash
# 0. environment
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. GraphDB (free edition). 10.8.x runs without a license file; 11.x requires one (a free license can be requested).
docker run -d --name graphdb -p 7200:7200 -e GDB_JAVA_OPTS="-Xmx2g" ontotext/graphdb:10.8.11
#   or unzip a GraphDB distribution and run bin/graphdb. Workbench: http://localhost:7200

# 2. pipeline (each script is standalone; run in order the first time)
python scripts/00_generate_source_pdfs.py
python scripts/01_parse_clause_tree.py
python scripts/02_classify_deontic.py
python scripts/03_ground_ontology.py
python scripts/04_compile_rules.py           # add --llm to let an LLM emit the typed rules (needs OPENAI_API_KEY)
python scripts/05_resolve_conflicts.py
python scripts/06_build_rdf.py
python scripts/07_validate_shacl_local.py
python scripts/08_graphdb_load.py --reset    # creates repo 'pc-poc'
python scripts/09_graph_rag.py               # or: python scripts/09_graph_rag.py "your question"
python scripts/10_enforce_live_record.py
python scripts/11_run_tests.py               # expect: 44 passed, 0 failed
```

Environment variables: `GRAPHDB_URL` (default `http://localhost:7200`), `GRAPHDB_REPO` (default `pc-poc`),
`OPENAI_API_KEY` / `OPENAI_MODEL` (optional; enables LLM pass-2 adjudication, LLM rule extraction and LLM answers).
Without a key every stage still runs deterministically and says so in its output (`mode: offline-extractive`).
