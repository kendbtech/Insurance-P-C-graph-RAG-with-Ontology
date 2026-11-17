#!/usr/bin/env bash
# Runs the whole POC in order. Requires GraphDB at $GRAPHDB_URL (default http://localhost:7200) for steps 08-11.
set -euo pipefail
cd "$(dirname "$0")"
for s in 00_generate_source_pdfs 01_parse_clause_tree 02_classify_deontic 03_ground_ontology 04_compile_rules \
         05_resolve_conflicts 06_build_rdf 07_validate_shacl_local; do
  echo "================ $s"; python scripts/$s.py
done
echo "================ 08_graphdb_load";        python scripts/08_graphdb_load.py --reset
echo "================ 09_graph_rag";           python scripts/09_graph_rag.py
echo "================ 10_enforce_live_record"; python scripts/10_enforce_live_record.py
echo "================ 11_run_tests";           python scripts/11_run_tests.py
