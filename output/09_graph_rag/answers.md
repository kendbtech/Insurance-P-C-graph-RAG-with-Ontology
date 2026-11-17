# Graph RAG answers

## Q: Which endorsements modify Coverage A (Building) and are approved for use in Texas?
mode: offline-extractive | intent template: T1 | linked entities: TX, COV-A, Coverage, Approved

Approved and available: MM-CP-E101 (Flood Coverage Endorsement - Scheduled Locations, Ed. 06/2025); MM-CP-E205 (Equipment Breakdown Endorsement, Ed. 01/2025); MM-CP-E310 (Windstorm or Hail Percentage Deductible, Ed. 03/2025); MM-CP-E415 (Protective Safeguards Endorsement, Ed. 01/2025). [MM-FILINGS-CP-2025 | filing table | p.1]
Not available: MM-CP-FL-01 (Florida Amendatory Endorsement, Ed. 07/2025) modifies COV-A; TX status: no filing in this state. [MM-CP-E-SERIES | Endorsement Availability Matrix | p.1]
Supporting passages:
- "3.4 This endorsement is mandatory for risks located in Florida Tier 1 coastal counties and in Texas territory TX-T01 per Underwriting Guideline MM-UW-CP-2025 Section 4.3." [MM-CP-E-SERIES | 3. MM-CP-E310 - WINDSTORM OR HAIL PERCENTAGE DEDUCTIBLE (Ed. 03/2025) / 3.4 | p.2]
- "4.3 MM-CP-E310 Windstorm or Hail Percentage Deductible is mandatory for all locations in Florida Tier 1 coastal counties and in Texas rating territory TX-T01; a 5% deductible is required within one mile of the coast and 2% elsewhere in those territories." [MM-UW-CP-2025 | SECTION 4 - REQUIRED ENDORSEMENTS AND FORMS / 4.3 | p.3]
- "1.1 This endorsement modifies insurance provided under MM-CP-0010 and MM-CP-1030. It applies only to the scheduled locations listed in the Schedule below and to Coverages COV-A (Building) and COV-B (Your Business Personal Property)." [MM-CP-E-SERIES | 1. MM-CP-E101 - FLOOD COVERAGE ENDORSEMENT - SCHEDULED LOCATIONS (Ed. 06/2025) / 1.1 | p.1]
- "2.1 The adjuster must verify that the form edition and endorsements on the policy match the editions approved in the applicable State Filing before issuing any coverage position." [MM-CM-CP-2025 | SECTION 2 - COVERAGE VERIFICATION / 2.1 | p.1]

<details><summary>retrieval trace</summary>

Top chunks: MM-CP-E-SERIES 3.4 p.2 (score 0.722); MM-UW-CP-2025 4.3 p.3 (score 0.673); MM-CP-E-SERIES 1.1 p.1 (score 0.651); MM-CM-CP-2025 2.1 p.1 (score 0.615); MM-CP-0010 G.1 p.3 (score 0.608); MM-CP-E-SERIES 5.5 p.3 (score 0.593)

Nearest ontology terms: Coverage A - Building (0.558), Coverage (0.515), State Amendatory Endorsement (0.477)
</details>

## Q: A Florida policy has a scheduled location in flood zone AE. Is flood damage to the building covered, and what is required?
mode: offline-extractive | intent template: T2 | linked entities: FL, COV-A, Flood, Obligation, Policy, Location, FloodZone

