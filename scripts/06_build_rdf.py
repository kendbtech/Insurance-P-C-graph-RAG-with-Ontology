#!/usr/bin/env python3
"""
06_build_rdf.py   RDF GENERATION  (knowledge binding: extraction output -> triples using the ontology)

Inputs : output/03_grounded/*.json (clause tree + tags + grounding), output/05_active_rules/active_rules.json
Outputs: output/06_rdf/data.ttl         entities & relations (forms, endorsements, filings, territories, factors...)
         output/06_rdf/clauses.ttl      one pc:Clause per clause (+ exceptions), text chunks, PROV links
         output/06_rdf/rules.ttl        pc:Rule nodes (DSL, status, compiledFrom, overriddenBy)
         output/06_rdf/operational.ttl  small set of VALID policy / location / claim records for the demo
         output/06_rdf/all.trig         everything in named graphs (used by the local pySHACL gate)

Mapping approach: plain Python + rdflib. Each mapping function below is the equivalent of one RML
TriplesMap (logical source = a Layer-1 table or clause list; subject template; predicate-object maps).
RML/RMLMapper is the standards-based alternative when the sources are relational tables (see docs).
"""
import re
from datetime import date
from rdflib import Graph, Dataset, Namespace, URIRef, Literal, RDF, RDFS, XSD, PROV
from common import (OUTPUT, DOCS, ONTOLOGY_TTL, PC, PCD, GRAPH_ONTOLOGY, GRAPH_DATA, GRAPH_CLAUSES, GRAPH_RULES,
                    GRAPH_OPS, read_json)

IN_DIR = OUTPUT / "03_grounded"
RULES = OUTPUT / "05_active_rules" / "active_rules.json"
OUT_DIR = OUTPUT / "06_rdf"
pc, pcd = Namespace(PC), Namespace(PCD)
SHAPE = Namespace("https://example.org/pc/shape/")


def clause_iri(clause_id):
    return pcd[clause_id.replace("#", "_").replace("/", "_")]


def bind(g):
    g.bind("pc", pc); g.bind("pcd", pcd); g.bind("prov", PROV); g.bind("shape", SHAPE)
    return g


