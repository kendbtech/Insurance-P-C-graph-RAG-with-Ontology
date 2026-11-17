# P&C Graph RAG on Graphwise GraphDB: a six-layer POC, explained and built

Audience: a junior engineer who knows Python and some SQL, and is new to RDF, SHACL and graph RAG.
Scope: proof of concept. Everything favors clarity and reproducibility over performance, HA or security.
All data is synthetic (fictional carrier "Meridian Mutual Insurance Company"; forms, states, filings and people are invented).

What you get in the project folder `pc-graphrag-poc/`:

| Piece | Where | Status |
|---|---|---|
| Six synthetic source PDFs (2-3 pages each) + generator | `sources/`, `scripts/00_generate_source_pdfs.py` | generated and parsed |
| Layer 1-5 pipeline as standalone scripts | `scripts/01..05` | run end to end, outputs in `output/` |
| P&C ontology (OWL/RDFS + SKOS) | `ontology/pc_ontology.ttl` | 35 classes, individuals for coverages, perils, states |
| Core SHACL shapes + 12 compiled rule shapes | `shapes/` | validated locally (pySHACL) and in GraphDB (ShaclSail) |
| GraphDB repository build, 12 SPARQL queries | `scripts/08`, `queries/` | run live against GraphDB 10.8.11 Free |
| Graph RAG (SPARQL + vector + LLM/offline) | `scripts/09_graph_rag.py` | 3 questions answered with citations |
| Layer 6 stream-enforcement simulation | `scripts/10_enforce_live_record.py` | 3 events, alerts routed |
| Test plan as 44 assertions | `scripts/11_run_tests.py` | 44 passed, 0 failed |

Sections follow the three tasks: Task 1 explains the layers, Task 2 describes the documents, Task 3 walks through the build.

---

## Vocabulary you will need

- RDF triple: one fact as `subject predicate object`, for example `pcd:MM-CP-E101 pc:modifiesCoverage pcd:COV-A`. A graph is a set of triples. IRIs (web-style identifiers) name the things; literals hold strings, numbers and dates.
- Turtle (`.ttl`): the human-readable text format for RDF. TriG adds named graphs (a label on a group of triples, used here to separate ontology / data / clauses / rules / operational records).
- Ontology (OWL/RDFS): the schema of the graph: classes (`pc:Endorsement`), properties (`pc:modifiesCoverage`), hierarchies (`pc:Endorsement rdfs:subClassOf pc:Form`). Inference uses these to derive triples you never typed.
- SKOS: a small vocabulary for labels and "broader than" links. We use `skos:altLabel` for synonyms and `skos:broader` to say Flood is a kind of Water.
- SPARQL: the query language for RDF. Think SQL where every `WHERE` line is a triple pattern and variables start with `?`.
- SHACL: a W3C language for constraints over RDF ("every Endorsement must have at least one `modifiesCoverage`"). A shape targets a class and lists property constraints; a validation report lists each violation with the offending node, path and message. SHACL-SPARQL lets a shape express a condition as a SPARQL query.
- Deontic type: whether a clause is an obligation (must), a permission (may / we will pay) or a prohibition (must not / we will not pay).
- Named graph / context: GraphDB stores each triple with a fourth element, the graph IRI. We use five graphs plus the reserved shapes graph.
- RDF4J: the Java framework GraphDB is built on. Its REST protocol (`/repositories/{id}/statements`, `/repositories/{id}` for queries) is what our scripts call; nothing proprietary is needed.
- ShaclSail: RDF4J's SHACL engine, which GraphDB exposes as a repository option. Shapes live in the reserved graph `http://rdf4j.org/schema/rdf4j#SHACLShapeGraph`, and every commit is validated against them; a failing commit is rolled back and the HTTP response carries the report ([GraphDB SHACL validation docs](https://graphdb.ontotext.com/documentation/11.5/shacl-validation.html)).

---

# Task 1: the six-layer design, layer by layer

The six layers come from your reference deck. The pattern that runs through all of them: a language model is used only where language must be understood, and everything after that is deterministic code that can be tested, versioned and explained.

```
PDFs ──L1 Hierarchical Perception──> clause tree (with exceptions, tables)
     ──L2 Confidence-Routed Classification──> clause + deontic label + confidence
     ──L3 Dynamic Ontology Grounding──> clause + top-3 ontology terms + identifiers
     ──L4 Formal Logic Compiler──> typed rule JSON ──> DSL ──> AST ──> SHACL shape (one per clause)
     ──L5 Normative Conflict Reasoner──> conflict-free ACTIVE shape set (losers scoped, decisions logged)
     ──L6 Virtualization & Stream Enforcement──> changed record validated at Quote / Bind / Endorsement / FNOL / Renewal ──> alerts
```

## Layer 1: Hierarchical Perception

Purpose. Turn a PDF into a tree of clauses that keeps the document's structure: section, clause, sub-clause, and above all the exceptions that modify a clause ("except when...", "unless..."). It solves the problem that flat text chunks lose the relationship between a rule and its carve-out, which in insurance is the whole point of the sentence.

Inputs, outputs, components. Input: PDF files. Output: one JSON per document with `sections -> clauses -> exceptions` plus tables lifted as structured rows. Components: a layout-aware parser (production: Docling or Marker; the POC uses pdfplumber, which gives words with coordinates and detects ruled tables), a clause splitter that only splits on a clause number that follows a sentence end, an exception extractor that keeps the exception as a child node while the parent keeps the full sentence, and a rule-based linguistic gatekeeper that drops preambles, definition headers, marketing text and empty headings.

Connections. Below it is the raw document. Above it, Layer 2 reads `clause.text` to classify and Layer 3 reads `clause.ids` (identifiers found by regex) to ground. Every later layer carries the `clause_id` (`MM-CP-0010#SECTION-E/E.3`) so a shape or an answer can always be traced back to page and section.

Insurance example. Endorsement clause 4.2 of MM-CP-E415: "You must notify us within 48 hours if any listed protective safeguard is impaired or out of service, except when the impairment is due to ordinary maintenance that is completed within 24 hours." Layer 1 produces a clause node with the full sentence and one child `4.2/x1` holding "except when the impairment is due to ordinary maintenance that is completed within 24 hours." The parent is still a complete sentence (so Layer 2 can classify it); the child is still linked (`exception_to`), so Layer 4 can compile it as an `UNLESS` condition rather than lose it.

Common mistakes.
- Fixed-size chunking (every 500 tokens) splits exceptions from their rule. Chunk at clause boundaries.
- Splitting on any "1.2" pattern breaks on "within 1.2 miles" or "$1.2 million". Require a sentence end before the number.
- Dropping tables, or flattening them into prose. Tables hold the entity data (filing status, territory factors); lift them as rows.
- Gatekeeper that is too aggressive: dropping "Definitions" wholesale removes defined terms that Layer 3 needs. Drop definition headers, keep definition bodies if they carry rules.

## Layer 2: Confidence-Routed Classification

Purpose. Tag each clause as Obligation, Permission or Prohibition with a confidence, and spend expensive adjudication only where the cheap classifier is unsure. It solves cost and consistency: a small local model handles the clear 70 percent, a strict second pass handles the ambiguous band.

Inputs, outputs, components. Input: clause text. Output: `deontic`, `confidence`, `route`. Components: pass 1 (production: a small fine-tuned local model; the POC uses a weighted lexical scorer that returns the same fields), a gate at 0.60, and a pass 2 adjudicator for the 0.40-0.60 band (production: a strict prompt to a larger model; POC: a "first deontic marker wins" rule, or an LLM when `OPENAI_API_KEY` is set). Below 0.40 the design routes to human review; the POC labels these and leaves the low confidence visible in the graph.

Connections. Takes Layer 1 clauses, adds the label, passes everything to Layer 3 unchanged. Layer 4 uses the label as a sanity check: a rule compiled as PROHIBITION from a clause labelled Permission with confidence 0.34 is a flag for review, not an error.

Insurance example. "E.3 Duties In The Event Of Loss Or Damage. You must see that the following are done ... (b) Give us prompt notice ... in no event later than 72 hours" scores Obligation 7.0, Permission 1.5, confidence 0.82: pass 1 accepts. Clause B.1 "See the applicable Causes of Loss form MM-CP-1030 for exclusions ... apply to Coverages COV-A ... unless an endorsement attached to this policy states otherwise" has no strong marker; pass 1 confidence 0.34 falls through, pass 2 produces Permission with the low confidence kept. In the real pipeline this is exactly the clause a human should see, because it is a pointer clause (it imports exclusions from another form) rather than a rule by itself.

Common mistakes.
- Treating "may" as always Permission: "may not" is a Prohibition, "may cancel" is a Permission for the insurer. Use phrase-level cues, not single words.
- Dropping the confidence after classification. Keep it in the graph; it drives review queues and lets Layer 6 weight alerts.
- Letting pass 2 see pass 1's answer. The adjudicator must be independent or it will just agree.
- Over-fitting the gate. 0.60 is a starting point; tune it against a labelled sample (the test plan checks pass-2 share stays under 40 percent).

## Layer 3: Dynamic Ontology Grounding

Purpose. Link each clause to the ontology: which coverage, peril, form, state, territory, class code does it talk about? It solves the "which Coverage A" problem: the graph must connect clause text to the same IRI that the rate manual and the filing register use, otherwise nothing joins.

Inputs, outputs, components. Input: clause text and the ontology. Output: `grounding.hard` (identifiers found by regex, resolved to IRIs: `COV-A -> pcd:COV-A`) and `grounding.soft_top3` (the three closest ontology terms by embedding similarity). Components: a vector store of ontology terms (label + `skos:altLabel`s, embedded with all-MiniLM-L6-v2; TF-IDF fallback when offline), a regex layer for identifiers, a peril-cue layer ("surface water" -> Flood), and in production a focused prompt that asks a model to pick among the top-3 rather than invent a term.

Connections. Reads Layer 1 identifiers and Layer 2 labels; writes IRIs that Layer 4 must use (the compiler rejects a rule that names an identifier the clause is not grounded to) and that the RDF build turns into `pc:mentions` and `pc:groundedTerm` edges, which Graph RAG later uses for entity-boosted retrieval.

Insurance example. Clause B.1 of MM-CP-0010 is hard-grounded to MM-CP-1030, EXCL-FLD, EXCL-EQ, EXCL-WAR, EXCL-MOLD, EXCL-WEAR, COV-A..D; its soft top-3 are Policy Form, Claim, Exclusion. Clause 1.2 of MM-CP-E101 "Exclusion EXCL-FLD (Water) ... is deleted with respect to the peril of Flood" is grounded to EXCL-FLD and, through the peril cue, to `pcd:Flood`, which the ontology marks `skos:broader pcd:Water`. That one link is what lets Layer 5 see that a Flood grant collides with a Water exclusion.