Flood is removed from MM-CP-0010 by exclusion EXCL-FLD (Water (flood, surface water, overflow)), which lives in MM-CP-1030 and is pulled in by Section B.1. [MM-CP-0010 | SECTION B - EXCLUSIONS / B.1 | p.2]
MM-CP-E101 (Flood Coverage Endorsement - Scheduled Locations) deletes EXCL-FLD and restores Flood for COV-A, COV-B; sublimit 250,000, deductible 5% (minimum 25,000); approved in TX, FL. [MM-CP-E-SERIES | 1-MM-CP-E101 / 1.2-1.4 | p.1]
Rule R01 (scoped): PROHIBITION Claim pay_for_loss Peril:Flood WHEN Claim.onPolicy.hasForm = MM-CP-0010 SOURCE MM-CP-0010#SECTION-B/B.1 UNLESS Claim.onPolicy.hasEndorsement = MM-CP-E101 AND Claim.atLocation.scheduledUnder = MM-CP-E101 AND Claim.affectsCoverage IN (COV-A, COV-B) - narrowed/scoped by R02 (Layer 5 precedence). [MM-CP-0010 | SECTION B - EXCLUSIONS AND LIMITATIONS / B.1 | p.2]
Rule R02 (active): PERMISSION Claim pay_for_loss Peril:Flood WHEN Claim.causeOfLoss = Flood WHEN Claim.onPolicy.hasEndorsement = MM-CP-E101 REQUIRES Claim.atLocation.scheduledUnder = MM-CP-E101 REQUIRES Claim.affectsCoverage IN (COV-A, COV-B) SOURCE MM-CP-E-SERIES#1-MM-CP-E101/1.2. [MM-CP-E-SERIES | 1. MM-CP-E101 - FLOOD COVERAGE ENDORSEMENT - SCHEDULED LOCATIONS (Ed. 06/2025) / 1.2 | p.1]
Rule R09 (active): OBLIGATION Location schedule_location Endorsement:MM-CP-E101 WHEN Location.inFloodZone IN (A, AE, V, VE) UNLESS Location.^hasLocation.floodAcknowledgmentSigned = true SOURCE MM-UW-CP-2025#SECTION-4/4.4. [MM-UW-CP-2025 | SECTION 4 - REQUIRED ENDORSEMENTS AND FORMS / 4.4 | p.3]
Supporting passages:
- "2.3 If MM-CP-E101 is attached and the premises is a scheduled location, Flood damage to COV-A and COV-B is covered up to the Flood Sublimit of $250,000 subject to the 5% Flood Deductible; COV-D is not covered unless the Schedule shows a COV-D Flood Sublimit." [MM-CM-CP-2025 | SECTION 2 - COVERAGE VERIFICATION / 2.3 | p.1]
- "1.2 Coverage Grant. Exclusion EXCL-FLD (Water) in Section B.1.g of MM-CP-1030 is deleted with respect to the peril of Flood for the scheduled locations. We will pay for direct physical loss of or damage to Covered Property at a scheduled location caused by Flo..." [MM-CP-E-SERIES | 1. MM-CP-E101 - FLOOD COVERAGE ENDORSEMENT - SCHEDULED LOCATIONS (Ed. 06/2025) / 1.2 | p.1]
- "1.3 Flood Deductible. A deductible of 5% of the Limit of Insurance for COV-A at the scheduled location applies to each Flood occurrence, but not less than $25,000. This deductible replaces the deductible in Section D of MM-CP-0010 for the peril of Flood only." [MM-CP-E-SERIES | 1. MM-CP-E101 - FLOOD COVERAGE ENDORSEMENT - SCHEDULED LOCATIONS (Ed. 06/2025) / 1.3 | p.1]
- "2.2 For any loss involving water, the adjuster must determine whether the cause of loss is Flood as excluded by EXCL-FLD in MM-CP-1030 Section B.1.g, and then check whether MM-CP-E101 is attached and whether the damaged premises is a scheduled location under t..." [MM-CM-CP-2025 | SECTION 2 - COVERAGE VERIFICATION / 2.2 | p.1]

<details><summary>retrieval trace</summary>

Top chunks: MM-CM-CP-2025 2.3 p.1 (score 0.856); MM-CP-E-SERIES 1.2 p.1 (score 0.789); MM-CP-E-SERIES 1.3 p.1 (score 0.747); MM-CM-CP-2025 2.2 p.1 (score 0.733); MM-CM-CP-2025 2.4 p.1 (score 0.704); MM-UW-CP-2025 5.3 p.3 (score 0.689)

Nearest ontology terms: FEMA Flood Zone (0.543), Insured Location (0.476), Flood (0.452)
</details>

## Q: What must the insured do after a loss, and how quickly must a Florida claim be acknowledged?
mode: offline-extractive | intent template: T3 | linked entities: FL, Claim