def mdy(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
    return Literal(date(int(m.group(3)), int(m.group(1)), int(m.group(2)))) if m else None


# ------------------------------------------------------------------ documents, forms, endorsements
FORM_TYPES = {"MM-CP-0010": pc.PolicyForm, "MM-CP-1030": pc.PolicyForm, "MM-CP-E101": pc.Endorsement,
              "MM-CP-E205": pc.Endorsement, "MM-CP-E310": pc.Endorsement, "MM-CP-E415": pc.Endorsement,
              "MM-CP-FL-01": pc.StateAmendatoryEndorsement}
DOC_TYPES = {"PolicyForm": pc.PolicyForm, "EndorsementPackage": pc.Document, "UnderwritingGuideline": pc.UnderwritingGuideline,
             "RateManual": pc.RateManual, "ClaimsManual": pc.ClaimsManual, "StateFilingRegister": pc.Document}
EXCLUSION_PERILS = {"EXCL-FLD": ["Flood", "Water"], "EXCL-EQ": ["EarthMovement"], "EXCL-MOLD": ["Mold"],
                    "EXCL-WAR": [], "EXCL-WEAR": []}
STATUS = {"Approved": pcd.Approved, "Pending": pcd.Pending, "Not filed": pcd.NotFiled}


def map_documents(g, trees):
    for doc_id, t in trees.items():
        d = pcd[doc_id]
        g.add((d, RDF.type, DOC_TYPES[t["doc_type"]]))
        g.add((d, pc.documentId, Literal(doc_id)))
        g.add((d, RDFS.label, Literal(t["title"])))
        for k, v in t["metadata"].items():
            if k in ("Edition Date", "Edition"): g.add((d, pc.editionDate, Literal(v)))
            if k == "Version": g.add((d, pc.versionLabel, Literal(v)))
            if k == "Effective Date" and mdy(v): g.add((d, pc.effectiveDate, mdy(v)))
            if k in ("States In Scope", "Approved States", "State Availability"):
                for st in re.findall(r"\b(FL|TX|NY)\b", v):
                    g.add((d, pc.appliesInState, pcd[st]))
        # document -> document references (any form / doc id mentioned anywhere in the document)
        for s in t["sections"]:
            for c in s["clauses"]:
                for kind in ("form", "document", "filing"):
                    for ref in c.get("ids", {}).get(kind, []):
                        if ref != doc_id:
                            g.add((d, pc.references, pcd[ref]))
    for f, cls in FORM_TYPES.items():
        g.add((pcd[f], RDF.type, cls)); g.add((pcd[f], pc.formNumber, Literal(f)))
    g.add((pcd["MM-CP-1030"], RDFS.label, Literal("Causes of Loss - Special Form")))
    g.add((pcd["MM-CP-1030"], pc.editionDate, Literal("01/2025")))
    g.add((pcd["MM-CP-0010"], pc.references, pcd["MM-CP-1030"]))
    for ex, perils in EXCLUSION_PERILS.items():
        g.add((pcd[ex], RDF.type, pc.Exclusion)); g.add((pcd[ex], pc.exclusionCode, Literal(ex)))
        g.add((pcd["MM-CP-1030"], pc.hasExclusion, pcd[ex])); g.add((pcd["MM-CP-0010"], pc.hasExclusion, pcd[ex]))
        for p in perils:
            g.add((pcd[ex], pc.excludesPeril, pcd[p]))
    g.add((pcd["EXCL-FLD"], RDFS.label, Literal("Water (flood, surface water, overflow)")))
    g.add((pcd["EXCL-EQ"], RDFS.label, Literal("Earth Movement")))
    g.add((pcd["EXCL-WAR"], RDFS.label, Literal("War and Military Action")))
    g.add((pcd["EXCL-MOLD"], RDFS.label, Literal("Fungus, Wet Rot and Bacteria")))
    g.add((pcd["EXCL-WEAR"], RDFS.label, Literal("Wear and Tear")))


def map_endorsement_matrix(g, table):
    """Table 'ENDORSEMENT AVAILABILITY MATRIX' -> modifiesCoverage / modifiesForm / editionDate / appliesInState"""
    hdr = table["header"]
    for row in table["rows"]:
        r = dict(zip(hdr, row))
        e = pcd[r["Endorsement"]]
        g.add((e, pc.editionDate, Literal(r["Edition"])))
        for cov in re.findall(r"COV-[A-D]", r["Modifies Coverages"]):
            g.add((e, pc.modifiesCoverage, pcd[cov]))
        for f in re.findall(r"MM-CP-\d{4}", r["Modifies Forms"]):
            g.add((e, pc.modifiesForm, pcd[f]))
        for st in ("FL", "TX", "NY"):
            if r.get(st, "").startswith("Approved"):
                g.add((e, pc.appliesInState, pcd[st]))
                if "mandatory" in r[st].lower():
                    g.add((e, pc.mandatoryIn, pcd[st]))
    titles = {"MM-CP-E101": "Flood Coverage Endorsement - Scheduled Locations", "MM-CP-E205": "Equipment Breakdown Endorsement",
              "MM-CP-E310": "Windstorm or Hail Percentage Deductible", "MM-CP-E415": "Protective Safeguards Endorsement",
              "MM-CP-FL-01": "Florida Amendatory Endorsement"}
    for k, v in titles.items():
        g.add((pcd[k], RDFS.label, Literal(v)))
    # text-derived relations (from clauses 1.2 / 2.2): E101 removes EXCL-FLD and restores Flood; E205 restores breakdown
    g.add((pcd["MM-CP-E101"], pc.removesExclusion, pcd["EXCL-FLD"])); g.add((pcd["MM-CP-E101"], pc.restoresPeril, pcd.Flood))
    g.add((pcd["MM-CP-E101"], pc.sublimitAmount, Literal(250000, datatype=XSD.decimal)))
    g.add((pcd["MM-CP-E101"], pc.deductiblePercent, Literal(5, datatype=XSD.decimal)))
    g.add((pcd["MM-CP-E101"], pc.deductibleMinimum, Literal(25000, datatype=XSD.decimal)))
    g.add((pcd["MM-CP-E205"], pc.restoresPeril, pcd.MechanicalBreakdown))
    g.add((pcd["MM-CP-E205"], pc.sublimitAmount, Literal(100000, datatype=XSD.decimal)))
    g.add((pcd["MM-CP-E310"], pc.mandatoryIn, pcd["FL-T03"])); g.add((pcd["MM-CP-E310"], pc.mandatoryIn, pcd["TX-T01"]))


def map_filings(g, tree):
    """FILING sections -> pc:StateFiling + one pc:FormApproval per table row"""
    for s in tree["sections"]:
        m = re.match(r"FILING \d+ - (\w+) \((FL|TX|NY)\) - (MM-\w\w-2025-\d{4})", s["title"])
        if not m:
            continue
        _, st, fno = m.groups()
        f = pcd[fno]
        g.add((f, RDF.type, pc.StateFiling)); g.add((f, pc.filingNumber, Literal(fno)))
        g.add((f, pc.appliesInState, pcd[st])); g.add((f, RDFS.label, Literal(f"{st} form and rate filing {fno}")))
        text = " ".join(c["text"] for c in s["clauses"])
        tm = re.search(r"Tracking number (MMIC-\d+)", text)
        if tm: g.add((f, pc.trackingNumber, Literal(tm.group(1))))
        am = re.search(r"Approved (\d{2}/\d{2}/\d{4})", text)
        if am: g.add((f, pc.approvalDate, mdy(am.group(1))))
        em = re.search(r"Effective (\d{2}/\d{2}/\d{4})", text)
        if em: g.add((f, pc.effectiveDate, mdy(em.group(1))))
        for tb in s["tables"]:
            hdr = tb["header"]
            if hdr[:2] != ["Form", "Edition"]:
                continue
            for row in tb["rows"]:
                r = dict(zip(hdr, row))
                ap = pcd[f"approval/{fno}/{r['Form']}"]
                g.add((f, pc.hasFormApproval, ap)); g.add((ap, RDF.type, pc.FormApproval))
                g.add((ap, pc.approvalOfForm, pcd[r["Form"]])); g.add((ap, pc.approvalInState, pcd[st]))
                g.add((ap, pc.approvalStatus, STATUS[r["Status"]])); g.add((ap, pc.editionDate, Literal(r["Edition"])))
                g.add((ap, RDFS.comment, Literal(r.get("Action", ""))))
                # replaced editions -> supersedes
                sm = re.search(r"Replaces Ed\. (\d{2}/\d{4})", r.get("Action", ""))
                if sm:
                    old = pcd[f"{r['Form']}-Ed-{sm.group(1).replace('/', '-')}"]
                    g.add((old, RDF.type, FORM_TYPES.get(r["Form"], pc.Form))); g.add((old, pc.formNumber, Literal(r["Form"])))
                    g.add((old, pc.editionDate, Literal(sm.group(1)))); g.add((pcd[r["Form"]], pc.supersedes, old))


def map_rate_manual(g, tree):
    for s in tree["sections"]:
        for tb in s["tables"]:
            hdr = tb["header"]
            if hdr[0] == "Territory Code":
                for row in tb["rows"]:
                    r = dict(zip(hdr, row)); t = pcd[r["Territory Code"]]
                    g.add((t, RDF.type, pc.Territory)); g.add((t, pc.territoryCode, Literal(r["Territory Code"])))
                    g.add((t, pc.territoryState, pcd[r["State"]])); g.add((t, RDFS.label, Literal(f"{r['Territory Code']} {r['Description']}")))
                    g.add((t, pc.factorValue, Literal(float(r["Factor"]), datatype=XSD.decimal)))
                    if r.get("Notes"): g.add((t, RDFS.comment, Literal(r["Notes"])))
            elif hdr[0] == "Construction Class":
                for row in tb["rows"]:
                    r = dict(zip(hdr, row)); c = pcd[r["Construction Class"]]
                    g.add((c, RDF.type, pc.ConstructionClass)); g.add((c, RDFS.label, Literal(f"{r['Construction Class']} {r['Description']}")))
                    g.add((c, pc.factorValue, Literal(float(r["Base Rate COV-A"]), datatype=XSD.decimal)))
                    g.add((c, RDFS.comment, Literal(f"Base rate per $100: COV-A {r['Base Rate COV-A']}, COV-B {r['Base Rate COV-B']}")))
            elif hdr[0] == "Factor Code":
                for row in tb["rows"]:
                    r = dict(zip(hdr, row)); f = pcd[r["Factor Code"]]
                    g.add((f, RDF.type, pc.RatingFactor)); g.add((f, pc.factorCode, Literal(r["Factor Code"])))
                    g.add((f, RDFS.label, Literal(r["Safeguard"]))); g.add((f, pc.factorValue, Literal(float(r["Factor"]), datatype=XSD.decimal)))
                    for e in re.findall(r"MM-CP-E\d{3}", r["Required Endorsement"]):
                        g.add((f, pc.factorRequiresEndorsement, pcd[e]))
            elif hdr[0] == "Protection Class":
                for i, col in enumerate(hdr[1:], start=1):
                    for pcode in re.findall(r"PC\d+", col) or []:
                        pass
                # PC1..PC10 individuals with band factor
                bands = dict(zip(hdr[1:], tb["rows"][0][1:]))
                for band, val in bands.items():
                    lo, hi = re.findall(r"PC(\d+)", band) + ([re.findall(r"PC(\d+)", band)[0]] if len(re.findall(r"PC(\d+)", band)) == 1 else [])
                    for n in range(int(lo), int(hi) + 1):
                        p = pcd[f"PC{n}"]; g.add((p, RDF.type, pc.ProtectionClass)); g.add((p, RDFS.label, Literal(f"Protection Class {n}")))
                        g.add((p, pc.factorValue, Literal(float(re.match(r"[\d.]+", val).group(0)), datatype=XSD.decimal)))
            elif hdr[0] == "Endorsement" and "Rating Basis" in hdr:
                for row in tb["rows"]:
                    r = dict(zip(hdr, row))
                    e = re.search(r"MM-CP-[A-Z0-9-]+", r["Endorsement"]).group(0)
                    g.add((pcd[e], RDFS.comment, Literal(f"Rating: {r['Rating Basis']}; {r['Rate or Factor']}")))


def map_uw_tables(g, tree):
    for s in tree["sections"]:
        for tb in s["tables"]:
            hdr = tb["header"]
            if hdr[0] == "Class Code":
                for row in tb["rows"]:
                    r = dict(zip(hdr, row)); c = pcd[f"CC-{r['Class Code']}"]
                    g.add((c, RDF.type, pc.ClassCode)); g.add((c, pc.classCode, Literal(r["Class Code"])))
                    g.add((c, RDFS.label, Literal(r["Description"]))); g.add((c, pc.classCodeStatus, pcd[r["Status"]]))
                    g.add((c, RDFS.comment, Literal(r["Reason"])))
            elif hdr[0] == "Authority Level":
                for row in tb["rows"]:
                    r = dict(zip(hdr, row)); lvl = pcd["authority/" + re.sub(r"[^A-Za-z0-9]+", "-", r["Authority Level"]).strip("-")]
                    g.add((lvl, RDF.type, pc.AuthorityLevel)); g.add((lvl, RDFS.label, Literal(r["Authority Level"])))
                    m = re.search(r"\$([\d,]+)", r["Maximum TIV Per Location"])
                    if m and not r["Maximum TIV Per Location"].startswith("Over"):
                        g.add((lvl, pc.authorityMaxTIV, Literal(float(m.group(1).replace(",", "")), datatype=XSD.decimal)))


# ------------------------------------------------------------------ clauses, chunks, provenance
def map_clauses(g, trees):
    for doc_id, t in trees.items():
        d = pcd[doc_id]
        for s in t["sections"]:
            for c in s["clauses"]:
                ci = clause_iri(c["clause_id"])
                g.add((ci, RDF.type, pc.Clause)); g.add((ci, RDF.type, pc.Chunk))
                g.add((ci, pc.sourceDocument, d)); g.add((ci, PROV.wasDerivedFrom, d))
                g.add((ci, pc.sectionRef, Literal(f"{s['title']} / {c['ref']}")))
                g.add((ci, pc.pageNumber, Literal(c["page"])))
                g.add((ci, pc.clauseText, Literal(c["full_text"])))
                g.add((ci, pc.chunkText, Literal(f"[{doc_id} {s['title']} {c['ref']} p.{c['page']}] {c['full_text']}")))
                g.add((ci, RDFS.label, Literal(f"{doc_id} {c['ref']}")))
                k = c["classification"]
                g.add((ci, pc.deonticType, pcd[k["deontic"]]))
                g.add((ci, pc.confidence, Literal(k["confidence"], datatype=XSD.decimal)))
                g.add((ci, pc.classifierRoute, Literal(k["route"])))
                for h in c["grounding"]["hard"]:
                    g.add((ci, pc.mentions, URIRef(h["iri"])))
                for tterm in c["grounding"]["soft_top3"]:
                    g.add((ci, pc.groundedTerm, URIRef(tterm["iri"])))
                for x in c["exceptions"]:
                    xi = clause_iri(x["clause_id"])
                    g.add((xi, RDF.type, pc.Clause)); g.add((xi, pc.exceptionTo, ci)); g.add((xi, pc.clauseText, Literal(x["text"])))
                    g.add((xi, pc.sourceDocument, d)); g.add((xi, pc.pageNumber, Literal(c["page"])))
                    g.add((xi, pc.sectionRef, Literal(f"{s['title']} / {c['ref']} (exception)")))
            for tb in s["tables"]:
                ti = clause_iri(tb["table_id"])
                flat = " | ".join(" ; ".join(f"{h}: {v}" for h, v in zip(tb["header"], row)) for row in tb["rows"])
                g.add((ti, RDF.type, pc.Chunk)); g.add((ti, PROV.wasDerivedFrom, d)); g.add((ti, pc.sourceDocument, d))
                g.add((ti, pc.pageNumber, Literal(tb["page"]))); g.add((ti, pc.sectionRef, Literal(f"{s['title']} / table")))
                g.add((ti, pc.chunkText, Literal(f"[{doc_id} {s['title']} table p.{tb['page']}] {flat}")))
                g.add((ti, RDFS.label, Literal(f"{doc_id} table {' / '.join(tb['header'][:3])}")))


def map_rules(g):
    for r in read_json(RULES)["rules"]:
        ri = pcd[f"rule/{r['rule_id']}"]
        g.add((ri, RDF.type, pc.Rule)); g.add((ri, RDFS.label, Literal(r["rule_id"])))
        g.add((ri, pc.ruleDSL, Literal(r["dsl"]))); g.add((ri, pc.ruleStatus, Literal(r["status"])))
        g.add((ri, pc.compiledFrom, clause_iri(r["source_clause"]))); g.add((ri, pc.hasShape, SHAPE[r["rule_id"]]))
        g.add((ri, RDFS.comment, Literal(r["message"])))
        for w in r.get("overridden_by", []):
            g.add((ri, pc.overriddenBy, pcd[f"rule/{w}"]))


# ------------------------------------------------------------------ operational sample records (valid)
def operational(g):
    uw = pcd["uw/jane-doe"]; g.add((uw, RDF.type, pc.Underwriter)); g.add((uw, RDFS.label, Literal("J. Doe (UW Level 1)")))
    g.add((uw, pc.hasAuthorityLevel, pcd["authority/UW-Level-1-Associate"]))
    pol = pcd["policy/POL-FL-0001"]
    g.add((pol, RDF.type, pc.Policy)); g.add((pol, pc.policyNumber, Literal("POL-FL-0001"))); g.add((pol, pc.inState, pcd.FL))
    for f in ("MM-CP-0010", "MM-CP-1030"): g.add((pol, pc.hasForm, pcd[f]))
    for e in ("MM-CP-FL-01", "MM-CP-E310", "MM-CP-E101"): g.add((pol, pc.hasEndorsement, pcd[e]))
    g.add((pol, pc.hasClassCode, pcd["CC-0745"])); g.add((pol, pc.totalInsuredValue, Literal(4000000, datatype=XSD.decimal)))
    g.add((pol, pc.boundBy, uw)); g.add((pol, pc.effectiveDate, Literal(date(2025, 9, 1))))
    loc = pcd["location/LOC-0001"]
    g.add((pol, pc.hasLocation, loc)); g.add((loc, RDF.type, pc.Location)); g.add((loc, RDFS.label, Literal("100 Bayfront Ave, Tampa FL")))
    g.add((loc, pc.inState, pcd.FL)); g.add((loc, pc.inTerritory, pcd["FL-T03"])); g.add((loc, pc.inFloodZone, pcd.AE))
    g.add((loc, pc.scheduledUnder, pcd["MM-CP-E101"])); g.add((loc, pc.hasConstructionClass, pcd.CC4))
    g.add((loc, pc.hasProtectionClass, pcd.PC4)); g.add((loc, pc.vacantDays, Literal(0)))
    for z in ("A", "AE", "V", "VE", "X"):
        g.add((pcd[z], RDF.type, pc.FloodZone)); g.add((pcd[z], RDFS.label, Literal(f"FEMA zone {z}")))
    clm = pcd["claim/CLM-0001"]
    g.add((clm, RDF.type, pc.Claim)); g.add((clm, pc.onPolicy, pol)); g.add((clm, pc.atLocation, loc))
    g.add((clm, pc.causeOfLoss, pcd.Flood)); g.add((clm, pc.affectsCoverage, pcd["COV-A"]))
    g.add((clm, pc.lossDate, Literal(date(2025, 10, 2)))); g.add((clm, pc.noticeDelayHours, Literal(100)))
    g.add((clm, pc.acknowledgmentDelayDays, Literal(10))); g.add((clm, pc.claimStatus, Literal("open")))


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trees = {d: read_json(IN_DIR / f"{d}.json") for d in DOCS}

    data, clauses, rules, ops = bind(Graph()), bind(Graph()), bind(Graph()), bind(Graph())
    map_documents(data, trees)
    for s in trees["MM-CP-E-SERIES"]["sections"]:
        for tb in s["tables"]:
            if tb["header"][0] == "Endorsement" and "Modifies Coverages" in tb["header"]:
                map_endorsement_matrix(data, tb)
    map_filings(data, trees["MM-FILINGS-CP-2025"])
    map_rate_manual(data, trees["MM-RM-CP-2025"])
    map_uw_tables(data, trees["MM-UW-CP-2025"])
    map_clauses(clauses, trees)
    map_rules(rules)
    operational(ops)

    for name, g in [("data", data), ("clauses", clauses), ("rules", rules), ("operational", ops)]:
        g.serialize(OUT_DIR / f"{name}.ttl", format="turtle")
        print(f"{name}.ttl: {len(g)} triples")

    ds = Dataset()
    ds.graph(URIRef(GRAPH_ONTOLOGY)).parse(ONTOLOGY_TTL, format="turtle")
    for name, iri, g in [("data", GRAPH_DATA, data), ("clauses", GRAPH_CLAUSES, clauses), ("rules", GRAPH_RULES, rules), ("operational", GRAPH_OPS, ops)]:
        ds.graph(URIRef(iri)).__iadd__(g)
    ds.serialize(OUT_DIR / "all.trig", format="trig")
    print("all.trig:", sum(len(gg) for gg in ds.graphs()), "triples in", len(list(ds.graphs())), "graphs")
