#!/usr/bin/env python3
"""
10_enforce_live_record.py   LAYER 6 - Virtualization & Stream Enforcement (POC simulation)

Production design:  policy admin DB --CDC (Debezium)--> event bus --RML virtualization--> incremental SHACL check of the
                    changed record only --> dispatcher alerts underwriter / adjuster.
POC simulation:     JSON events (what a CDC payload carries) -> tiny mapping to RDF (the RML step) -> POST the record into
                    the GraphDB operational graph. GraphDB's ShaclSail validates ONLY the transaction's changes against the
                    active shape set and rejects the commit if a rule fires -> we parse the report -> route alerts.

Checkpoints: Quote, Bind, Endorsement, FNOL, Renewal. The dispatcher routes by rule owner:
   underwriting rules R05-R10 -> Underwriter ; coverage & claims rules R01-R04, R11-R12 -> Adjuster
Outputs: output/10_alerts/alerts.json , alerts.md
Fallback: if GraphDB is down the same check runs locally with pySHACL (needs the data graph as context).
"""
import json
import re
from datetime import datetime, timezone
from rdflib import Graph, Namespace, Literal, RDF, XSD
from common import OUTPUT, GRAPH_OPS, PC, PCD, ONTOLOGY_TTL, CORE_SHAPES_TTL, COMPILED_SHAPES_DIR, write_json
from graphdb_client import GraphDB

pc, pcd = Namespace(PC), Namespace(PCD)
OUT_DIR = OUTPUT / "10_alerts"
RULE_OWNER = {**{f"R{i:02d}": "Underwriter" for i in range(5, 11)}, **{r: "Adjuster" for r in ("R01", "R02", "R03", "R04", "R11", "R12")}}

# ------------------------------------------------------------------ demo CDC events
EVENTS = [
    {"event": "Bind", "policy": {"policyNumber": "POL-FL-0100", "state": "FL", "forms": ["MM-CP-0010", "MM-CP-1030"],
     "endorsements": [], "classCode": "0745", "tiv": 3200000, "underwriter": "jane-doe",
     "locations": [{"id": "LOC-0100", "state": "FL", "territory": "FL-T03", "floodZone": "AE", "scheduledUnderE101": False,
                    "construction": "CC4", "protectionClass": "PC4"}]},
     "note": "Coastal FL bind with no FL-01, no E310, flood zone AE not scheduled -> expect 3 underwriter alerts"},
    {"event": "FNOL", "claim": {"claimNumber": "CLM-0200", "policyNumber": "POL-FL-0001", "location": "LOC-0200",
     "causeOfLoss": "Flood", "coverage": "COV-A", "noticeDelayHours": 30, "lossDate": "2025-10-05"},
     "newLocation": {"id": "LOC-0200", "state": "FL", "floodZone": "X", "scheduledUnderE101": False},
     "note": "Flood claim at an UNscheduled location on the valid FL policy -> expect adjuster alert (R01 exclusion stands)"},
    {"event": "Bind", "policy": {"policyNumber": "POL-TX-0300", "state": "TX", "forms": ["MM-CP-0010", "MM-CP-1030"],
     "endorsements": ["MM-CP-E310", "MM-CP-E415"], "classCode": "0802", "tiv": 2500000, "underwriter": "jane-doe",
     "locations": [{"id": "LOC-0300", "state": "TX", "territory": "TX-T01", "floodZone": "X", "scheduledUnderE101": False,
                    "construction": "CC2", "protectionClass": "PC3"}]},
     "note": "Clean TX bind -> expect accepted, 0 alerts"},
]


# ------------------------------------------------------------------ the 'RML' step: JSON -> RDF
def event_to_rdf(ev):
    g = Graph(); g.bind("pc", pc); g.bind("pcd", pcd)
    if "policy" in ev:
        p = ev["policy"]; pol = pcd[f"policy/{p['policyNumber']}"]
        g.add((pol, RDF.type, pc.Policy)); g.add((pol, pc.policyNumber, Literal(p["policyNumber"]))); g.add((pol, pc.inState, pcd[p["state"]]))
        for f in p["forms"]: g.add((pol, pc.hasForm, pcd[f]))
        for e in p["endorsements"]: g.add((pol, pc.hasEndorsement, pcd[e]))
        g.add((pol, pc.hasClassCode, pcd[f"CC-{p['classCode']}"])); g.add((pol, pc.totalInsuredValue, Literal(str(p["tiv"]), datatype=XSD.decimal)))
        g.add((pol, pc.boundBy, pcd[f"uw/{p['underwriter']}"]))
        for l in p["locations"]:
            _location(g, l); g.add((pol, pc.hasLocation, pcd[f"location/{l['id']}"]))
    if "newLocation" in ev:
        l = ev["newLocation"]; _location(g, l)
        g.add((pcd[f"policy/{ev['claim']['policyNumber']}"], pc.hasLocation, pcd[f"location/{l['id']}"]))
    if "claim" in ev:
        c = ev["claim"]; clm = pcd[f"claim/{c['claimNumber']}"]
        g.add((clm, RDF.type, pc.Claim)); g.add((clm, pc.onPolicy, pcd[f"policy/{c['policyNumber']}"]))
        g.add((clm, pc.atLocation, pcd[f"location/{c['location']}"])); g.add((clm, pc.causeOfLoss, pcd[c["causeOfLoss"]]))
        g.add((clm, pc.affectsCoverage, pcd[c["coverage"]])); g.add((clm, pc.noticeDelayHours, Literal(int(c["noticeDelayHours"]))))
        g.add((clm, pc.lossDate, Literal(c["lossDate"], datatype=XSD.date))); g.add((clm, pc.claimStatus, Literal("open")))
    return g