Common mistakes.
- Letting the model free-type a term ("Flood Coverage") instead of choosing from the ontology. Always constrain to known IRIs; use top-3 plus "none".
- Grounding only with embeddings. Identifiers are exact; regex first, embeddings for the rest.
- Forgetting synonyms. "BPP", "contents" and "stock" all mean Coverage B; put them in `skos:altLabel` so the term index finds them.
- Rebuilding the term index from scratch on every run. Build once per ontology version and store it (the POC writes `_term_index.json`).

## Layer 4: Formal Logic Compiler

Purpose. Convert a grounded clause into an executable constraint, deterministically. The model is used once, to emit a typed JSON rule under a strict schema (constrained decoding). Everything after that is code: JSON -> one-line DSL -> grammar-checked AST -> SHACL shape. It solves the trust problem: you can read, diff and unit-test the rule, and a grammar failure rejects the rule instead of producing a wrong shape.

Inputs, outputs, components. Input: grounded clauses. Output: `rules.json` and `shapes/compiled/R*.ttl`, one SHACL NodeShape per clause. Components: a Pydantic `TypedRule` schema (the JSON schema the LLM must satisfy), a `to_dsl()` serializer, a Lark LALR grammar (EBNF) producing a typed AST, a consistency check that every identifier in the rule is grounded in the clause (or exists elsewhere in the corpus, with a warning), and an rdflib compiler that emits plain SHACL property shapes for simple rules and SHACL-SPARQL constraints for conditional ones.

Connections. Reads Layer 3 output (and the typed rules; in the POC `config/typed_rules_seed.json` stands in for the model, `--llm` switches to a real one). Hands all shapes to Layer 5; the shapes also carry `pc:compiledFrom <clause IRI>` so provenance survives into GraphDB.

Insurance example. UW guideline 4.2 "Every Florida policy must include MM-CP-FL-01" becomes

```
OBLIGATION Policy attach_endorsement Endorsement:MM-CP-FL-01 WHEN Policy.inState = FL SOURCE MM-UW-CP-2025#SECTION-4/4.2
```

and compiles to a shape targeting `pc:Policy` whose SPARQL constraint selects policies in FL that lack `pc:hasEndorsement pcd:MM-CP-FL-01`. The exception from Layer 1 example above would become `UNLESS ...` and compile to a `FILTER NOT EXISTS` block.

Common mistakes.
- Asking the model to write SHACL directly. It will produce plausible, subtly wrong shapes you cannot test. Make it fill a schema; compile the SHACL yourself.
- No grammar step. Without it, a typo in a path (`Policy.state` vs `Policy.inState`) becomes a shape that never fires. The grammar plus the ontology check reject it.
- Many rules in one shape. One shape per clause keeps violations traceable to a page.
- `sh:name` / `sh:description` on node shapes: RDF4J's ShaclSail treats those as property-shape characteristics and rejects the shape ("Shape with multiple types"). Use `rdfs:label` / `rdfs:comment`. This happened live in the POC and is fixed in `rulec.py`.

## Layer 5: Normative Conflict Reasoner

Purpose. Rules from different documents collide: the base form excludes flood, the endorsement grants it; the base form says notify within 72 hours, the Florida amendatory says 14 days. Layer 5 detects the collisions, decides who wins by precedence, and scopes (never deletes) the loser. It solves the "two shapes fire on the same record with opposite messages" problem before anything reaches Layer 6.

Inputs, outputs, components. Input: compiled rule ASTs. Output: `active_rules.json`, `decisions.json` (every collision, winner, loser, legal basis), and `active_shapes.ttl` (re-compiled, conflict-free). Components: a collision detector (opposite deontics on the same subject and action whose objects overlap under `skos:broader`; same obligation with different deadlines), a precedence table (lex specialis: state amendatory > endorsement > base form > manual; lex posterior: later edition wins within a form family), a scoping step that adds the winner's applicability as `UNLESS` (conjunctive carve-out) or complement `WHEN` to the loser, and a log. Production replaces the small resolver with an SMT or defeasible-logic solver (Z3) for exhaustive multi-rule checking.

Connections. Reads Layer 4; writes the shape set that Layer 6 enforces and that step 8 loads into GraphDB. The decisions also become `pc:overriddenBy` edges on `pc:Rule` nodes so Graph RAG can explain why a rule is scoped.

Insurance example. R01 (PROHIBITION pay Flood, from MM-CP-0010 B.1) collides with R02 (PERMISSION pay Flood when MM-CP-E101 attached, from E101 1.2). R02 is from an endorsement, R01 from the base form: lex specialis, R02 wins. R01 is re-written as "... UNLESS Claim.onPolicy.hasEndorsement = MM-CP-E101 AND Claim.atLocation.scheduledUnder = MM-CP-E101 AND Claim.affectsCoverage IN (COV-A, COV-B)". R03 (72 hours, base form) vs R04 (14 days, FL-01, state amendatory): R03 becomes "WHEN Claim.onPolicy.inState != FL". R02 vs R11 (no payment if vacant > 60 days) is judged compatible: R11 has its own substantive condition, so both stay active.

Common mistakes.
- Deleting the losing rule. It still applies outside the winner's scope (72 hours still binds Texas claims).
- Carve-outs as separate `UNLESS` lines: each one exempts on its own, so "has E101 OR scheduled OR Coverage A" is far too generous. The carve-out must be one conjunctive group.
- Treating scope conditions (which form, which state) as substantive restrictions when testing compatibility; the POC had this bug and wrongly called R01/R02 compatible until scope attributes were separated.
- Hard-coding precedence per rule. Derive it from the source document type and edition date so new documents inherit the right rank.

## Layer 6: Virtualization & Stream Enforcement

Purpose. Apply the active shape set to live records as they change, at the moments that matter (Quote, Bind, Endorsement, FNOL, Renewal), and tell the right person. It solves latency and cost: you validate only the changed record, not the whole book, and you never copy the policy admin system into the graph.

Inputs, outputs, components. Input: change events from the operational system (CDC via Debezium), a virtualization mapping (RML) that turns a row change into the few triples that describe that record, and the active shapes. Output: pass, or a validation report turned into alerts routed by rule owner (underwriting rules to the underwriter, coverage and claims rules to the adjuster). Components: event bus, RML/virtualization layer, an incremental SHACL engine (GraphDB's ShaclSail validates the transaction's changes against the shapes on every commit, which is what the POC uses), and a dispatcher.

Connections. Reads the shapes from Layer 5 and the reference data from the graph (filing statuses, territories, authority levels); writes alerts and, optionally, accepted records into the operational named graph.

