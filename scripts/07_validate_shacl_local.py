#!/usr/bin/env python3
"""
07_validate_shacl_local.py   SHACL GATE #1 (pre-load, local, pySHACL)

1. Validate the whole generated graph (ontology + data + clauses + rules + valid operational records)
   against   shapes/core_shapes.ttl  +  shapes/compiled/active_shapes.ttl.      Expect: conforms = True
2. Demonstrate violations: load output/07_validation/bad_records.ttl (written by this script) - an endorsement
   with no coverage, a policy in NY on an unapproved form, a FL policy without FL-01, a claim with late notice,
   a prohibited class code - and print the validation report.                   Expect: conforms = False
3. Show the fix: apply the corrections and re-validate.                          Expect: conforms = True

Reports are written as Turtle (machine-readable) and as a short text table.
"""
from pyshacl import validate
from rdflib import Graph, Dataset, URIRef, Namespace, Literal, RDF, XSD
from rdflib.namespace import SH
from common import OUTPUT, ONTOLOGY_TTL, CORE_SHAPES_TTL, COMPILED_SHAPES_DIR, PC, PCD

RDF_DIR = OUTPUT / "06_rdf"
OUT_DIR = OUTPUT / "07_validation"
pc, pcd = Namespace(PC), Namespace(PCD)


def load_shapes():
    s = Graph().parse(CORE_SHAPES_TTL, format="turtle")
    s.parse(COMPILED_SHAPES_DIR / "active_shapes.ttl", format="turtle")
    return s


def load_data():
    ds = Dataset().parse(RDF_DIR / "all.trig", format="trig")
    g = Graph()
    for ng in ds.graphs():
        g += ng
    return g


def run(data, shapes, label):
    conforms, report_graph, report_text = validate(
        data, shacl_graph=shapes, ont_graph=Graph().parse(ONTOLOGY_TTL, format="turtle"),
        inference="rdfs",              # subclass reasoning so pc:Endorsement counts as pc:Form etc.
        advanced=True, allow_warnings=False, meta_shacl=False, debug=False)
    report_graph.serialize(OUT_DIR / f"report_{label}.ttl", format="turtle")
    rows = []
    for r in report_graph.subjects(RDF.type, SH.ValidationResult):
        rows.append((str(report_graph.value(r, SH.sourceShape)).split("/")[-1],
                     str(report_graph.value(r, SH.focusNode)).replace(PCD, "pcd:"),
                     str(report_graph.value(r, SH.resultMessage))[:95]))
    print(f"\n=== {label}: conforms = {conforms}  ({len(rows)} results)")
    for shp, focus, msg in sorted(rows):
        print(f"  [{shp:>16}] {focus:<34} {msg}")
    (OUT_DIR / f"report_{label}.txt").write_text(f"conforms={conforms}\n" + "\n".join(f"{a}\t{b}\t{c}" for a, b, c in rows))
    return conforms