MM-CM-CP-2025 1.1: 1.1 The insured is required by MM-CP-0010 Section E.3(b) to report loss within 72 hours of becoming aware of it; in Florida, MM-CP-FL-01 Section 5.3 extends this period to 14 days. Late notice must not be used to deny a ... (deadline: within 72 hours) EXCEPTION: unless the delay prejudiced our investigation. [MM-CM-CP-2025 | SECTION 1 - FIRST NOTICE OF LOSS (FNOL) / 1.1 | p.1]
MM-CM-CP-2025 1.2: 1.2 The adjuster must acknowledge receipt of every claim in writing within 14 calendar days in Florida and within 15 business days in Texas, per the applicable state claims-handling requirements referenced in Filings MM-... (deadline: within 14 calendar days) [MM-CM-CP-2025 | SECTION 1 - FIRST NOTICE OF LOSS (FNOL) / 1.2 | p.1]
MM-CM-CP-2025 3.2: 3.2 Initial reserves must be set within 5 business days of FNOL and reviewed every 30 days. (deadline: within 5 business days) [MM-CM-CP-2025 | SECTION 3 - RESERVES AND AUTHORITY / 3.2 | p.3]
MM-CM-CP-2025 4.1: 4.1 Under MM-CP-0010 Section E.3(d) the insured must submit a signed, sworn proof of loss within 60 days of our request. The adjuster may extend this period in writing. (deadline: within 60 days) [MM-CM-CP-2025 | SECTION 4 - PROOF OF LOSS AND PAYMENT / 4.1 | p.3]
MM-CM-CP-2025 4.2: 4.2 Under Section E.4 we must state our coverage position within 30 days of receiving the proof of loss and pay undisputed amounts within 30 days. (deadline: within 30 days) [MM-CM-CP-2025 | SECTION 4 - PROOF OF LOSS AND PAYMENT / 4.2 | p.3]
MM-CM-CP-2025 5.2: 5.2 For fire losses at premises with MM-CP-E415, the adjuster must obtain evidence that the scheduled protective safeguards were operational, or that any impairment was reported to us within 48 hours. (deadline: within 48 hours) [MM-CM-CP-2025 | SECTION 5 - VACANCY AND PROTECTIVE SAFEGUARDS / 5.2 | p.3]
MM-CM-CP-2025 6.2: 6.2 Salvage must be offered for sale within 30 days of payment where the recovery is expected to exceed $2,500. (deadline: within 30 days) [MM-CM-CP-2025 | SECTION 6 - SUBROGATION AND SALVAGE / 6.2 | p.3]
MM-CP-0010 E.3: E.3 Duties In The Event Of Loss Or Damage. You must see that the following are done in the event of loss or damage to Covered Property: (a) Notify the police if a law may have been broken. (b) Give us prompt notice of th... (deadline: within 60 days) [MM-CP-0010 | SECTION E - LOSS CONDITIONS / E.3 | p.3]
Rule R03 (scoped): OBLIGATION Claim report_loss NONE WITHIN 72 hours SOURCE MM-CP-0010#SECTION-E/E.3 WHEN Claim.onPolicy.inState != FL - narrowed/scoped by R04 (Layer 5 precedence). [MM-CP-0010 | SECTION E - LOSS CONDITIONS / E.3 | p.3]
Rule R04 (active): OBLIGATION Claim report_loss NONE WHEN Claim.onPolicy.inState = FL WITHIN 14 days SOURCE MM-CP-E-SERIES#5-MM-CP-FL-01/5.3. [MM-CP-E-SERIES | 5. MM-CP-FL-01 - FLORIDA AMENDATORY ENDORSEMENT (Ed. 07/2025) / 5.3 | p.3]
Rule R12 (active): OBLIGATION Claim acknowledge_claim NONE WHEN Claim.onPolicy.inState = FL WITHIN 14 days SOURCE MM-CM-CP-2025#SECTION-1/1.2. [MM-CM-CP-2025 | SECTION 1 - FIRST NOTICE OF LOSS (FNOL) / 1.2 | p.1]
Supporting passages:
- "1.1 The insured is required by MM-CP-0010 Section E.3(b) to report loss within 72 hours of becoming aware of it; in Florida, MM-CP-FL-01 Section 5.3 extends this period to 14 days. Late notice must not be used to deny a claim unless the delay prejudiced our in..." [MM-CM-CP-2025 | SECTION 1 - FIRST NOTICE OF LOSS (FNOL) / 1.1 | p.1]
- "1.2 The adjuster must acknowledge receipt of every claim in writing within 14 calendar days in Florida and within 15 business days in Texas, per the applicable state claims-handling requirements referenced in Filings MM-FL-2025-0142 and MM-TX-2025-0098." [MM-CM-CP-2025 | SECTION 1 - FIRST NOTICE OF LOSS (FNOL) / 1.2 | p.1]
- "4.1 Under MM-CP-0010 Section E.3(d) the insured must submit a signed, sworn proof of loss within 60 days of our request. The adjuster may extend this period in writing." [MM-CM-CP-2025 | SECTION 4 - PROOF OF LOSS AND PAYMENT / 4.1 | p.3]
- "1.3 Conditions of approval: MM-CP-FL-01 Florida Amendatory Endorsement must be attached to every Florida policy; MM-CP-E310 must display the hurricane deductible in dollars and percent; the insurer must acknowledge claims within 14 calendar days." [MM-FILINGS-CP-2025 | FILING 1 - FLORIDA (FL) - MM-FL-2025-0142 / 1.3 | p.1]

<details><summary>retrieval trace</summary>

Top chunks: MM-CM-CP-2025 1.1 p.1 (score 0.823); MM-CM-CP-2025 1.2 p.1 (score 0.783); MM-CM-CP-2025 4.1 p.3 (score 0.655); MM-FILINGS-CP-2025 1.3 p.1 (score 0.612); MM-CP-0010 E.4 p.3 (score 0.611); MM-CM-CP-2025 4.2 p.3 (score 0.585)

Nearest ontology terms: Claim (0.605), Coverage (0.456), Claims Manual (0.373)
</details>
