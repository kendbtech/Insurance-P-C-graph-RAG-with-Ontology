"""Shared constants and helpers for all pipeline scripts."""
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (one level above this file's directory)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "sources"
OUTPUT = ROOT / "output"
ONTOLOGY_TTL = ROOT / "ontology" / "pc_ontology.ttl"
CORE_SHAPES_TTL = ROOT / "shapes" / "core_shapes.ttl"
COMPILED_SHAPES_DIR = ROOT / "shapes" / "compiled"
QUERIES = ROOT / "queries"

PC = "https://example.org/pc/ontology#"
PCD = "https://example.org/pc/id/"
GRAPH_ONTOLOGY = "https://example.org/pc/graph/ontology"
GRAPH_DATA = "https://example.org/pc/graph/data"
GRAPH_CLAUSES = "https://example.org/pc/graph/clauses"
GRAPH_RULES = "https://example.org/pc/graph/rules"
GRAPH_OPS = "https://example.org/pc/graph/operational"
SHACL_SHAPE_GRAPH = "http://rdf4j.org/schema/rdf4j#SHACLShapeGraph"   # RDF4J ShaclSail reserved graph

GRAPHDB_URL = os.environ.get("GRAPHDB_URL", "http://localhost:7200")
GRAPHDB_REPO = os.environ.get("GRAPHDB_REPO", "pc-poc")

# Document id  ->  (file, type, title)
DOCS = {
    "MM-CP-0010":  ("01_policy_form_MM-CP-0010.pdf", "PolicyForm", "Building and Personal Property Coverage Form"),
    "MM-CP-E-SERIES": ("02_endorsements_MM-CP-E-series.pdf", "EndorsementPackage", "Commercial Property Endorsements Package"),
    "MM-UW-CP-2025": ("03_underwriting_guidelines_MM-UW-CP-2025.pdf", "UnderwritingGuideline", "Commercial Property Underwriting Guidelines"),
    "MM-RM-CP-2025": ("04_rate_manual_MM-RM-CP-2025.pdf", "RateManual", "Commercial Property Rate Manual"),
    "MM-CM-CP-2025": ("05_claims_manual_MM-CM-CP-2025.pdf", "ClaimsManual", "Commercial Property Claims Handling Manual"),
    "MM-FILINGS-CP-2025": ("06_state_filings_MM-2025.pdf", "StateFilingRegister", "State Form and Rate Filing Register"),
}

# Deterministic identifier patterns (used by L1 gatekeeper, L3 hard grounding, RDF build)
ID_PATTERNS = {
    "form":       re.compile(r"\bMM-CP-(?:\d{4}|E\d{3}|FL-01)\b"),
    "coverage":   re.compile(r"\bCOV-[A-D]\b"),
    "exclusion":  re.compile(r"\bEXCL-(?:FLD|EQ|WAR|MOLD|WEAR)\b"),
    "state":      re.compile(r"\b(?:FL|TX|NY)\b"),
    "filing":     re.compile(r"\bMM-(?:FL|TX|NY)-2025-\d{4}\b"),
    "territory":  re.compile(r"\b(?:FL|TX|NY)-T\d{2}\b"),
    "classcode":  re.compile(r"\b(?:class code|Class Code|code)\s+(\d{4})\b"),
    "construction": re.compile(r"\bCC[1-6]\b"),
    "protection": re.compile(r"\bPC(?:10|[1-9])\b"),
    "factor":     re.compile(r"\b(?:SPR-1|ALM-[12]|WH-[25])\b"),
    "document":   re.compile(r"\bMM-(?:UW|RM|CM)-CP-2025\b"),
}

DEONTIC = ["Obligation", "Permission", "Prohibition"]


def read_json(p):
    return json.loads(Path(p).read_text())


def write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    print(f"wrote {p}")


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
