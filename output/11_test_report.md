| check | result | detail |
|---|---|---|
| L1 PDF 01_policy_form_MM-CP-0010.pdf exists with 2-3 pages | PASS | 3 pages |
| L1 MM-CP-0010 yields clauses | PASS |  |
| L1 PDF 02_endorsements_MM-CP-E-series.pdf exists with 2-3 pages | PASS | 3 pages |
| L1 MM-CP-E-SERIES yields clauses | PASS |  |
| L1 PDF 03_underwriting_guidelines_MM-UW-CP-2025.pdf exists with 2-3 pages | PASS | 3 pages |
| L1 MM-UW-CP-2025 yields clauses | PASS |  |
| L1 PDF 04_rate_manual_MM-RM-CP-2025.pdf exists with 2-3 pages | PASS | 3 pages |
| L1 MM-RM-CP-2025 yields clauses | PASS |  |
| L1 PDF 05_claims_manual_MM-CM-CP-2025.pdf exists with 2-3 pages | PASS | 3 pages |
| L1 MM-CM-CP-2025 yields clauses | PASS |  |
| L1 PDF 06_state_filings_MM-2025.pdf exists with 2-3 pages | PASS | 2 pages |
| L1 MM-FILINGS-CP-2025 yields clauses | PASS |  |
| L1 exception kept with parent (E415 4.2 'except when ... maintenance') | PASS |  |
| L1 tables lifted (endorsement availability matrix present) | PASS |  |
| L2 E.3 duties clause = Obligation | PASS |  |
| L2 D.1 exclusion/limit clause = Prohibition | PASS |  |
| L2 A.1 coverage grant = Permission | PASS |  |
| L2 pass-2 adjudication share < 40 % | PASS | 30% |
| L3 B.1 hard-grounded to EXCL-FLD and COV-A | PASS | COV-A, COV-B, COV-C, COV-D, EXCL-EQ, EXCL-FLD, EXCL-MOLD, EXCL-WAR, EXCL-WEAR, E |
| L3 soft grounding returns top-3 | PASS |  |
| L4 12 rules compiled, 0 rejected | PASS |  |
| L4 one shape file per rule | PASS |  |
| L4 R08 carries cross-document identifier warning (FL-T03) | PASS |  |
| L5 R01 (flood exclusion) narrowed by R02 (E101 grant), lex specialis | PASS |  |
| L5 R03 (72 h) scoped by R04 (FL 14 days) | PASS |  |
| L5 R02 vs R11 (vacancy) judged compatible | PASS |  |
| L5 scoped R01 DSL has conjunctive UNLESS carve-out | PASS |  |
| SHACL generated graph conforms (pySHACL) | PASS |  |
| SHACL bad records produce >= 8 results | PASS | 10 results |
| SHACL fixed records conform | PASS |  |
| GraphDB 5 named graphs + ShaclSail shapes graph present | PASS | 5 data graphs, 23 node shapes |
| GraphDB q01 = E101, E205, E310, E415 | PASS | MM-CP-E101, MM-CP-E205, MM-CP-E310, MM-CP-E415 |
| GraphDB inference: endorsements returned as pc:Form | PASS |  |
| GraphDB q08b explicit-only returns 0 rows | PASS |  |
| GraphDB ShaclSail rejected bad commit (HTTP 500) and accepted fix (204) | PASS |  |
| RAG answer cites sources: Which endorsements modify Coverage A (Buildin... | PASS | 6 citations, mode offline-extractive |
| RAG answer names expected entities ['MM-CP-E101', 'MM-CP-E205']... | PASS |  |
| RAG answer cites sources: A Florida policy has a scheduled location in ... | PASS | 9 citations, mode offline-extractive |
| RAG answer names expected entities ['EXCL-FLD', 'MM-CP-E101']... | PASS |  |
| RAG answer cites sources: What must the insured do after a loss, and ho... | PASS | 15 citations, mode offline-extractive |
| RAG answer names expected entities ['14 calendar days', '72 hours']... | PASS |  |
| L6 coastal FL bind rejected -> R07,R08,R09 to Underwriter | PASS |  |
| L6 unscheduled flood FNOL -> R01 to Adjuster | PASS |  |
| L6 clean TX bind accepted, 0 alerts | PASS |  |