def _location(g, l):
    loc = pcd[f"location/{l['id']}"]
    g.add((loc, RDF.type, pc.Location)); g.add((loc, pc.inState, pcd[l["state"]]))
    if l.get("territory"): g.add((loc, pc.inTerritory, pcd[l["territory"]]))
    if l.get("floodZone"): g.add((loc, pc.inFloodZone, pcd[l["floodZone"]]))
    if l.get("scheduledUnderE101"): g.add((loc, pc.scheduledUnder, pcd["MM-CP-E101"]))
    if l.get("construction"): g.add((loc, pc.hasConstructionClass, pcd[l["construction"]]))
    if l.get("protectionClass"): g.add((loc, pc.hasProtectionClass, pcd[l["protectionClass"]]))
    g.add((loc, pc.vacantDays, Literal(0)))


# ------------------------------------------------------------------ validation (GraphDB commit, or pySHACL fallback)
def parse_graphdb_report(body):
    """GraphDB returns the SHACL report as N-Triples inside the error body. Group by result node."""
    results = {}
    for s, p, o in re.findall(r'^(_:\S+) <([^>]+)> (.+) \.$', body, re.M):
        results.setdefault(s, {})[p.split("#")[-1].split("/")[-1]] = o.strip('"').split('"^^')[0].strip("<>")
    out = []
    for r in results.values():
        if r.get("type", "").endswith("ValidationResult"):
            shape = r.get("sourceShape", "")
            out.append({"shape": shape.split("/")[-1], "focus": r.get("focusNode", "").replace(PCD, ""),
                        "message": r.get("resultMessage", ""), "value": r.get("value", "").replace(PCD, "")})
    return out


def validate_graphdb(db, g):
    code, body = db.add_turtle_text(g.serialize(format="turtle"), GRAPH_OPS)
    if code in (200, 204):
        return "accepted", []
    return "rejected", parse_graphdb_report(body)


def validate_local(g):
    from pyshacl import validate
    from rdflib.namespace import SH
    data = Graph()
    for f in ("data.ttl", "operational.ttl"):
        data.parse(OUTPUT / "06_rdf" / f, format="turtle")
    data += g
    shapes = Graph().parse(CORE_SHAPES_TTL, format="turtle"); shapes.parse(COMPILED_SHAPES_DIR / "active_shapes.ttl", format="turtle")
    conforms, rep, _ = validate(data, shacl_graph=shapes, ont_graph=Graph().parse(ONTOLOGY_TTL, format="turtle"), inference="rdfs", advanced=True)
    out = [{"shape": str(rep.value(r, SH.sourceShape)).split("/")[-1], "focus": str(rep.value(r, SH.focusNode)).replace(PCD, ""),
            "message": str(rep.value(r, SH.resultMessage)), "value": str(rep.value(r, SH.value) or "").replace(PCD, "")}
           for r in rep.subjects(RDF.type, SH.ValidationResult)]
    return ("accepted" if conforms else "rejected"), out


# ------------------------------------------------------------------ dispatcher
def dispatch(ev, violations):
    alerts = []
    for v in violations:
        rule = v["shape"] if re.fullmatch(r"R\d{2}", v["shape"]) else None
        owner = RULE_OWNER.get(rule, "Data steward")       # core (structural) shapes go to the data steward
        alerts.append({"checkpoint": ev["event"], "to": owner, "rule": rule or v["shape"], "record": v["focus"],
                       "offending_value": v["value"], "message": v["message"], "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return alerts


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = GraphDB(); online = db.alive()
    print(f"validation engine: {'GraphDB ShaclSail (commit-time)' if online else 'pySHACL (local fallback)'}")
    log, md = [], ["# Layer 6 enforcement log\n"]
    for ev in EVENTS:
        g = event_to_rdf(ev)
        status, violations = validate_graphdb(db, g) if online else validate_local(g)
        alerts = dispatch(ev, violations)
        rec = {"event": ev["event"], "note": ev["note"], "triples_in_change": len(g), "status": status, "alerts": alerts}
        log.append(rec)
        key = ev.get("policy", ev.get("claim"))["policyNumber" if "policy" in ev else "claimNumber"]
        print(f"\n[{ev['event']}] {key}: {len(g)} triples -> {status.upper()} ({len(alerts)} alerts)   # {ev['note']}")
        md.append(f"## {ev['event']} {key} -> {status} ({len(alerts)} alerts)\n{ev['note']}\n")
        for a in alerts:
            print(f"   -> {a['to']:<12} {a['rule']:<10} {a['record']:<22} {a['message'][:95]}")
            md.append(f"- to **{a['to']}** | rule {a['rule']} | record `{a['record']}` | {a['message']}")
        if status == "accepted" and online:
            # keep the repository reproducible: remove the accepted demo record again. All subjects in ONE transaction -
            # ShaclSail validates deletes too, and removing a Location before its Policy would violate sh:class pc:Location.
            vals = " ".join(f"<{s}>" for s in set(str(s) for s in g.subjects()))
            code, body = db.update(f"DELETE {{ GRAPH <{GRAPH_OPS}> {{ ?s ?p ?o }} }} WHERE {{ VALUES ?s {{ {vals} }} GRAPH <{GRAPH_OPS}> {{ ?s ?p ?o }} }}")
            print(f"   cleanup of accepted record -> HTTP {code}")
    write_json(OUT_DIR / "alerts.json", log)
    (OUT_DIR / "alerts.md").write_text("\n".join(md))