def bad_records():
    g = Graph(); g.bind("pc", pc); g.bind("pcd", pcd)
    # 1. endorsement missing modifiesCoverage / appliesInState  -> EndorsementShape
    e = pcd["MM-CP-E999"]; g.add((e, RDF.type, pc.Endorsement)); g.add((e, pc.formNumber, Literal("MM-CP-E999")))
    g.add((e, pc.editionDate, Literal("01/2025"))); g.add((e, pc.modifiesForm, pcd["MM-CP-0010"]))
    # 2. NY policy on MM-CP-0010 (Pending in NY) + class code 0511 + TIV above UW Level 1 authority -> R06, R05, R10
    p = pcd["policy/POL-NY-0099"]; g.add((p, RDF.type, pc.Policy)); g.add((p, pc.policyNumber, Literal("POL-NY-0099")))
    g.add((p, pc.inState, pcd.NY)); g.add((p, pc.hasForm, pcd["MM-CP-0010"])); g.add((p, pc.hasClassCode, pcd["CC-0511"]))
    g.add((p, pc.totalInsuredValue, Literal("9000000", datatype=XSD.decimal))); g.add((p, pc.boundBy, pcd["uw/jane-doe"]))
    l = pcd["location/LOC-0099"]; g.add((p, pc.hasLocation, l)); g.add((l, RDF.type, pc.Location)); g.add((l, pc.inState, pcd.NY))
    # 3. FL policy without FL-01, location in FL-T03 without E310, zone VE not scheduled, no acknowledgment -> R07, R08, R09
    p2 = pcd["policy/POL-FL-0002"]; g.add((p2, RDF.type, pc.Policy)); g.add((p2, pc.policyNumber, Literal("POL-FL-0002")))
    g.add((p2, pc.inState, pcd.FL)); g.add((p2, pc.hasForm, pcd["MM-CP-0010"])); g.add((p2, pc.hasForm, pcd["MM-CP-1030"]))
    l2 = pcd["location/LOC-0002"]; g.add((p2, pc.hasLocation, l2)); g.add((l2, RDF.type, pc.Location)); g.add((l2, pc.inState, pcd.FL))
    g.add((l2, pc.inTerritory, pcd["FL-T03"])); g.add((l2, pc.inFloodZone, pcd.VE))
    # 4. claim on POL-FL-0002: flood, not scheduled -> R01 fires (no E101 carve-out); TX claim with 80h notice -> R03
    c = pcd["claim/CLM-0002"]; g.add((c, RDF.type, pc.Claim)); g.add((c, pc.onPolicy, p2)); g.add((c, pc.atLocation, l2))
    g.add((c, pc.causeOfLoss, pcd.Flood)); g.add((c, pc.affectsCoverage, pcd["COV-A"])); g.add((c, pc.noticeDelayHours, Literal(20)))
    p3 = pcd["policy/POL-TX-0003"]; g.add((p3, RDF.type, pc.Policy)); g.add((p3, pc.policyNumber, Literal("POL-TX-0003")))
    g.add((p3, pc.inState, pcd.TX)); g.add((p3, pc.hasForm, pcd["MM-CP-0010"]))
    l3 = pcd["location/LOC-0003"]; g.add((p3, pc.hasLocation, l3)); g.add((l3, RDF.type, pc.Location)); g.add((l3, pc.inState, pcd.TX))
    c3 = pcd["claim/CLM-0003"]; g.add((c3, RDF.type, pc.Claim)); g.add((c3, pc.onPolicy, p3)); g.add((c3, pc.atLocation, l3))
    g.add((c3, pc.causeOfLoss, pcd.Fire)); g.add((c3, pc.noticeDelayHours, Literal(80)))
    return g


def fixed_records(bad):
    g = Graph(); g += bad
    g.add((pcd["MM-CP-E999"], pc.modifiesCoverage, pcd["COV-A"])); g.add((pcd["MM-CP-E999"], pc.appliesInState, pcd.TX))
    p = pcd["policy/POL-NY-0099"]
    g.remove((p, pc.inState, pcd.NY)); g.add((p, pc.inState, pcd.TX))                      # write it in TX instead
    g.remove((p, pc.hasClassCode, pcd["CC-0511"])); g.add((p, pc.hasClassCode, pcd["CC-0745"]))
    g.remove((p, pc.totalInsuredValue, None)); g.add((p, pc.totalInsuredValue, Literal("4500000", datatype=XSD.decimal)))
    g.remove((pcd["location/LOC-0099"], pc.inState, pcd.NY)); g.add((pcd["location/LOC-0099"], pc.inState, pcd.TX))
    p2 = pcd["policy/POL-FL-0002"]
    for e in ("MM-CP-FL-01", "MM-CP-E310", "MM-CP-E101"): g.add((p2, pc.hasEndorsement, e and pcd[e]))
    g.add((pcd["location/LOC-0002"], pc.scheduledUnder, pcd["MM-CP-E101"]))
    g.remove((pcd["claim/CLM-0003"], pc.noticeDelayHours, None)); g.add((pcd["claim/CLM-0003"], pc.noticeDelayHours, Literal(48)))
    return g


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shapes, data = load_shapes(), load_data()
    ok = run(data, shapes, "01_generated_graph")

    bad = bad_records(); bad.serialize(OUT_DIR / "bad_records.ttl", format="turtle")
    ok_bad = run(data + bad, shapes, "02_with_bad_records")

    fixed = fixed_records(bad); fixed.serialize(OUT_DIR / "fixed_records.ttl", format="turtle")
    ok_fixed = run(data + fixed, shapes, "03_after_fix")
    print(f"\nSUMMARY generated={ok}  with_bad_records={ok_bad}  after_fix={ok_fixed}")