Insurance example (the deck's end-to-end case). A bind event arrives for a Florida commercial property policy: forms MM-CP-0010 and MM-CP-1030, no endorsements, one location in territory FL-T03, flood zone AE, not scheduled. The event is mapped to 16 triples and committed. ShaclSail rejects the commit with three results: R07 (FL-01 missing), R08 (E310 mandatory in FL-T03), R09 (zone AE location must be scheduled under E101 or carry a signed flood acknowledgment). All three route to the underwriter. The policy is never stored in the inconsistent state.

Common mistakes.
- Validating the whole repository on each event. Use commit-time (incremental) validation or a per-record check.
- Validating the candidate record in isolation. R06 (form approved in the policy state) needs the filing data; the check must run against the graph.
- One alert queue for everyone. Route by rule owner; underwriters and adjusters need different items.
- Forgetting that deletes are validated too. In the POC, deleting a location before its policy was rejected because the policy would then point at a node that is no longer a `pc:Location`. Delete related records in one transaction.

---

# Task 2: the six synthetic source documents

All six are generated by `scripts/00_generate_source_pdfs.py` (reportlab; 500 lines, one function per document, shared `build()` and `table()` helpers). Run `python scripts/00_generate_source_pdfs.py` to regenerate `sources/*.pdf`. The PDFs are attached to this delivery as well.

Shared identifier set, so that every document can reference every other one:

| Kind | Identifiers |
|---|---|
| Forms | MM-CP-0010 (Building and Personal Property Coverage Form, Ed. 01/2025), MM-CP-1030 (Causes of Loss - Special Form, Ed. 01/2025) |
| Endorsements | MM-CP-E101 Flood, scheduled locations (06/2025); MM-CP-E205 Equipment Breakdown (01/2025); MM-CP-E310 Windstorm or Hail percentage deductible (03/2025); MM-CP-E415 Protective Safeguards (01/2025); MM-CP-FL-01 Florida Amendatory (07/2025) |
| Coverages | COV-A Building, COV-B Your Business Personal Property, COV-C Personal Property of Others, COV-D Business Income |
| Exclusions | EXCL-FLD Water/Flood, EXCL-EQ Earth Movement, EXCL-WAR, EXCL-MOLD, EXCL-WEAR |
| States and filings | FL MM-FL-2025-0142 (approved 06/15/2025), TX MM-TX-2025-0098 (approved), NY MM-NY-2025-0211 (pending; E101 and E310 not filed) |
| Rating | territories FL-T01, FL-T03 (Tier 1 coastal, 1.45), TX-T01 (Gulf coast, 1.35), TX-T04, NY-T07; construction classes CC1-CC6; protection classes PC1-PC10; safeguard factors SPR-1, ALM-1, ALM-2, WH-2, WH-5; deductible factors |
| Class codes | 0511 prohibited, 0921 and 0634 refer, 0745 and 0802 eligible |
| Authority | UW Level 1 Associate (max 5,000,000 TIV), Level 2 Senior, Level 3 Manager, Home Office |

Document contents (what Layer 1 extracted from each; page numbers are where the sections land):

1. `01_policy_form_MM-CP-0010.pdf` (3 pages). Sections A Coverage (A.1-A.4 grants for COV-A..D with a limits table), B Exclusions and Limitations (B.1 imports EXCL-* from MM-CP-1030 "unless an endorsement ... states otherwise"), C Limits, D Deductible (D.1 flat deductible, D.2 percentage deductible reference to E310), E Loss Conditions (E.1 Abandonment, E.2 Appraisal, E.3 Duties: police, notice within 72 hours, proof of loss within 60 days; E.4 Loss Payment 30 days; E.5 Vacancy: no payment for vandalism/water if vacant more than 60 days), F Additional Conditions, G Optional endorsements list.
2. `02_endorsements_MM-CP-E-series.pdf` (3 pages). Five endorsements, each 4-5 numbered clauses: E101 (1.1 scope, 1.2 coverage grant deleting EXCL-FLD for Flood at scheduled locations, 1.3 5 percent deductible min $25,000, 1.4 $250,000 sublimit, COV-D excluded, schedule table), E205 (mechanical breakdown grant, $100,000 sublimit), E310 (wind/hail percentage deductible; 3.4 mandatory in FL Tier 1 coastal and TX-T01), E415 (safeguards; 4.2 notify within 48 hours except ordinary maintenance; 4.3 suspension of coverage), FL-01 (5.2 cancellation 45 days, 5.3 notice extended to 14 days, 5.4 hurricane deductible display, 5.5 mediation), and section 6 the Endorsement Availability Matrix (endorsement x edition x coverages x forms x FL/TX/NY status).
3. `03_underwriting_guidelines_MM-UW-CP-2025.pdf` (3 pages). 1 Purpose and scope; 2 Eligibility with the class code table (0511 prohibited, 0921 refer...); 3 Authority limits with the authority level table and 3.1 "must not bind above authority"; 4 Required endorsements and forms (4.2 FL-01 on every FL policy, 4.3 E310 mandatory in FL Tier 1 coastal / TX-T01, 4.4 flood zone A/AE/V/VE must be scheduled under E101 or signed Flood Exclusion Acknowledgment, 4.5 E415 for class 0802, 4.6 forms only where the state filing shows Approved); 5 Quoting and binding; 6 Renewal review.
4. `04_rate_manual_MM-RM-CP-2025.pdf` (3 pages). Rule 1 rating procedure (premium = TIV / 100 x base rate x territory x protection x deductible x safeguard factors); Rule 2 base rates by construction class (table); Rule 3 territory factors (table, with "E310 mandatory" notes on FL-T03 / TX-T01); Rule 4 protection class factors; Rule 5 deductible factors; Rule 6 protective safeguard factors (SPR-1 requires E415); Rule 7 endorsement premiums (E101 per $100 of flood sublimit by zone); Rule 8 worked example.
5. `05_claims_manual_MM-CM-CP-2025.pdf` (3 pages). 1 FNOL (1.1 72 hours, FL 14 days via FL-01 5.3, late notice not a denial unless prejudice; 1.2 acknowledge within 14 calendar days FL / 15 business days TX; 1.3 what to record); 2 Coverage verification (2.1 editions match filing, 2.2-2.4 flood decision tree around EXCL-FLD and E101, table of decision outcomes); 3 Reserves and authority (table); 4 Proof of loss and payment (60 / 30 days, percentage deductible handling); 5 Vacancy and safeguards; 6 Subrogation and salvage.
6. `06_state_filings_MM-2025.pdf` (2 pages). Filing 1 FL MM-FL-2025-0142 (tracking, approval date, conditions, form table with statuses and "Replaces Ed. 07/2022" actions), Filing 2 TX MM-TX-2025-0098, Filing 3 NY MM-NY-2025-0211 (pending; 3.2 E101 and E310 not included, must not be used in NY), Section 4 filing compliance rules, Section 5 form-to-state cross-reference table.

How the generator is written (excerpt, same style for all six):

```python
# scripts/00_generate_source_pdfs.py  (excerpt). build() renders a title block, a metadata table, then a list of
# ("h2" | "p" | "table") blocks with reportlab platypus; each document is one function.
def endorsements():
    build("02_endorsements_MM-CP-E-series.pdf",
          "Commercial Property Endorsements Package",
          "Meridian Mutual Insurance Company (fictional). Endorsements modifying form MM-CP-0010 and MM-CP-1030.",
          [["Package", "MM-CP-E-SERIES"], ["Edition Dates", "E101 06/2025; E205 01/2025; E310 03/2025; E415 01/2025; FL-01 07/2025"],
           ["Modifies Forms", "MM-CP-0010 (Ed. 01/2025), MM-CP-1030 (Ed. 01/2025)"]],
          [
              ("h2", "1. MM-CP-E101 - FLOOD COVERAGE ENDORSEMENT - SCHEDULED LOCATIONS (Ed. 06/2025)"),
              ("p", "1.1 This endorsement modifies insurance provided under MM-CP-0010 and MM-CP-1030. It applies only to the "
                    "scheduled locations listed in the Schedule below and to Coverages COV-A (Building) and COV-B ..."),
              ("p", "1.2 Coverage Grant. Exclusion EXCL-FLD (Water) in Section B.1.g of MM-CP-1030 is deleted with respect to the "
                    "peril of Flood for the scheduled locations. We will pay for direct physical loss ... caused by Flood ..."),
              ("p", "1.3 Flood Deductible. A deductible of 5% of the Limit of Insurance for COV-A at the scheduled location "
                    "applies to each Flood occurrence, but not less than $25,000. ..."),
              ("table", [["Schedule Item", "Value"], ["Flood Sublimit (COV-A + COV-B, per location)", "$250,000"],
                         ["Flood Deductible", "5% of COV-A limit, minimum $25,000"], ["Available States", "FL, TX"]],
               [3.2 * inch, 3.2 * inch]),
              # ... E205, E310, E415, FL-01 ...
              ("h2", "6. ENDORSEMENT AVAILABILITY MATRIX"),
              ("table", [["Endorsement", "Edition", "Modifies Coverages", "Modifies Forms", "FL", "TX", "NY"],
                         ["MM-CP-E101", "06/2025", "COV-A, COV-B", "MM-CP-0010, MM-CP-1030", "Approved", "Approved", "Not filed"],
                         ["MM-CP-E310", "03/2025", "COV-A, COV-B", "MM-CP-0010", "Approved (mandatory Tier 1)", "Approved", "Not filed"],
                         ["MM-CP-FL-01", "07/2025", "COV-A", "MM-CP-0010", "Approved (mandatory)", "N/A", "N/A"]],
               [0.95 * inch, 0.6 * inch, 1.1 * inch, 1.4 * inch, 0.95 * inch, 0.7 * inch, 0.7 * inch]),
              ("p", "6.1 Precedence. Where an endorsement conflicts with the base form, the endorsement controls. ..."),
          ])
```

Design choice worth copying: every clause starts with its number ("1.2 ") and every table has a header row. That is what makes Layer 1 deterministic. Real carrier documents are messier; Docling or Marker then do the work pdfplumber does here.

---

# Task 3: end-to-end POC on Graphwise GraphDB

Everything below was run, not just written. Sample outputs are copied from the files in `output/`. Each script is standalone, reads the previous script's output folder and writes its own, so you can re-run any stage alone.

Environment used: GraphDB 10.8.11 Free (unzipped distribution, `bin/graphdb`, Java 21), Python 3.14, rdflib 7.6, pySHACL 0.40, Lark 1.3, sentence-transformers 6.1 (all-MiniLM-L6-v2). The official image is on Docker Hub as `ontotext/graphdb` with tags for 10.8.x and 11.x ([Docker Hub](https://hub.docker.com/r/ontotext/graphdb/)). Note on licensing: the 11.5.1 distribution refused writes with "No license was set" until a license file is installed (a free license can be requested from Graphwise); 10.8.11 runs as "free" out of the box. Nothing in the POC depends on the version.

## Step 1: data extraction (Layers 1-3)

### 1a. Parse PDFs into a clause tree (`scripts/01_parse_clause_tree.py`, Layer 1)

Core idea in code: read words and tables with their coordinates, interleave them by vertical position, split into clauses only where a clause number follows a sentence end, and keep exceptions as children.

```python
# clause boundary: "A.1", "E.3", "1.2" ... but only at the start or right after ". " or ": "
CLAUSE_SPLIT_RE = re.compile(r"(?:^|(?<=[.:]\s))(?=(?:[A-H]\.\d{1,2}|\d{1,2}\.\d{1,2})\s+(?=[A-Z'\"]))")

def build_clause(doc_id, section, cid, body, page):
    """A clause node. Exception sentences become children; sub-items (a)...(e) are kept inside the text."""
    sentences = split_sentences(body)
    main, exceptions = [], []
    for s in sentences:
        if s.lower().startswith(("except", "unless", "however")):
            exceptions.append(s); continue                 # whole sentence is an exception
        main.append(s)                                     # the rule sentence stays with the parent...
        m = re.search(r",?\s+\b(except|unless|but not less than|other than|does not apply)\b", s, re.I)
        if m:                                              # ...and the exception fragment is ALSO kept as a child
            exceptions.append(s[m.start():].strip(" ,"))
    return {"clause_id": f"{doc_id}#{section['id']}/{cid}", "ref": cid, "page": page,
            "text": " ".join(main) if main else body, "full_text": body,
            "exceptions": [{"clause_id": f"{doc_id}#{section['id']}/{cid}/x{i+1}", "text": e,
                            "exception_to": f"{doc_id}#{section['id']}/{cid}"} for i, e in enumerate(exceptions)],
            "ids": {k: sorted(set(p.findall(body))) for k, p in ID_PATTERNS.items()}}

def gatekeeper(node):
    """Rule-based filter: keep if it looks like a rule or carries an identifier; drop front matter."""
    if node["section"] == "FRONT": return False, "front-matter"
    if RULE_SIGNALS.search(node["full_text"]): return True, "rule-signal"
    if node["ids"]: return True, "identifier"
    return False, "no-rule-signal"
```

Sample output (`output/01_clause_tree/MM-CP-E-SERIES.json`, trimmed):

```json
{
  "clause_id": "MM-CP-E-SERIES#4-MM-CP-E415/4.2",
  "section_title": "4. MM-CP-E415 - PROTECTIVE SAFEGUARDS ENDORSEMENT (Ed. 01/2025)",
  "ref": "4.2", "page": 3,
  "full_text": "4.2 You must notify us within 48 hours if any listed protective safeguard is impaired or out of service, except when the impairment is due to ordinary maintenance that is completed within 24 hours.",
  "exceptions": [{ "clause_id": "MM-CP-E-SERIES#4-MM-CP-E415/4.2/x1",
                   "text": "except when the impairment is due to ordinary maintenance that is completed within 24 hours.",
                   "exception_to": "MM-CP-E-SERIES#4-MM-CP-E415/4.2" }]
}
```

Result over the six documents: 90 clauses kept, 21 dropped by the gatekeeper (front matter, headings), 22 tables lifted (6 front-matter metadata tables plus the availability matrix, filing tables, territory factors, class codes, authority levels...).

### 1b. Classify (`scripts/02_classify_deontic.py`, Layer 2)

```python
GATE = 0.60
CUES = {"Prohibition": [(r"\bwill not pay\b", 3), (r"\bmust not\b", 3), (r"\bprohibited\b", 3), (r"\bnot covered\b", 2.5), ...],
        "Obligation":  [(r"\byou must\b", 3), (r"\bmust\b", 2.5), (r"\bis required to\b", 3), (r"\bmandatory\b", 3),
                        (r"\bwithin \d+ (?:hours|days|business days|calendar days)\b", 1.5), ...],
        "Permission":  [(r"\bwe will pay\b", 3), (r"\bmay be attached\b", 3), (r"\bis deleted\b", 2.5), (r"\bdoes not apply\b", 2), ...]}

def pass1(text):                      # fast scorer (stand-in for a small local model)
    scores = {k: sum(w * len(rx.findall(text)) for rx, w in COMPILED[k]) for k in CUES}
    total = sum(scores.values())
    if total == 0: return "Permission", 0.34, scores          # descriptive text: weak default, visible in the graph
    label = max(scores, key=scores.get)
    return label, round(scores[label] / total, 3), scores

def classify(text):
    label, conf, scores = pass1(text); route = "pass1"
    if conf < GATE:                                             # confidence gate -> strict adjudicator
        label, route = pass2_llm(text) if os.environ.get("OPENAI_API_KEY") else pass2_rules(text)
    return {"deontic": label, "confidence": conf, "route": route, "scores": scores}
```

Sample output (`output/02_classified/_summary.json`): gate 0.60; routes pass1 63, pass2-rules 27 (30 percent), pass2-llm 0; labels Permission 37, Prohibition 15, Obligation 38. Known weak spot kept on purpose: A.2 (a definition of Covered Property that says "limited in A.3 Property Not Covered") lands as Prohibition with confidence 1.0 because "not covered" is its only cue, and B.1 is Permission at 0.34; both are the kind of item a review queue should receive, and the first one shows why high confidence from a lexical scorer is not the same as being right.

### 1c. Ground to the ontology (`scripts/03_ground_ontology.py`, Layer 3)

```python
def build_term_index():              # every class + individual in the ontology, with label and skos:altLabels
    g = Graph().parse(ONTOLOGY_TTL)
    terms = []
    for s in set(g.subjects(RDF.type, OWL.Class)) | {s for s in g.subjects() if (s, RDF.type, None) in g and str(s).startswith(PCD)}:
        labels = [str(o) for o in g.objects(s, RDFS.label)] + [str(o) for o in g.objects(s, SKOS.altLabel)]
        if labels: terms.append({"iri": str(s), "label": labels[0], "altLabels": labels[1:], "text": "; ".join(labels)})
    return terms

sims = C @ T.T                        # clause embeddings x term embeddings (MiniLM, normalized -> cosine)
c["grounding"] = {"hard": hard_ground(c["ids"]) + peril_ground(c["text"]),           # regex ids -> IRIs
                  "soft_top3": [{"iri": terms[j]["iri"], "label": terms[j]["label"], "score": round(float(sims[i, j]), 3)}
                                for j in np.argsort(-sims[i])[:3]]}
```

Sample output for MM-CP-0010 B.1: hard = MM-CP-1030, COV-A, COV-B, COV-C, COV-D, EXCL-FLD, EXCL-EQ, EXCL-WAR, EXCL-MOLD, EXCL-WEAR; soft top-3 = Policy Form 0.485, Claim 0.419, Exclusion 0.418. 63 ontology terms indexed.

### 1d. LLM-assisted extraction (where the model sits)

Three places, all optional and all schema-constrained: pass-2 adjudication in 02 (JSON `{"label": ...}`), typed rule extraction in 04 (`--llm`, Pydantic `TypedRule` schema, re-validated), and answer generation in 09. Without `OPENAI_API_KEY` the deterministic stand-ins run, so the whole POC is reproducible offline.

## Step 2: ontology (`ontology/pc_ontology.ttl`)

Design: classes for documents and their parts, for the insurance domain, for operational records, and for the pipeline's own artefacts (clause, chunk, rule). Individuals for closed sets (coverages, perils, states, statuses). SKOS for synonyms and the peril hierarchy.

```turtle
@prefix pc:   <https://example.org/pc/ontology#> .     # classes and properties
@prefix pcd:  <https://example.org/pc/id/> .            # individuals and instance data
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

pc:Document   a owl:Class .
pc:Form       a owl:Class ; rdfs:subClassOf pc:Document .
pc:PolicyForm a owl:Class ; rdfs:subClassOf pc:Form .
pc:Endorsement a owl:Class ; rdfs:subClassOf pc:Form ;
    skos:altLabel "rider", "amendment" .
pc:StateAmendatoryEndorsement a owl:Class ; rdfs:subClassOf pc:Endorsement .
pc:UnderwritingGuideline a owl:Class ; rdfs:subClassOf pc:Document .    # also RateManual, ClaimsManual, StateFiling

pc:Coverage  a owl:Class .          pc:Peril a owl:Class .        pc:Exclusion a owl:Class .
pc:State a owl:Class .              pc:Territory a owl:Class .    pc:ClassCode a owl:Class .
pc:FloodZone a owl:Class .          pc:AuthorityLevel a owl:Class . pc:FormApproval a owl:Class .
pc:Policy a owl:Class .             pc:Location a owl:Class .     pc:Claim a owl:Class .
pc:Clause a owl:Class .             pc:Chunk a owl:Class .        pc:Rule a owl:Class .

pcd:COV-A a pc:Coverage ; pc:coverageCode "COV-A" ; rdfs:label "Coverage A - Building" ; skos:altLabel "building coverage" .
pcd:Flood a pc:Peril ; rdfs:label "Flood" ; skos:broader pcd:Water ; skos:altLabel "surface water", "storm surge" .
pcd:FL a pc:State ; pc:stateCode "FL" ; rdfs:label "Florida" .

pc:modifiesCoverage  a owl:ObjectProperty ; rdfs:domain pc:Endorsement ; rdfs:range pc:Coverage .
pc:modifiesForm      a owl:ObjectProperty ; rdfs:domain pc:Endorsement ; rdfs:range pc:PolicyForm .
pc:removesExclusion  a owl:ObjectProperty ; rdfs:domain pc:Endorsement ; rdfs:range pc:Exclusion .
pc:restoresPeril     a owl:ObjectProperty ; rdfs:domain pc:Endorsement ; rdfs:range pc:Peril .
pc:hasExclusion      a owl:ObjectProperty ; rdfs:domain pc:Form ; rdfs:range pc:Exclusion .
pc:excludesPeril     a owl:ObjectProperty ; rdfs:domain pc:Exclusion ; rdfs:range pc:Peril .
pc:hasFormApproval   a owl:ObjectProperty ; rdfs:domain pc:StateFiling ; rdfs:range pc:FormApproval .
pc:approvalOfForm    a owl:ObjectProperty .  pc:approvalInState a owl:ObjectProperty .  pc:approvalStatus a owl:ObjectProperty .
pc:mandatoryIn       a owl:ObjectProperty .  # endorsement -> state or territory
pc:compiledFrom      a owl:ObjectProperty ; rdfs:domain pc:Rule ; rdfs:range pc:Clause .
pc:overriddenBy      a owl:ObjectProperty ; rdfs:domain pc:Rule ; rdfs:range pc:Rule .
pc:exceptionTo       a owl:ObjectProperty ; rdfs:domain pc:Clause ; rdfs:range pc:Clause .
pc:hasEndorsement    a owl:ObjectProperty ; rdfs:domain pc:Policy ; rdfs:range pc:Endorsement .   # + hasForm, hasLocation, inState ...
pc:noticeDelayHours  a owl:DatatypeProperty ; rdfs:domain pc:Claim ; rdfs:range xsd:integer .
```

Diagram description (draw it as three bands):
- Top band, documents: Document -> Form -> {PolicyForm, Endorsement -> StateAmendatoryEndorsement}; Document -> {UnderwritingGuideline, RateManual, ClaimsManual, StateFiling}. Clause and Chunk hang off Document via `sourceDocument` / `prov:wasDerivedFrom`; Clause -> Clause via `exceptionTo`; Rule -> Clause via `compiledFrom`, Rule -> Rule via `overriddenBy`.
- Middle band, domain: Endorsement -> Coverage (`modifiesCoverage`), Endorsement -> PolicyForm (`modifiesForm`), Form -> Exclusion (`hasExclusion`) -> Peril (`excludesPeril`), Endorsement -> Exclusion (`removesExclusion`) and -> Peril (`restoresPeril`), StateFiling -> FormApproval -> {Form, State, FilingStatus}, Endorsement -> State or Territory (`mandatoryIn`), Territory -> State, RatingFactor -> Endorsement (`factorRequiresEndorsement`).
- Bottom band, operational: Policy -> {State, Form, Endorsement, Location, ClassCode, Underwriter -> AuthorityLevel}; Location -> {State, Territory, FloodZone, Endorsement (`scheduledUnder`)}; Claim -> {Policy, Location, Peril (`causeOfLoss`), Coverage (`affectsCoverage`)} plus the deadline literals.

Why `rdfsplus-optimized`: GraphDB's repository config takes a `ruleset` (`empty`, `rdfs`, `rdfsplus`, `owl-horst`, `owl-max`, `owl2-rl`, each with an `-optimized` variant), the default being `rdfsplus-optimized` ([GraphDB configuring a repository](https://graphdb.ontotext.com/documentation/11.5/configuring-a-repository.html)). RDFS-Plus gives us subclass and domain/range inference (an Endorsement is a Form; a thing with `hasEndorsement` is a Policy) at negligible cost, which is all this POC needs.

## Step 3: RDF generation (`scripts/06_build_rdf.py`)

Mapping approach: Python + rdflib, one function per logical source, deliberately shaped like RML TriplesMaps (subject template, predicate-object maps). `docs/rml_example.ttl` shows the same two mappings in RML for when the source is a relational table.

```python
def map_endorsement_matrix(g, table):
    """Table 'ENDORSEMENT AVAILABILITY MATRIX' -> modifiesCoverage / modifiesForm / editionDate / appliesInState"""
    hdr = table["header"]
    for row in table["rows"]:
        r = dict(zip(hdr, row))
        e = pcd[r["Endorsement"]]                                   # subject template  pcd:{Endorsement}
        g.add((e, pc.editionDate, Literal(r["Edition"])))
        for cov in re.findall(r"COV-[A-D]", r["Modifies Coverages"]):
            g.add((e, pc.modifiesCoverage, pcd[cov]))
        for f in re.findall(r"MM-CP-\d{4}", r["Modifies Forms"]):
            g.add((e, pc.modifiesForm, pcd[f]))
        for st in ("FL", "TX", "NY"):
            if r.get(st, "").startswith("Approved"):
                g.add((e, pc.appliesInState, pcd[st]))
                if "mandatory" in r[st].lower(): g.add((e, pc.mandatoryIn, pcd[st]))

def map_clauses(g, trees):          # every clause becomes a pc:Clause AND a pc:Chunk with citation fields
    for doc_id, t in trees.items():
        for s in t["sections"]:
            for c in s["clauses"]:
                ci = clause_iri(c["clause_id"])                     # '#' and '/' -> '_' : pcd:MM-CP-0010_SECTION-E_E.3
                g.add((ci, RDF.type, pc.Clause)); g.add((ci, RDF.type, pc.Chunk))
                g.add((ci, pc.sourceDocument, pcd[doc_id])); g.add((ci, PROV.wasDerivedFrom, pcd[doc_id]))
                g.add((ci, pc.sectionRef, Literal(f"{s['title']} / {c['ref']}"))); g.add((ci, pc.pageNumber, Literal(c["page"])))
                g.add((ci, pc.clauseText, Literal(c["full_text"])))
                g.add((ci, pc.chunkText, Literal(f"[{doc_id} {s['title']} {c['ref']} p.{c['page']}] {c['full_text']}")))
                g.add((ci, pc.deonticType, pcd[c["classification"]["deontic"]]))
                g.add((ci, pc.confidence, Literal(c["classification"]["confidence"], datatype=XSD.decimal)))
                for h in c["grounding"]["hard"]:  g.add((ci, pc.mentions, URIRef(h["iri"])))
                for x in c["exceptions"]:
                    xi = clause_iri(x["clause_id"]); g.add((xi, RDF.type, pc.Clause)); g.add((xi, pc.exceptionTo, ci)) ...
```

Sample Turtle (`output/06_rdf/data.ttl` and `clauses.ttl`):

```turtle
pcd:MM-CP-E101 a pc:Endorsement ;
    rdfs:label "Flood Coverage Endorsement - Scheduled Locations" ;
    pc:formNumber "MM-CP-E101" ; pc:editionDate "06/2025" ;
    pc:modifiesCoverage pcd:COV-A, pcd:COV-B ;
    pc:modifiesForm pcd:MM-CP-0010, pcd:MM-CP-1030 ;
    pc:appliesInState pcd:FL, pcd:TX ;
    pc:removesExclusion pcd:EXCL-FLD ; pc:restoresPeril pcd:Flood ;
    pc:sublimitAmount 250000.0 ; pc:deductiblePercent 5.0 ; pc:deductibleMinimum 25000.0 .

pcd:approval/MM-FL-2025-0142/MM-CP-E101 a pc:FormApproval ;
    pc:approvalOfForm pcd:MM-CP-E101 ; pc:approvalInState pcd:FL ; pc:approvalStatus pcd:Approved ; pc:editionDate "06/2025" .

pcd:FL-T03 a pc:Territory ; rdfs:label "FL-T03 Tier 1 coastal counties" ; pc:territoryState pcd:FL ;
    pc:factorValue 1.45 ; rdfs:comment "MM-CP-E310 mandatory (MM-UW-CP-2025 4.3)" .

pcd:MM-CP-0010_SECTION-B_B.1 a pc:Clause, pc:Chunk ;
    rdfs:label "MM-CP-0010 B.1" ; prov:wasDerivedFrom pcd:MM-CP-0010 ;
    pc:sectionRef "SECTION B - EXCLUSIONS AND LIMITATIONS / B.1" ; pc:pageNumber 2 ;
    pc:deonticType pcd:Permission ; pc:confidence 0.34 ; pc:classifierRoute "pass2-rules" ;
    pc:mentions pcd:COV-A, pcd:COV-B, pcd:EXCL-FLD, pcd:MM-CP-1030 ... ;
    pc:groundedTerm pc:Claim, pc:Exclusion, pc:PolicyForm ;
    pc:clauseText "B.1 See the applicable Causes of Loss form MM-CP-1030 for exclusions ..." .
```

Output: `data.ttl` 407 triples, `clauses.ttl` 1760, `rules.ttl` 86, `operational.ttl` 44 (one valid FL policy, location in FL-T03 zone AE scheduled under E101, one flood claim), `all.trig` 2780 triples in 6 named graphs.

## Step 4: SHACL validation (Layers 4-5 produce shapes; two gates validate)

### 4a. Core shapes, hand-written (`shapes/core_shapes.ttl`)

```turtle
shape:EndorsementShape a sh:NodeShape ;
    sh:targetClass pc:Endorsement ;
    sh:property [ sh:path pc:modifiesForm ; sh:minCount 1 ; sh:class pc:PolicyForm ;
                  sh:message "An endorsement must modify at least one policy form." ] ;
    sh:property [ sh:path pc:modifiesCoverage ; sh:minCount 1 ; sh:class pc:Coverage ;
                  sh:message "An endorsement must state which coverage(s) it modifies." ] ;
    sh:property [ sh:path pc:appliesInState ; sh:minCount 1 ; sh:class pc:State ;
                  sh:message "An endorsement must be approved in at least one state, otherwise it cannot be attached anywhere." ] .

shape:ClauseShape a sh:NodeShape ;
    sh:targetClass pc:Clause ;
    sh:property [ sh:path pc:sourceDocument ; sh:minCount 1 ; sh:maxCount 1 ; sh:class pc:Document ;
                  sh:message "Every clause must point to the document it came from (citation guarantee)." ] ;
    sh:property [ sh:path pc:pageNumber ; sh:minCount 1 ; sh:datatype xsd:integer ; sh:minInclusive 1 ] ;
    sh:property [ sh:path pc:deonticType ; sh:maxCount 1 ; sh:in ( pcd:Obligation pcd:Permission pcd:Prohibition ) ] ;
    sh:property [ sh:path pc:exceptionTo ; sh:class pc:Clause ] .
```

Shapes also exist for Form, StateFiling, FormApproval, Coverage, Territory, ClassCode, Policy, Location, Claim.

### 4b. Compiled rule shapes (Layer 4, `scripts/rulec.py` + `04_compile_rules.py`)

The typed rule the model must emit (R02, from `config/typed_rules_seed.json`):

```json
{ "rule_id": "R02", "deontic": "PERMISSION", "subject": "Claim", "action": "pay_for_loss",
  "object_type": "Peril", "object_ids": ["Flood"],
  "conditions":   [ {"path": "Claim.causeOfLoss", "op": "=", "value": "Flood"},
                    {"path": "Claim.onPolicy.hasEndorsement", "op": "=", "value": "MM-CP-E101"} ],
  "requirements": [ {"path": "Claim.atLocation.scheduledUnder", "op": "=", "value": "MM-CP-E101"},
                    {"path": "Claim.affectsCoverage", "op": "IN", "value": ["COV-A", "COV-B"]} ],
  "source_clause": "MM-CP-E-SERIES#1-MM-CP-E101/1.2",
  "message": "MM-CP-E101 restores Flood only for scheduled locations and only for COV-A / COV-B (sublimit $250,000, 5% deductible)." }
```

DSL line, grammar and compiler (excerpts):

```
PERMISSION Claim pay_for_loss Peril:Flood WHEN Claim.causeOfLoss = Flood WHEN Claim.onPolicy.hasEndorsement = MM-CP-E101
  REQUIRES Claim.atLocation.scheduledUnder = MM-CP-E101 REQUIRES Claim.affectsCoverage IN (COV-A, COV-B) SOURCE MM-CP-E-SERIES#1-MM-CP-E101/1.2
```

```python
GRAMMAR = r"""
start: deontic subject action object clause* source
deontic: "OBLIGATION" -> obligation | "PERMISSION" -> permission | "PROHIBITION" -> prohibition
object: "NONE" -> no_object | CLASS ":" idlist -> typed_object
clause: "WHEN" cond -> when | "REQUIRES" cond -> requires | "UNLESS" cond ("AND" cond)* -> unless | "WITHIN" INT UNIT -> within
cond: PATH OP value
value: "(" ID ("," ID)* ")" -> list_value | PATH -> path_value | "true" | "false" | NUMBER | ID
PATH.2: /[A-Z][A-Za-z]+(\.\^?[A-Za-z][A-Za-z0-9]*)+/      # Claim.onPolicy.hasEndorsement ; ^ = inverse step
SRC: /[A-Z][A-Z0-9-]+#[A-Za-z0-9.\-]+\/[A-Za-z0-9.\-\/]+/
"""
_parser = Lark(GRAMMAR, parser="lalr")        # a parse error = the rule is rejected, never compiled

def compile_shape(rule_id, ast, message, status):
    shape = SHAPE[rule_id]
    g.add((shape, RDF.type, SH.NodeShape)); g.add((shape, SH.targetClass, PCN[ast["subject"]]))
    g.add((shape, RDFS.label, RLiteral(rule_id)))                       # not sh:name (see Layer 4 mistakes)
    g.add((shape, PCN.compiledFrom, URIRef(PCD + ast["source"].replace("#", "/").replace("/", "_"))))
    if simple_unconditional(ast):                                       # -> plain property shape
        ...  sh:path / sh:hasValue  |  sh:not [sh:hasValue]  |  sh:maxInclusive
    else:                                                               # -> SHACL-SPARQL constraint
        lines = ["SELECT $this ?value WHERE {"] + [_cond_sparql(c, i) for i, c in enumerate(ast["when"])]
        lines.append(violation_pattern(ast))                            # e.g. BIND(<E101> AS ?value) FILTER NOT EXISTS { $this pc:hasEndorsement ?value }
        for grp in ast["unless"]:                                       # each UNLESS group = one FILTER NOT EXISTS { a . b . c }
            lines.append("FILTER NOT EXISTS { " + " ".join(_cond_sparql(c, j) for j, c in enumerate(grp)) + " }")
```

Compiled shape (R07, `shapes/compiled/R07.ttl`):

```turtle
shape:R07 a sh:NodeShape ;
    rdfs:label "R07" ;
    rdfs:comment "OBLIGATION Policy attach_endorsement | source MM-UW-CP-2025#SECTION-4/4.2 | status active" ;
    sh:targetClass pc:Policy ;
    pc:compiledFrom pcd:MM-UW-CP-2025_SECTION-4_4.2 ; pc:ruleStatus "active" ;
    sh:sparql [ sh:message "Florida policies must include MM-CP-FL-01 Florida Amendatory Endorsement (MM-UW-CP-2025 4.2)." ;
                sh:select """PREFIX pc: <https://example.org/pc/ontology#>  PREFIX pcd: <https://example.org/pc/id/>
                             SELECT $this ?value WHERE {
                               $this pc:inState ?c0 . FILTER(?c0 = pcd:FL)
                               BIND(pcd:MM-CP-FL-01 AS ?value)
                               FILTER NOT EXISTS { $this pc:hasEndorsement ?value } }""" ] .
```

Compiler run: 12 rules, 0 rejected. R08 is accepted with a logged warning: "cross-document identifier FL-T03: not in clause text, resolved from corpus tables; confirm in review" (UW 4.3 says "Florida Tier 1 coastal counties"; only the rate manual names FL-T03). Rule IDs and sources: R01 flood exclusion (0010 B.1), R02 E101 grant (E101 1.2), R03 72-hour notice (0010 E.3), R04 FL 14-day notice (FL-01 5.3), R05 prohibited class 0511 (UW 2.3), R06 form approved in state (UW 4.6), R07 FL-01 required (UW 4.2), R08 E310 in FL-T03/TX-T01 (UW 4.3), R09 flood zone scheduling (UW 4.4), R10 authority limit (UW 3.1), R11 vacancy (0010 E.5), R12 acknowledge in 14 days (CM 1.2).

GraphDB-specific limits to know, from the SHACL docs: ShaclSail supports `sh:path` only as a predicate, sequence, alternative or inverse path (no zero-or-more); `sh:sparql` constraints are supported but run per target node, so keep them selective; and `sh:message` does not substitute variables ([GraphDB SHACL validation](https://graphdb.ontotext.com/documentation/11.5/shacl-validation.html)). The compiler respects all three.

### 4c. Conflicts resolved (Layer 5, `scripts/05_resolve_conflicts.py`)

```python
def detect(rules, up):                                   # up = skos:broader closure from the ontology
    for a, b in pairs(rules):
        if A["subject"] != B["subject"] or A["action"] != B["action"]: continue
        if {A["deontic"], B["deontic"]} == {"PERMISSION", "PROHIBITION"} and overlaps(A.object.ids, B.object.ids, up):
            found.append({"type": "grant-vs-exclusion", "rules": [a.id, b.id]})
        elif A["deontic"] == B["deontic"] == "OBLIGATION" and A["within"] != B["within"]:
            found.append({"type": "deadline-value-conflict", "rules": [a.id, b.id]})

SPECIFICITY = [("MM-CP-FL-01", 4, "state amendatory"), ("MM-CP-E", 3, "endorsement"), ("MM-CP-0010", 2, "base form"), ("MM-UW", 1, "manual"), ...]
SCOPE_ATTRS = {"hasForm", "inState", "hasEndorsement", "inTerritory"}   # delimit WHERE a rule applies; not substantive

def resolve(col):
    winner, loser = by_rank_then_edition(a, b)           # lex specialis, then lex posterior
    if prohibition_has_substantive_condition_not_in_permission: log("compatible"); return
    if col["type"] == "grant-vs-exclusion":
        loser.ast["unless"].append(winner.ast["when"] (minus the peril condition) + winner.ast["requires"])   # ONE conjunctive group
    else:
        loser.ast["when"] += [negate(c) for c in winner.ast["when"]]
    loser.status = "scoped"; loser.overridden_by.append(winner.id)
```

Decisions (`output/05_active_rules/decisions.json`):

```
3 collisions detected
 - grant-vs-exclusion    [R01, R02] -> R01 narrowed: exclusion does not apply where R02 grants coverage | lex specialis
 - grant-vs-exclusion    [R02, R11] -> compatible | prohibition has its own narrower condition; both rules stay active
 - deadline-value-conflict [R03, R04] -> R03 scoped to the complement of R04's conditions | lex specialis
active rule set: 12 rules (10 active, 2 scoped)
  R01: PROHIBITION Claim pay_for_loss Peril:Flood WHEN Claim.onPolicy.hasForm = MM-CP-0010 ... UNLESS Claim.onPolicy.hasEndorsement = MM-CP-E101
       AND Claim.atLocation.scheduledUnder = MM-CP-E101 AND Claim.affectsCoverage IN (COV-A, COV-B)
  R03: OBLIGATION Claim report_loss NONE WITHIN 72 hours ... WHEN Claim.onPolicy.inState != FL
```

### 4d. Gate 1: local pySHACL with a break-and-fix demo (`scripts/07_validate_shacl_local.py`)

```python
conforms, report_graph, _ = validate(data, shacl_graph=shapes, ont_graph=ontology, inference="rdfs", advanced=True)
```

Output:

```
=== 01_generated_graph:    conforms = True   (0 results)
=== 02_with_bad_records:   conforms = False  (10 results)
  [EndorsementShape] pcd:MM-CP-E999         An endorsement must state which coverage(s) it modifies.
  [EndorsementShape] pcd:MM-CP-E999         An endorsement must be approved in at least one state ...
  [R01]  pcd:claim/CLM-0002                 Flood is excluded (EXCL-FLD, MM-CP-1030 B.1.g via MM-CP-0010 Section B.1). Check for a restoring endorsement.
  [R03]  pcd:claim/CLM-0003                 Insured must give notice of loss within 72 hours (MM-CP-0010 E.3(b)).
  [R05]  pcd:policy/POL-NY-0099             Class code 0511 (Fireworks or Explosives Manufacturing) is prohibited (MM-UW-CP-2025 2.3).
  [R06]  pcd:policy/POL-NY-0099             A form may be attached only where the State Filing shows status Approved for the policy state
  [R07]  pcd:policy/POL-FL-0002             Florida policies must include MM-CP-FL-01 ...
  [R08]  pcd:policy/POL-FL-0002             MM-CP-E310 is mandatory for locations in FL Tier 1 coastal counties (FL-T03) and TX-T01
  [R09]  pcd:location/LOC-0002              A location in flood zone A/AE/V/VE must be scheduled under MM-CP-E101 unless ...
  [R10]  pcd:policy/POL-NY-0099             Underwriter must not bind a risk above his or her authority level (MM-UW-CP-2025 3.1).
=== 03_after_fix:          conforms = True   (0 results)
```

The fix (`fixed_records.ttl`): give E999 a coverage and a state; write POL-NY-0099 in TX with class 0745 and TIV 4.5M; add FL-01, E310, E101 to POL-FL-0002 and schedule LOC-0002; set CLM-0003 notice to 48 hours. Note CLM-0002 (flood at an unscheduled location) is still rejected until the location is scheduled: the carve-out is conjunctive, exactly as Layer 5 intended.

### 4e. Gate 2: GraphDB ShaclSail at commit time (`scripts/08_graphdb_load.py`)

Repository config (`config/graphdb-repo-config.ttl`, derived from the distribution's `configs/templates/graphdb-shacl.ttl`): a `rdf4j:ShaclSail` wrapping the GraphDB sail, `ruleset "rdfsplus-optimized"`, context index on, FTS index on, `logValidationViolations true`, `parallelValidation false`. SHACL must be enabled when the repository is created; it cannot be switched on later ([GraphDB SHACL validation](https://graphdb.ontotext.com/documentation/11.5/shacl-validation.html)).

```python
db.create_repository(CONFIG)                                   # POST /rest/repositories  (multipart 'config')
for path, graph in [(ONTOLOGY_TTL, GRAPH_ONTOLOGY), (RDF_DIR/"data.ttl", GRAPH_DATA), ...]:
    db.load_turtle(path, graph, replace=True)                  # PUT /repositories/pc-poc/statements?context=<graph>
for p in (CORE_SHAPES_TTL, COMPILED_SHAPES_DIR/"active_shapes.ttl"):
    db.load_turtle(p, "http://rdf4j.org/schema/rdf4j#SHACLShapeGraph")   # reserved shapes graph; this commit validates all data
code, body = db.load_turtle(VAL_DIR/"bad_records.ttl", GRAPH_OPS)        # -> 500 + report in body, nothing stored
code, body = db.load_turtle(VAL_DIR/"fixed_records.ttl", GRAPH_OPS)      # -> 204
```

Live run:

```
creating repository pc-poc -> 201
load pc_ontology.ttl -> ontology HTTP 204 | data.ttl 204 | clauses.ttl 204 | rules.ttl 204 | operational.ttl 204
load shapes core_shapes.ttl -> SHACLShapeGraph HTTP 204
load shapes active_shapes.ttl -> SHACLShapeGraph HTTP 204
POST bad_records.ttl -> HTTP 500  (expected 500: ShaclSail rejected the transaction)
   violation: A form may be attached only where the State Filing shows status Approved for the policy state ...
   violation: A location in flood zone A/AE/V/VE must be scheduled under MM-CP-E101 unless a Flood Exclusion Acknowledgment ...
   violation: An endorsement must be approved in at least one state ...
   violation: An endorsement must state which coverage(s) it modifies.
   violation: Class code 0511 (Fireworks or Explosives Manufacturing) is prohibited (MM-UW-CP-2025 2.3).
   violation: Flood is excluded (EXCL-FLD, MM-CP-1030 B.1.g via MM-CP-0010 Section B.1). Check for a restoring endorsement.
   violation: Florida policies must include MM-CP-FL-01 Florida Amendatory Endorsement (MM-UW-CP-2025 4.2).
   violation: MM-CP-E310 is mandatory for locations in FL Tier 1 coastal counties (FL-T03) and TX-T01 (MM-UW-CP-2025 4.3).
   violation: Underwriter must not bind a risk above his or her authority level (MM-UW-CP-2025 3.1).
POST fixed_records.ttl -> HTTP 204  (expected 204: accepted)
cleanup of demo records -> HTTP 204; operational graph size now 44 (expected 44)
```

The 500 body is the SHACL validation report in N-Triples (`sh:conforms false`, one `sh:ValidationResult` per violation with `sh:focusNode`, `sh:sourceShape`, `sh:resultMessage`); `10_enforce_live_record.py` parses it into alerts. Two practical notes from the run: the shapes graph is not visible to SPARQL `GRAPH ?g` queries (read it back via `GET /repositories/pc-poc/statements?context=<shapes graph>`), and GraphDB also offers ad hoc validation endpoints (`POST /rest/repositories/{id}/validate/text`) for checking existing data against shapes you have not installed ([GraphDB SHACL validation](https://graphdb.ontotext.com/documentation/11.5/shacl-validation.html)).

## Step 5: graph load and SPARQL verification

Loading is the script above. Twelve queries live in `queries/` and `08_graphdb_load.py` runs them all and saves `output/08_graphdb/query_results.json`. Three of them, with results and a line-by-line reading for a SPARQL beginner.

q01: which endorsements modify Coverage A and are approved in Texas?

```sparql
PREFIX pc:  <https://example.org/pc/ontology#>   PREFIX pcd: <https://example.org/pc/id/>
SELECT ?endorsement ?title ?edition ?status WHERE {
  ?e a pc:Endorsement ;                      # ?e is anything typed Endorsement ("a" = rdf:type)
     pc:formNumber ?endorsement ;            # ";" repeats the subject ?e: read its form number...
     rdfs:label ?title ;                     # ...its title...
     pc:modifiesCoverage pcd:COV-A .         # ...and require that it modifies COV-A (a fixed IRI, no variable)
  OPTIONAL { ?e pc:editionDate ?edition }    # keep the row even if there is no edition date
  ?ap a pc:FormApproval ;                    # now a second node: an approval record
      pc:approvalOfForm ?e ;                 # ...for the same endorsement (this is the join)
      pc:approvalInState pcd:TX ;            # ...in Texas
      pc:approvalStatus ?st .                # ...with some status
  ?st rdfs:label ?status .                   # status label for display
  FILTER(?st = pcd:Approved)                 # keep only Approved
} ORDER BY ?endorsement
```

| endorsement | title | edition | status |
|---|---|---|---|
| MM-CP-E101 | Flood Coverage Endorsement - Scheduled Locations | 06/2025 | Approved |
| MM-CP-E205 | Equipment Breakdown Endorsement | 01/2025 | Approved |
| MM-CP-E310 | Windstorm or Hail Percentage Deductible | 03/2025 | Approved |
| MM-CP-E415 | Protective Safeguards Endorsement | 01/2025 | Approved |

MM-CP-FL-01 also modifies COV-A but is absent: it has no Texas approval record. That absence is the answer the filing register gives, and the graph reproduces it without any text search.

q02: the flood coverage path.

```sparql
SELECT ?exclusion ?restoringEndorsement ?sublimit ?deductiblePct ?deductibleMin
       (GROUP_CONCAT(DISTINCT ?stCode; separator=", ") AS ?approvedStates) WHERE {
  pcd:MM-CP-0010 pc:hasExclusion ?x .                       # start at the base form, walk to its exclusions
  ?x pc:exclusionCode ?exclusion ; pc:excludesPeril pcd:Flood .   # keep the one that excludes Flood
  ?e pc:removesExclusion ?x ; pc:formNumber ?restoringEndorsement . # any endorsement that deletes that exclusion
  OPTIONAL { ?e pc:sublimitAmount ?sublimit } OPTIONAL { ?e pc:deductiblePercent ?deductiblePct } OPTIONAL { ?e pc:deductibleMinimum ?deductibleMin }
  ?ap pc:approvalOfForm ?e ; pc:approvalStatus pcd:Approved ; pc:approvalInState ?st . ?st pc:stateCode ?stCode .
} GROUP BY ?exclusion ?restoringEndorsement ?sublimit ?deductiblePct ?deductibleMin   # one row per endorsement, states concatenated
```

Result: EXCL-FLD | MM-CP-E101 | 250000.0 | 5.0 | 25000.0 | TX, FL.

q08: is inference on? `pc:Endorsement rdfs:subClassOf pc:Form`, so asking for `?f a pc:Form` must return endorsements although no triple says so explicitly.

```sparql
SELECT ?f ?form ?assertedType WHERE {
  ?f a pc:Form ; pc:formNumber ?form ; a ?assertedType .         # ?f matched pc:Form through inference...
  FILTER(?assertedType IN (pc:PolicyForm, pc:Endorsement, pc:StateAmendatoryEndorsement))   # ...this is what was loaded
} ORDER BY ?form
```

Returns all 7 forms including the 5 endorsements. The companion q08b adds `FROM onto:explicit` (a GraphDB pseudo-graph that restricts a query to asserted statements) and returns 0 rows. `onto:explicit` is GraphDB-specific; the portable check is to compare with a repository created with ruleset `empty`.

Other queries: q03 the form x state approval matrix (12 rows), q04 where E310 and FL-01 are mandatory with territory factors, q05 clause counts per deontic type per document with average confidence, q06 obligations with deadlines and their exceptions side by side (12 rows, e.g. "MM-CM-CP-2025 1.1 | within 72 hours | unless the delay prejudiced our investigation"), q07 every rule with status, source clause, document, page and `overriddenBy` (R01 -> R02, R03 -> R04), q09 class codes, q10 the document cross-reference web, q11 clauses mentioning a given entity with citation fields (the template Graph RAG uses).

## Step 6: Graph RAG (`scripts/09_graph_rag.py`)

Retrieval combines three things and the answer must cite `[document | section | p.N]` for every statement.

```python
def answer(self, question):
    ents, soft = self.link_entities(question)          # 1. regex ids + ontology labels/altLabels + MiniLM nearest terms
    intent = self.intent(question, ents)               # 2. T1 endorsement availability | T2 peril coverage path | T3 duties & deadlines | T0 generic
    facts, queries = getattr(self, f"facts_{intent}")(ents)   # 3. SPARQL templates filled with the linked IRIs -> facts with provenance
    chunks = self.retrieve(question, ents)             # 4. cosine over pc:Chunk chunkText + 0.12 boost per linked entity the chunk pc:mentions
    prompt = self.build_prompt(question, facts, chunks)
    text = self.llm(prompt) or self.compose_offline(intent, question, facts, chunks)   # 5. LLM, or deterministic extractive composer
    return {"question": question, "mode": "llm" if ... else "offline-extractive", "facts": facts, "chunks": chunks, "answer": text}

def retrieve(self, question, ents, k=6):
    qv = self.emb.encode([question])[0]
    sims = self.chunk_vecs @ qv                                            # 113 chunks (90 clauses + tables), embedded once
    ent_iris = {e["iri"] for e in ents.values()}
    scored = [(float(sims[i]) + 0.12 * len(ent_iris & c["mentions"]), c) for i, c in enumerate(self.chunks)]
    return top_k(scored, k)
```

Where this sits relative to GraphDB's own features: the vector index here is in-process numpy so the POC has no extra moving parts. GraphDB offers the same hybrid pattern natively: Talk to Your Graph combines SPARQL, full-text search, similarity search and a ChatGPT retrieval connector ([GraphDB Talk to Your Graph](https://graphdb.ontotext.com/documentation/11.5/talk-to-graph.html)); the Similarity plugin provides text-embedding similarity over literals ([Graphwise, what is Graph RAG](https://graphwise.ai/fundamentals/what-is-graph-rag/)); and since 11.2 the Elasticsearch and OpenSearch connectors support vector search and a native Python client is available ([GraphDB 11.2 release notes](https://graphdb.ontotext.com/documentation/11.2/release-notes.html)). Swapping `retrieve()` for one of those is a one-function change.

Three questions, answered live (offline composer; the LLM mode uses the same facts and passages). Full text with retrieval traces in `output/09_graph_rag/answers.md`.

Q1. Which endorsements modify Coverage A (Building) and are approved for use in Texas?
Linked entities: TX, COV-A. Template T1.
Answer: Approved and available: MM-CP-E101 (Flood Coverage Endorsement - Scheduled Locations, Ed. 06/2025); MM-CP-E205 (Equipment Breakdown Endorsement, Ed. 01/2025); MM-CP-E310 (Windstorm or Hail Percentage Deductible, Ed. 03/2025); MM-CP-E415 (Protective Safeguards Endorsement, Ed. 01/2025). [MM-FILINGS-CP-2025 | filing table | p.1]
Not available: MM-CP-FL-01 (Florida Amendatory Endorsement, Ed. 07/2025) modifies COV-A; TX status: no filing in this state. [MM-CP-E-SERIES | Endorsement Availability Matrix | p.1]
Supporting passages: E310 3.4 "mandatory for risks located in Florida Tier 1 coastal counties and in Texas territory TX-T01" [MM-CP-E-SERIES | 3. MM-CP-E310 ... / 3.4 | p.2]; UW 4.3 [MM-UW-CP-2025 | SECTION 4 ... / 4.3 | p.3]; claims manual 2.1 "verify that the form edition and endorsements on the policy match the editions approved in the applicable State Filing" [MM-CM-CP-2025 | SECTION 2 ... / 2.1 | p.1].

Q2. A Florida policy has a scheduled location in flood zone AE. Is flood damage to the building covered, and what is required?
Linked entities: FL, COV-A, Flood, Location, FloodZone. Template T2.
Answer: Flood is removed from MM-CP-0010 by exclusion EXCL-FLD (Water), which lives in MM-CP-1030 and is pulled in by Section B.1. [MM-CP-0010 | SECTION B - EXCLUSIONS / B.1 | p.2]
MM-CP-E101 deletes EXCL-FLD and restores Flood for COV-A, COV-B; sublimit 250,000, deductible 5% (minimum 25,000); approved in TX, FL. [MM-CP-E-SERIES | 1-MM-CP-E101 / 1.2-1.4 | p.1]
Rule R01 (scoped): the flood exclusion does not apply when E101 is attached AND the location is scheduled under E101 AND the coverage is COV-A/COV-B; narrowed by R02 (Layer 5 precedence). [MM-CP-0010 | SECTION B / B.1 | p.2]
Rule R02 (active): E101 permits payment for Flood under those requirements. [MM-CP-E-SERIES | 1. MM-CP-E101 ... / 1.2 | p.1]
Rule R09 (active): a location in zone A/AE/V/VE must be scheduled under MM-CP-E101 unless a signed Flood Exclusion Acknowledgment is on file. [MM-UW-CP-2025 | SECTION 4 ... / 4.4 | p.3]
Supporting passages: claims manual 2.3 "If MM-CP-E101 is attached and the premises is a scheduled location, Flood damage to COV-A and COV-B is covered up to the Flood Sublimit of $250,000 subject to the 5% Flood Deductible; COV-D is not covered" [MM-CM-CP-2025 | SECTION 2 ... / 2.3 | p.1]; E101 1.2 and 1.3 [MM-CP-E-SERIES | ... / 1.2, 1.3 | p.1]; claims manual 2.2 [MM-CM-CP-2025 | ... / 2.2 | p.1].
So: yes, covered for the building (COV-A), up to $250,000, with a 5 percent deductible (minimum $25,000), provided E101 is attached and the location is on its schedule, which UW 4.4 requires for zone AE in any case.

Q3. What must the insured do after a loss, and how quickly must a Florida claim be acknowledged?
Linked entities: FL, Claim. Template T3.
Answer (condensed): The insured must give notice within 72 hours under MM-CP-0010 E.3(b); in Florida MM-CP-FL-01 5.3 extends this to 14 days, and late notice must not be used to deny a claim unless the delay prejudiced the investigation [MM-CM-CP-2025 | SECTION 1 - FNOL / 1.1 | p.1]. The insured must also notify the police if a law may have been broken, take reasonable steps to protect the property from further damage, submit a signed, sworn proof of loss within 60 days of request, and cooperate with the investigation [MM-CP-0010 | SECTION E - LOSS CONDITIONS / E.3 | p.3] [MM-CM-CP-2025 | SECTION 4 / 4.1 | p.3]. The adjuster must acknowledge receipt of every claim in writing within 14 calendar days in Florida (15 business days in Texas) [MM-CM-CP-2025 | SECTION 1 / 1.2 | p.1], which is also a condition of the Florida filing approval [MM-FILINGS-CP-2025 | FILING 1 - FLORIDA / 1.3 | p.1]. Rules: R03 (72 hours) is scoped to non-Florida claims by R04 (FL 14 days); R12 (acknowledge within 14 days, FL) is active.

What to notice: the structured part answers "which" and "how much" exactly and explains precedence; the passages supply the wording and the page; the citation format is identical for both, so a reviewer can open the PDF at the page.

## Step 7: validation and demo

Test plan (`scripts/11_run_tests.py`, 44 assertions, all passing on the recorded run; report in `output/11_test_report.md`):

| Area | Checks | Success criterion |
|---|---|---|
| L1 parsing | 6 PDFs exist with 2-3 pages; each yields >= 5 clauses; E415 4.2 exception retained as child; availability matrix lifted | all pass |
| L2 classification | E.3 = Obligation, D.1 = Prohibition, A.1 = Permission; pass-2 share < 40 percent (30 percent) | all pass |
| L3 grounding | B.1 hard-grounded to EXCL-FLD and COV-A; exactly 3 soft terms | pass |
| L4 compiler | 12 compiled, 0 rejected; one shape file per rule; R08 cross-document warning present | pass |
| L5 conflicts | R01 scoped by R02 (lex specialis); R03 scoped by R04; R02/R11 compatible; R01 carve-out is conjunctive | pass |
| SHACL gate 1 | generated graph conforms; bad records >= 8 results (10); fixed records conform | pass |
| GraphDB | 5 data graphs + 23 node shapes in shapes graph; q01 = E101/E205/E310/E415; inference returns endorsements as Form; explicit-only returns 0; bad commit 500, fixed 204 | pass |
| Graph RAG | each answer has >= 3 citations in `[doc | section | p.N]` form and names the expected entities/values | pass |
| L6 enforcement | coastal bind rejected with R07/R08/R09 to Underwriter; unscheduled flood FNOL rejected with R01 to Adjuster; clean TX bind accepted | pass |

Layer 6 demo (`scripts/10_enforce_live_record.py`), live output:

```
validation engine: GraphDB ShaclSail (commit-time)
[Bind] POL-FL-0100: 16 triples -> REJECTED (3 alerts)   # Coastal FL bind with no FL-01, no E310, flood zone AE not scheduled
   -> Underwriter  R07  policy/POL-FL-0100   Florida policies must include MM-CP-FL-01 Florida Amendatory Endorsement (MM-UW-CP-2025 4.2).
   -> Underwriter  R08  policy/POL-FL-0100   MM-CP-E310 is mandatory for locations in FL Tier 1 coastal counties (FL-T03) and TX-T01 (MM-UW-CP-2025 4.3).
   -> Underwriter  R09  location/LOC-0100    A location in flood zone A/AE/V/VE must be scheduled under MM-CP-E101 unless a Flood Exclusion Acknowledgment ...
[FNOL] CLM-0200: 13 triples -> REJECTED (2 alerts)      # Flood claim at an UNscheduled location on the valid FL policy
   -> Adjuster     R01  claim/CLM-0200       Flood is excluded (EXCL-FLD, MM-CP-1030 B.1.g via MM-CP-0010 Section B.1). Check for a restoring endorsement.
   -> Adjuster     R02  claim/CLM-0200       MM-CP-E101 restores Flood only for scheduled locations and only for COV-A / COV-B ...
[Bind] POL-TX-0300: 18 triples -> ACCEPTED (0 alerts)   # Clean TX bind
   cleanup of accepted record -> HTTP 204
```

Demo script for a 15-minute walkthrough: (1) open a PDF and the matching clause JSON side by side, point at an exception node; (2) show `_summary.json` and one pass-2 clause; (3) show the R02 typed JSON, its DSL line and its compiled shape; (4) show `decisions.json`, then the scoped R01 DSL; (5) in GraphDB Workbench run q01, q02, q08; (6) run `08_graphdb_load.py` and show the HTTP 500 report; (7) run `09_graph_rag.py` with a new question; (8) run `10_enforce_live_record.py` and read the alerts; (9) run `11_run_tests.py`.

What success looks like for the POC: every rule in the graph is traceable to a page; a wrong record cannot be committed and the rejection names the clause; the same question answered by SPARQL and by retrieval agrees; the test script is green after a clean rebuild (`./run_all.sh`).

---

# Project folder and run order

```
pc-graphrag-poc/
  GUIDE.md  README.md  requirements.txt  run_all.sh
  config/   graphdb-repo-config.ttl  typed_rules_seed.json
  ontology/ pc_ontology.ttl
  shapes/   core_shapes.ttl  compiled/R01..R12.ttl  compiled/active_shapes.ttl
  queries/  _prefixes.rq  q01..q11.rq (+ q08b)
  docs/     rml_example.ttl
  scripts/  common.py  rulec.py  graphdb_client.py
            00_generate_source_pdfs.py  01_parse_clause_tree.py  02_classify_deontic.py  03_ground_ontology.py
            04_compile_rules.py  05_resolve_conflicts.py  06_build_rdf.py  07_validate_shacl_local.py
            08_graphdb_load.py  09_graph_rag.py  10_enforce_live_record.py  11_run_tests.py
  sources/  six PDFs
  output/   01_clause_tree/ 02_classified/ 03_grounded/ 04_rules/ 05_active_rules/ 06_rdf/ 07_validation/
            08_graphdb/ 09_graph_rag/ 10_alerts/ 11_test_report.md
```

Run order (tick as you go):

1. `pip install -r requirements.txt` (Python 3.11+).
2. Start GraphDB: `docker run -d -p 7200:7200 ontotext/graphdb:10.8.11` (or a local distribution). Check http://localhost:7200.
3. `python scripts/00_generate_source_pdfs.py` -> `sources/*.pdf`
4. `python scripts/01_parse_clause_tree.py` -> `output/01_clause_tree/`
5. `python scripts/02_classify_deontic.py` -> `output/02_classified/`
6. `python scripts/03_ground_ontology.py` -> `output/03_grounded/` (first run downloads MiniLM, ~90 MB; falls back to TF-IDF offline)
7. `python scripts/04_compile_rules.py` -> `output/04_rules/`, `shapes/compiled/`
8. `python scripts/05_resolve_conflicts.py` -> `output/05_active_rules/`, `shapes/compiled/active_shapes.ttl`
9. `python scripts/06_build_rdf.py` -> `output/06_rdf/`
10. `python scripts/07_validate_shacl_local.py` -> `output/07_validation/` (expect True / False / True)
11. `python scripts/08_graphdb_load.py --reset` -> repository `pc-poc`, `output/08_graphdb/`
12. `python scripts/09_graph_rag.py` -> `output/09_graph_rag/answers.md`
13. `python scripts/10_enforce_live_record.py` -> `output/10_alerts/`
14. `python scripts/11_run_tests.py` -> expect `44 passed, 0 failed`

Or `./run_all.sh` for all of it. Environment variables: `GRAPHDB_URL`, `GRAPHDB_REPO`, optional `OPENAI_API_KEY` / `OPENAI_MODEL`.

---

# From POC to production (what would change)

Security
- Enable GraphDB security, create roles per named graph (read for RAG, write for the pipeline, admin for shapes), put the Workbench and REST behind SSO and TLS.
- Keep the shapes graph write-protected; changes only via the Layer 4/5 pipeline with code review.
- Secrets (LLM keys, DB credentials) in a vault; no keys in scripts or env files in the repo.

Scale and reliability
- Replace pdfplumber with Docling or Marker and run Layer 1 as a batch job; store clause trees in object storage with document version and hash.
- Replace the lexical scorer with a small fine-tuned classifier; keep the gate and measure pass-2 share and human-review share.
- Move vector retrieval into the GraphDB Similarity plugin or an Elasticsearch/OpenSearch connector; cache SPARQL templates.
- Use the Layer 6 design as drawn: Debezium CDC -> Kafka -> RML virtualization -> ShaclSail commit or a per-record validation service; a GraphDB cluster for availability; `parallelValidation` on and violation logging off in production.
- Load reference data with the GraphDB bulk loader; keep clause and chunk graphs separate from operational graphs so re-indexing documents never touches policies.

Governance
- Version everything that defines meaning: ontology, shapes, typed-rule seeds, precedence table, embedding model, prompts. Tag the repository with the versions used for every load.
- Human review queue for pass-2 and low-confidence clauses, for rules with grounding warnings (the R08 case), and for every Layer 5 decision; sign-off recorded as PROV activities in the graph.
- A versioned SME question baseline (15-20 questions with expected entities, values and citations) run as regression on every change, as in your institutional-knowledge design.
- Legal review of the precedence rules; they encode how the carrier reads its own forms.

Monitoring
- Pipeline metrics: clauses per document, gatekeeper drop rate, pass-2 share, grounding coverage (clauses with at least one hard link), compile rejections, conflicts per release.
- Runtime metrics: commit rejections per checkpoint and per rule, alert volume per owner, time to acknowledge, false-positive rate from reviewer feedback; RAG citation coverage (sentences with a citation) and answer agreement between SPARQL facts and LLM text.
- Alerting on shape-set changes, inference count drift after loads, and GraphDB validation latency.
