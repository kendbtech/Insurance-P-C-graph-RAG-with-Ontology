#!/usr/bin/env python3
"""
00_generate_source_pdfs.py  (Task 2)

Generates six SYNTHETIC P&C source documents as PDFs (2-3 pages each).
Carrier, forms, codes, people and numbers are fictional.

Cross-referenceable identifiers used across all six documents:
  Forms ........ MM-CP-0010, MM-CP-1030, MM-CP-E101, MM-CP-E205, MM-CP-E310, MM-CP-E415, MM-CP-FL-01
  Coverages .... COV-A (Building), COV-B (Business Personal Property),
                 COV-C (Personal Property of Others), COV-D (Business Income)
  Exclusions ... EXCL-FLD, EXCL-EQ, EXCL-WAR, EXCL-MOLD, EXCL-WEAR
  States ....... FL, TX, NY
  Filings ...... MM-FL-2025-0142, MM-TX-2025-0098, MM-NY-2025-0211
  Rating ....... territories FL-T03, TX-T01, NY-T07 ; construction classes CC1..CC6 ; protection classes PC1..PC10
  Class codes .. 0511 (prohibited), 0921 (refer), 0745 (eligible)

Run:  python scripts/00_generate_source_pdfs.py
Out:  sources/*.pdf
"""
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sources"
OUT.mkdir(exist_ok=True)

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=15, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("BODY", parent=styles["BodyText"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=8, textColor=colors.grey)
CELL = ParagraphStyle("CELL", parent=BODY, fontSize=8.5, leading=11)


def table(rows, col_widths=None):
    data = [[Paragraph(str(c), CELL) for c in r] for r in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F9")]),
    ]))
    return t


def build(filename, title, subtitle, header_meta, blocks):
    """blocks: list of ('h2', text) | ('p', text) | ('table', rows, widths) | ('pb',)"""
    doc = SimpleDocTemplate(str(OUT / filename), pagesize=LETTER,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            title=title, author="Meridian Mutual Insurance Company (fictional)")
    story = [Paragraph(title, H1), Paragraph(subtitle, BODY), Spacer(1, 4)]
    story.append(table([["Field", "Value"]] + header_meta, [1.8 * inch, 4.6 * inch]))
    story.append(Paragraph("SYNTHETIC DOCUMENT FOR TRAINING AND TESTING. Not a real insurance form. "
                           "Carrier, forms, codes and figures are fictional.", SMALL))
    story.append(Spacer(1, 8))
    for b in blocks:
        if b[0] == "h2":
            story.append(Paragraph(b[1], H2))
        elif b[0] == "p":
            story.append(Paragraph(b[1], BODY))
            story.append(Spacer(1, 3))
        elif b[0] == "table":
            story.append(table(b[1], b[2] if len(b) > 2 else None))
            story.append(Spacer(1, 6))
        elif b[0] == "pb":
            story.append(PageBreak())
    doc.build(story)
    print("wrote", OUT / filename)


# --------------------------------------------------------------------------- 1
def policy_form():
    build("01_policy_form_MM-CP-0010.pdf",
          "Building and Personal Property Coverage Form",
          "Meridian Mutual Insurance Company (fictional). Commercial Property Line of Business.",
          [["Form Number", "MM-CP-0010"], ["Edition Date", "01/2025"],
           ["Line of Business", "Commercial Property (CP)"],
           ["Companion Form", "MM-CP-1030 Causes of Loss - Special Form (Ed. 01/2025)"],
           ["Approved States", "FL (Filing MM-FL-2025-0142), TX (Filing MM-TX-2025-0098)"]],
          [
              ("h2", "SECTION A - COVERAGE"),
              ("p", "A.1 Insuring Agreement. We will pay for direct physical loss of or damage to Covered Property "
                    "at the premises described in the Declarations caused by or resulting from any Covered Cause of Loss. "
                    "Covered Causes of Loss are defined in the Causes of Loss form MM-CP-1030 attached to this policy."),
              ("p", "A.2 Covered Property. Covered Property, as used in this Coverage Part, means the type of property "
                    "described in this section and limited in A.3 Property Not Covered, if a Limit of Insurance is shown "
                    "in the Declarations for that type of property."),
              ("table", [["Coverage Code", "Coverage Name", "Description", "Default Deductible"],
                         ["COV-A", "Building", "The building or structure described in the Declarations, including completed additions, fixtures, permanently installed machinery and equipment.", "$2,500"],
                         ["COV-B", "Your Business Personal Property", "Furniture, fixtures, machinery, stock and all other personal property owned by you and used in your business, located in or within 100 feet of the described premises.", "$2,500"],
                         ["COV-C", "Personal Property of Others", "Personal property of others that is in your care, custody or control and located in or within 100 feet of the described premises.", "$2,500"],
                         ["COV-D", "Business Income and Extra Expense", "Actual loss of Business Income you sustain due to the necessary suspension of operations during the period of restoration.", "72-hour waiting period"]],
               [0.9 * inch, 1.5 * inch, 3.0 * inch, 1.0 * inch]),
              ("p", "A.3 Property Not Covered. Covered Property does not include: (a) accounts, bills, currency, deeds, "
                    "money or securities; (b) land, water, growing crops or lawns; (c) vehicles or self-propelled machines "
                    "that are licensed for use on public roads, except vehicles you manufacture, process or warehouse; "
                    "(d) the cost to research, replace or restore the information on valuable papers and records, except "
                    "as provided in the Coverage Extensions."),
              ("p", "A.4 Additional Coverages. Debris Removal: We will pay your expense to remove debris of Covered Property "
                    "caused by a Covered Cause of Loss, subject to a limit of 25% of the amount we pay for the direct physical "
                    "loss plus the deductible. Preservation of Property: If it is necessary to move Covered Property to "
                    "preserve it from loss, we will pay for any direct physical loss while it is being moved or stored at "
                    "another location for up to 30 days."),
              ("h2", "SECTION B - EXCLUSIONS AND LIMITATIONS"),
              ("p", "B.1 See the applicable Causes of Loss form MM-CP-1030 for exclusions and limitations. The exclusions "
                    "EXCL-FLD (Water), EXCL-EQ (Earth Movement), EXCL-WAR (War and Military Action), EXCL-MOLD (Fungus, Wet "
                    "Rot and Bacteria) and EXCL-WEAR (Wear and Tear) apply to Coverages COV-A, COV-B, COV-C and COV-D unless an "
                    "endorsement attached to this policy states otherwise."),
              ("h2", "SECTION C - LIMITS OF INSURANCE"),
              ("p", "C.1 The most we will pay for loss or damage in any one occurrence is the applicable Limit of Insurance "
                    "shown in the Declarations. C.2 The limits applicable to the Coverage Extensions and the Additional "
                    "Coverages are in addition to the Limits of Insurance, except Preservation of Property."),
              ("h2", "SECTION D - DEDUCTIBLE"),
              ("p", "D.1 We will not pay for loss or damage in any one occurrence until the amount of loss or damage exceeds "
                    "the Deductible shown in the Declarations. We will then pay the amount of loss or damage in excess of the "
                    "Deductible, up to the applicable Limit of Insurance. D.2 Where a percentage deductible endorsement such as "
                    "MM-CP-E310 is attached, the percentage deductible replaces the flat deductible for the peril named in that endorsement."),
              ("pb",),
              ("h2", "SECTION E - LOSS CONDITIONS"),
              ("p", "E.1 Abandonment. There can be no abandonment of any property to us."),
              ("p", "E.2 Appraisal. If we and you disagree on the value of the property or the amount of loss, either may "
                    "make written demand for an appraisal of the loss. Each party will select a competent and impartial "
                    "appraiser within 20 days of the demand."),
              ("p", "E.3 Duties In The Event Of Loss Or Damage. You must see that the following are done in the event of loss "
                    "or damage to Covered Property: (a) Notify the police if a law may have been broken. (b) Give us prompt "
                    "notice of the loss or damage, and in no event later than 72 hours after you become aware of it, including "
                    "a description of the property involved. (c) Take all reasonable steps to protect the Covered Property from "
                    "further damage. (d) Send us a signed, sworn proof of loss containing the information we request within 60 "
                    "days after our request. (e) Cooperate with us in the investigation or settlement of the claim, and permit "
                    "us to inspect the property and examine your books and records."),
              ("p", "E.4 Loss Payment. We will give notice of our intentions within 30 days after we receive the sworn proof of "
                    "loss. We will pay for covered loss or damage within 30 days after we receive the sworn proof of loss, if "
                    "you have complied with all of the terms of this Coverage Part and we have reached agreement with you on "
                    "the amount of loss, or an appraisal award has been made."),
              ("p", "E.5 Vacancy. If the building where loss or damage occurs has been vacant for more than 60 consecutive days "
                    "before that loss or damage occurs, we will not pay for any loss or damage caused by vandalism, sprinkler "
                    "leakage, building glass breakage, water damage, theft or attempted theft. With respect to Covered Causes "
                    "of Loss other than those listed, we will reduce the amount we would otherwise pay by 15%."),
              ("h2", "SECTION F - ADDITIONAL CONDITIONS"),
              ("p", "F.1 Coinsurance. If a Coinsurance percentage is shown in the Declarations and the value of Covered Property "
                    "at the time of loss times the Coinsurance percentage is greater than the Limit of Insurance, we will pay "
                    "only the proportion of the loss that the Limit of Insurance bears to the required amount."),
              ("p", "F.2 Mortgageholders. We will pay for covered loss of or damage to buildings to each mortgageholder shown in "
                    "the Declarations in their order of precedence."),
              ("h2", "SECTION G - OPTIONAL COVERAGES AND ENDORSEMENTS"),
              ("p", "G.1 The following endorsements may be attached to this form when shown in the Declarations: MM-CP-E101 "
                    "Flood Coverage Endorsement - Scheduled Locations; MM-CP-E205 Equipment Breakdown Endorsement; MM-CP-E310 "
                    "Windstorm or Hail Percentage Deductible; MM-CP-E415 Protective Safeguards Endorsement. State amendatory "
                    "endorsements such as MM-CP-FL-01 (Florida) are attached automatically where required by the state filing."),
              ("h2", "SECTION H - DEFINITIONS"),
              ("p", "H.1 'Occurrence' means an accident, including continuous or repeated exposure to substantially the same "
                    "general harmful conditions. H.2 'Period of restoration' means the period that begins 72 hours after the "
                    "time of direct physical loss and ends on the date when the property should be repaired, rebuilt or "
                    "replaced with reasonable speed. H.3 'Scheduled location' means a premises listed by address in the "
                    "Declarations or in a schedule attached to an endorsement."),
          ])


# --------------------------------------------------------------------------- 2
def endorsements():
    build("02_endorsements_MM-CP-E-series.pdf",
          "Commercial Property Endorsements Package",
          "Meridian Mutual Insurance Company (fictional). Endorsements modifying form MM-CP-0010 and MM-CP-1030.",
          [["Package", "MM-CP-E-SERIES"], ["Edition Dates", "E101 06/2025; E205 01/2025; E310 03/2025; E415 01/2025; FL-01 07/2025"],
           ["Modifies Forms", "MM-CP-0010 (Ed. 01/2025), MM-CP-1030 (Ed. 01/2025)"],
           ["State Availability", "See Section 6 and State Filings MM-FL-2025-0142, MM-TX-2025-0098, MM-NY-2025-0211"]],
          [
              ("h2", "1. MM-CP-E101 - FLOOD COVERAGE ENDORSEMENT - SCHEDULED LOCATIONS (Ed. 06/2025)"),
              ("p", "1.1 This endorsement modifies insurance provided under MM-CP-0010 and MM-CP-1030. It applies only to the "
                    "scheduled locations listed in the Schedule below and to Coverages COV-A (Building) and COV-B (Your Business "
                    "Personal Property)."),
              ("p", "1.2 Coverage Grant. Exclusion EXCL-FLD (Water) in Section B.1.g of MM-CP-1030 is deleted with respect to the "
                    "peril of Flood for the scheduled locations. We will pay for direct physical loss of or damage to Covered "
                    "Property at a scheduled location caused by Flood, subject to the Flood Sublimit and Flood Deductible shown "
                    "in the Schedule."),
              ("p", "1.3 Flood Deductible. A deductible of 5% of the Limit of Insurance for COV-A at the scheduled location "
                    "applies to each Flood occurrence, but not less than $25,000. This deductible replaces the deductible in "
                    "Section D of MM-CP-0010 for the peril of Flood only."),
              ("p", "1.4 Limitations. We will not pay under this endorsement for loss to property in the open, for loss at any "
                    "location that is not a scheduled location, or for loss caused by Flood that begins before the effective "
                    "date of this endorsement or within 72 hours after it. Coverage COV-D (Business Income) is not extended by "
                    "this endorsement unless the Schedule shows a COV-D Flood Sublimit."),
              ("table", [["Schedule Item", "Value"], ["Flood Sublimit (COV-A + COV-B, per location)", "$250,000"],
                         ["Flood Deductible", "5% of COV-A limit, minimum $25,000"], ["Annual Aggregate", "$500,000"],
                         ["Eligible Flood Zones", "AE, A, VE, X (shaded)"], ["Available States", "FL, TX"]],
               [3.2 * inch, 3.2 * inch]),
              ("h2", "2. MM-CP-E205 - EQUIPMENT BREAKDOWN ENDORSEMENT (Ed. 01/2025)"),
              ("p", "2.1 This endorsement modifies MM-CP-0010 Coverages COV-A and COV-B. We will pay for direct physical damage "
                    "to Covered Property caused by a Breakdown to Covered Equipment, including mechanical breakdown, electrical "
                    "arcing and steam boiler explosion. 2.2 The exclusion for mechanical breakdown in MM-CP-1030 Section B.2.d "
                    "does not apply to the extent coverage is provided by this endorsement. 2.3 The most we will pay for loss "
                    "under this endorsement is $100,000 per occurrence unless a higher limit is shown in the Declarations. "
                    "2.4 You must maintain all Covered Equipment in accordance with the manufacturer's recommendations."),
              ("h2", "3. MM-CP-E310 - WINDSTORM OR HAIL PERCENTAGE DEDUCTIBLE (Ed. 03/2025)"),
              ("p", "3.1 This endorsement modifies Section D - Deductible of MM-CP-0010 for Coverage COV-A and COV-B. 3.2 For "
                    "loss caused by Windstorm or Hail, the deductible is the percentage shown in the Declarations (2% or 5%) of "
                    "the Limit of Insurance for the damaged property, replacing the flat deductible. 3.3 In Florida the Windstorm "
                    "deductible applies as a Hurricane deductible on a calendar-year basis as required by Filing MM-FL-2025-0142. "
                    "3.4 This endorsement is mandatory for risks located in Florida Tier 1 coastal counties and in Texas "
                    "territory TX-T01 per Underwriting Guideline MM-UW-CP-2025 Section 4.3."),
              ("pb",),
              ("h2", "4. MM-CP-E415 - PROTECTIVE SAFEGUARDS ENDORSEMENT (Ed. 01/2025)"),
              ("p", "4.1 As a condition of this insurance, you are required to maintain the protective devices or services "
                    "listed in the Schedule (for example P-1 Automatic Sprinkler System, P-2 Automatic Fire Alarm, P-9 Central "
                    "Station Burglar Alarm). 4.2 You must notify us within 48 hours if any listed protective safeguard is "
                    "impaired or out of service, except when the impairment is due to ordinary maintenance that is completed "
                    "within 24 hours. 4.3 We will not pay for loss or damage caused by or resulting from fire if, prior to the "
                    "fire, you knew of any suspension or impairment in any protective safeguard listed in the Schedule and "
                    "failed to notify us of that fact. 4.4 This endorsement modifies Coverages COV-A, COV-B and COV-C."),
              ("h2", "5. MM-CP-FL-01 - FLORIDA AMENDATORY ENDORSEMENT (Ed. 07/2025)"),
              ("p", "5.1 This endorsement modifies MM-CP-0010 for policies issued in the State of Florida (FL) and supersedes any "
                    "conflicting provision in the base form. 5.2 Cancellation. We may cancel this policy only for the reasons "
                    "permitted by Florida law and we must mail written notice of cancellation at least 45 days before the "
                    "effective date of cancellation, except 10 days for nonpayment of premium. 5.3 Section E.3(b) of MM-CP-0010 "
                    "is amended to read: you must give us prompt notice of the loss or damage, and in no event later than 14 days "
                    "after you become aware of it. 5.4 Hurricane Deductible Disclosure. Where MM-CP-E310 is attached, the "
                    "Declarations must display the hurricane deductible in dollars and as a percentage. 5.5 Coverage COV-A is "
                    "amended to include the cost to comply with any ordinance or law up to $25,000 per occurrence."),
              ("h2", "6. ENDORSEMENT AVAILABILITY MATRIX"),
              ("table", [["Endorsement", "Edition", "Modifies Coverages", "Modifies Forms", "FL", "TX", "NY"],
                         ["MM-CP-E101", "06/2025", "COV-A, COV-B", "MM-CP-0010, MM-CP-1030", "Approved", "Approved", "Not filed"],
                         ["MM-CP-E205", "01/2025", "COV-A, COV-B", "MM-CP-0010, MM-CP-1030", "Approved", "Approved", "Pending"],
                         ["MM-CP-E310", "03/2025", "COV-A, COV-B", "MM-CP-0010", "Approved (mandatory Tier 1)", "Approved", "Not filed"],
                         ["MM-CP-E415", "01/2025", "COV-A, COV-B, COV-C", "MM-CP-0010", "Approved", "Approved", "Pending"],
                         ["MM-CP-FL-01", "07/2025", "COV-A", "MM-CP-0010", "Approved (mandatory)", "N/A", "N/A"]],
               [0.95 * inch, 0.6 * inch, 1.1 * inch, 1.4 * inch, 0.95 * inch, 0.7 * inch, 0.7 * inch]),
              ("p", "6.1 Precedence. Where an endorsement conflicts with the base form, the endorsement controls. Where a state "
                    "amendatory endorsement conflicts with any other endorsement, the state amendatory endorsement controls. "
                    "Where two editions of the same form are in force, the later edition controls."),
          ])


# --------------------------------------------------------------------------- 3
def uw_guidelines():
    build("03_underwriting_guidelines_MM-UW-CP-2025.pdf",
          "Commercial Property Underwriting Guidelines",
          "Meridian Mutual Insurance Company (fictional). Internal underwriting manual.",
          [["Document ID", "MM-UW-CP-2025"], ["Version", "3.2"], ["Effective Date", "07/01/2025"],
           ["Applies To Forms", "MM-CP-0010 (Ed. 01/2025), MM-CP-1030 (Ed. 01/2025) and E-series endorsements"],
           ["States In Scope", "FL, TX (NY pending Filing MM-NY-2025-0211)"]],
          [
              ("h2", "SECTION 1 - PURPOSE AND SCOPE"),
              ("p", "1.1 These guidelines govern the acceptance, pricing referral and binding of Commercial Property risks written "
                    "on form MM-CP-0010. 1.2 Underwriters must apply these guidelines together with Rate Manual MM-RM-CP-2025 and "
                    "the state filings listed above. 1.3 Any exception to these guidelines requires written approval from an "
                    "Underwriting Manager and must be documented in the underwriting file."),
              ("h2", "SECTION 2 - ELIGIBILITY"),
              ("p", "2.1 Eligible Risks. A risk is eligible if all of the following are true: (a) construction class is CC1 through "
                    "CC6; (b) Public Protection Class is PC1 through PC8; (c) the building is not vacant and has not been vacant "
                    "for more than 60 consecutive days in the prior 12 months; (d) Total Insured Value (TIV) does not exceed "
                    "$25,000,000 per location; (e) the class code is not listed as Prohibited in Section 2.3."),
              ("p", "2.2 Referral Risks. The following risks may be written only with Underwriting Manager approval: Protection "
                    "Class PC9 or PC10; buildings over 50 years old without updated electrical, plumbing, heating and roof within "
                    "the last 25 years; class code 0921 (Vacant Buildings); any location in FEMA flood zone A, AE, V or VE that "
                    "does not carry MM-CP-E101."),
              ("table", [["Class Code", "Description", "Status", "Reason"],
                         ["0511", "Fireworks or Explosives Manufacturing", "Prohibited", "Unacceptable fire and explosion hazard"],
                         ["0921", "Vacant Buildings", "Refer", "Vandalism and water damage frequency; see MM-CP-0010 E.5"],
                         ["0745", "Office Buildings - Mercantile Occupancy", "Eligible", "Preferred class"],
                         ["0802", "Warehouses - General Storage", "Eligible", "Verify protective safeguards MM-CP-E415"],
                         ["0634", "Restaurants with Cooking", "Refer", "Requires UL300 hood suppression (P-1 or P-5 safeguard)"]],
               [0.8 * inch, 2.4 * inch, 0.9 * inch, 2.4 * inch]),
              ("p", "2.3 Prohibited Risks. Underwriters must not quote or bind any risk with class code 0511, any risk with "
                    "unresolved open fire code violations, or any risk located in a state where form MM-CP-0010 is not approved "
                    "(currently NY, pending Filing MM-NY-2025-0211)."),
              ("h2", "SECTION 3 - AUTHORITY LIMITS"),
              ("table", [["Authority Level", "Maximum TIV Per Location", "Maximum Policy Premium", "Approval Required"],
                         ["UW Level 1 (Associate)", "$5,000,000", "$75,000", "None within limits"],
                         ["UW Level 2 (Senior)", "$15,000,000", "$250,000", "None within limits"],
                         ["UW Level 3 (Underwriting Manager)", "$25,000,000", "$600,000", "None within limits"],
                         ["Above Level 3", "Over $25,000,000", "Over $600,000", "Chief Underwriting Officer and facultative reinsurance"]],
               [1.9 * inch, 1.6 * inch, 1.5 * inch, 1.5 * inch]),
              ("p", "3.1 An underwriter must not bind a risk that exceeds his or her authority level. 3.2 Where a risk exceeds "
                    "the authority of the assigned underwriter, the file must be referred before a quote is released."),
              ("pb",),
              ("h2", "SECTION 4 - REQUIRED ENDORSEMENTS AND FORMS"),
              ("p", "4.1 Every policy must include the base coverage form MM-CP-0010 and the causes of loss form MM-CP-1030 in the "
                    "edition approved in the state of the risk. 4.2 Florida policies must include MM-CP-FL-01 Florida Amendatory "
                    "Endorsement. 4.3 MM-CP-E310 Windstorm or Hail Percentage Deductible is mandatory for all locations in Florida "
                    "Tier 1 coastal counties and in Texas rating territory TX-T01; a 5% deductible is required within one mile of "
                    "the coast and 2% elsewhere in those territories. 4.4 Any scheduled location in FEMA flood zone A, AE, V or VE "
                    "must carry MM-CP-E101 Flood Coverage Endorsement, or the insured must sign a Flood Exclusion Acknowledgment "
                    "form before binding. 4.5 MM-CP-E415 Protective Safeguards is required when the rate manual applies a sprinkler "
                    "credit (factor SPR-1) or a central station alarm credit (factor ALM-1). 4.6 Endorsements may be attached only in "
                    "states where the State Filing shows the status Approved."),
              ("h2", "SECTION 5 - QUOTING, BINDING AND DOCUMENTATION"),
              ("p", "5.1 Before releasing a quote the underwriter must verify: eligibility under Section 2; that the premium was "
                    "developed from Rate Manual MM-RM-CP-2025; and that all required endorsements under Section 4 are included. "
                    "5.2 Before binding, the underwriter must verify that every form edition on the policy matches the edition "
                    "approved in the applicable State Filing. 5.3 The underwriting file must document the flood zone determination "
                    "for every scheduled location. 5.4 Inspections are required within 60 days of binding for any location with TIV "
                    "above $2,000,000 or Protection Class PC7 or higher."),
              ("h2", "SECTION 6 - RENEWAL REVIEW"),
              ("p", "6.1 At renewal the underwriter must confirm that form editions remain current and that no State Filing has "
                    "withdrawn a form in use. 6.2 Loss ratio above 65% over the prior three years requires Underwriting Manager "
                    "review. 6.3 Where a newer edition of a form has been approved, the newer edition must be attached at renewal."),
          ])


# --------------------------------------------------------------------------- 4
def rate_manual():
    build("04_rate_manual_MM-RM-CP-2025.pdf",
          "Commercial Property Rate Manual",
          "Meridian Mutual Insurance Company (fictional). Rates and rating factors for form MM-CP-0010.",
          [["Document ID", "MM-RM-CP-2025"], ["Edition", "07/2025"], ["Effective Date", "07/01/2025 (new and renewal)"],
           ["Rate Filings", "FL: MM-FL-2025-0142 (approved); TX: MM-TX-2025-0098 (approved, +4.8% overall); NY: MM-NY-2025-0211 (pending)"],
           ["Companion Documents", "MM-UW-CP-2025 Underwriting Guidelines; MM-CP-0010 Coverage Form"]],
          [
              ("h2", "RULE 1 - RATING PROCEDURE"),
              ("p", "1.1 Premium for Coverage COV-A and COV-B is computed as: Limit of Insurance / 100 x Base Rate x Territory "
                    "Factor x Protection Class Factor x Deductible Factor x Safeguard Factors, plus endorsement premiums. "
                    "1.2 COV-D (Business Income) is rated at 80% of the COV-A rate applied to the COV-D limit. 1.3 The minimum "
                    "premium per policy is $1,000. 1.4 Rates in this manual apply only to forms in the editions listed in the "
                    "applicable State Filing."),
              ("h2", "RULE 2 - BASE RATES PER $100 OF INSURANCE (COV-A BUILDING)"),
              ("table", [["Construction Class", "Description", "Base Rate COV-A", "Base Rate COV-B"],
                         ["CC1", "Frame", "0.420", "0.510"], ["CC2", "Joisted Masonry", "0.350", "0.430"],
                         ["CC3", "Non-Combustible", "0.290", "0.360"], ["CC4", "Masonry Non-Combustible", "0.240", "0.300"],
                         ["CC5", "Modified Fire Resistive", "0.190", "0.240"], ["CC6", "Fire Resistive", "0.150", "0.200"]],
               [1.3 * inch, 2.3 * inch, 1.4 * inch, 1.4 * inch]),
              ("h2", "RULE 3 - TERRITORY FACTORS"),
              ("table", [["Territory Code", "State", "Description", "Factor", "Notes"],
                         ["FL-T01", "FL", "Inland counties", "1.10", ""],
                         ["FL-T03", "FL", "Tier 1 coastal counties", "1.45", "MM-CP-E310 mandatory (MM-UW-CP-2025 4.3)"],
                         ["TX-T01", "TX", "Gulf coast counties", "1.35", "MM-CP-E310 mandatory"],
                         ["TX-T04", "TX", "North and central", "0.95", ""],
                         ["NY-T07", "NY", "Metro", "1.20", "Not in effect until Filing MM-NY-2025-0211 is approved"]],
               [1.0 * inch, 0.5 * inch, 1.9 * inch, 0.7 * inch, 2.3 * inch]),
              ("h2", "RULE 4 - PROTECTION CLASS FACTORS"),
              ("table", [["Protection Class", "PC1-PC3", "PC4-PC6", "PC7-PC8", "PC9", "PC10"],
                         ["Factor", "0.85", "1.00", "1.20", "1.60 (refer)", "2.00 (refer)"]]),
              ("pb",),
              ("h2", "RULE 5 - DEDUCTIBLE FACTORS"),
              ("table", [["Deductible", "$1,000", "$2,500 (base)", "$5,000", "$10,000", "$25,000"],
                         ["Factor", "1.05", "1.00", "0.95", "0.90", "0.82"]]),
              ("p", "5.1 Where MM-CP-E310 Windstorm or Hail Percentage Deductible is attached, apply factor WH-2 (0.92) for a 2% "
                    "deductible or WH-5 (0.85) for a 5% deductible to the COV-A and COV-B premium in territories FL-T03 and TX-T01."),
              ("h2", "RULE 6 - PROTECTIVE SAFEGUARD FACTORS"),
              ("table", [["Factor Code", "Safeguard", "Factor", "Required Endorsement"],
                         ["SPR-1", "P-1 Automatic Sprinkler System (full)", "0.80", "MM-CP-E415"],
                         ["ALM-1", "P-9 Central Station Burglar Alarm", "0.95", "MM-CP-E415"],
                         ["ALM-2", "P-2 Automatic Fire Alarm", "0.97", "MM-CP-E415"]],
               [1.0 * inch, 2.6 * inch, 0.8 * inch, 2.0 * inch]),
              ("h2", "RULE 7 - ENDORSEMENT PREMIUMS"),
              ("table", [["Endorsement", "Rating Basis", "Rate or Factor", "States"],
                         ["MM-CP-E101 Flood - Scheduled Locations", "Per $100 of Flood Sublimit", "0.350 in zone X; 0.900 in zones A/AE; 1.400 in zones V/VE", "FL, TX"],
                         ["MM-CP-E205 Equipment Breakdown", "Per $100 of COV-A + COV-B limit", "0.025", "FL, TX"],
                         ["MM-CP-E310 Windstorm/Hail % Deductible", "Factor on COV-A + COV-B premium", "WH-2 0.92 / WH-5 0.85", "FL, TX"],
                         ["MM-CP-E415 Protective Safeguards", "No charge (enables SPR/ALM factors)", "1.00", "FL, TX"],
                         ["MM-CP-FL-01 Florida Amendatory", "No charge (mandatory)", "1.00", "FL"]],
               [2.0 * inch, 1.7 * inch, 1.9 * inch, 0.8 * inch]),
              ("h2", "RULE 8 - WORKED EXAMPLE"),
              ("p", "8.1 A CC4 office building (class code 0745) in territory FL-T03 with COV-A limit $4,000,000, PC4, $5,000 "
                    "deductible, 5% windstorm deductible (MM-CP-E310) and full sprinklers (SPR-1 with MM-CP-E415): "
                    "4,000,000 / 100 x 0.240 x 1.45 x 1.00 x 0.95 x 0.80 x 0.85 = $8,992 COV-A premium before fees. 8.2 Adding "
                    "MM-CP-E101 with a $250,000 flood sublimit in zone AE adds 250,000 / 100 x 0.900 = $2,250."),
          ])


# --------------------------------------------------------------------------- 5
def claims_manual():
    build("05_claims_manual_MM-CM-CP-2025.pdf",
          "Commercial Property Claims Handling Manual",
          "Meridian Mutual Insurance Company (fictional). Internal claims procedures.",
          [["Document ID", "MM-CM-CP-2025"], ["Version", "2.0"], ["Effective Date", "05/01/2025"],
           ["Applies To Forms", "MM-CP-0010, MM-CP-1030, MM-CP-E101, MM-CP-E205, MM-CP-E310, MM-CP-E415, MM-CP-FL-01"],
           ["States In Scope", "FL, TX"]],
          [
              ("h2", "SECTION 1 - FIRST NOTICE OF LOSS (FNOL)"),
              ("p", "1.1 The insured is required by MM-CP-0010 Section E.3(b) to report loss within 72 hours of becoming aware of it; "
                    "in Florida, MM-CP-FL-01 Section 5.3 extends this period to 14 days. Late notice must not be used to deny a claim "
                    "unless the delay prejudiced our investigation. 1.2 The adjuster must acknowledge receipt of every claim in "
                    "writing within 14 calendar days in Florida and within 15 business days in Texas, per the applicable state "
                    "claims-handling requirements referenced in Filings MM-FL-2025-0142 and MM-TX-2025-0098. 1.3 At FNOL the "
                    "adjuster must record: policy number, form edition of MM-CP-0010 in force, all attached endorsements, date of "
                    "loss, cause of loss, and the scheduled location involved."),
              ("h2", "SECTION 2 - COVERAGE VERIFICATION"),
              ("p", "2.1 The adjuster must verify that the form edition and endorsements on the policy match the editions approved "
                    "in the applicable State Filing before issuing any coverage position. 2.2 For any loss involving water, the "
                    "adjuster must determine whether the cause of loss is Flood as excluded by EXCL-FLD in MM-CP-1030 Section "
                    "B.1.g, and then check whether MM-CP-E101 is attached and whether the damaged premises is a scheduled location "
                    "under that endorsement. 2.3 If MM-CP-E101 is attached and the premises is a scheduled location, Flood damage to "
                    "COV-A and COV-B is covered up to the Flood Sublimit of $250,000 subject to the 5% Flood Deductible; COV-D is not "
                    "covered unless the Schedule shows a COV-D Flood Sublimit. 2.4 If MM-CP-E101 is not attached, or the premises is "
                    "not a scheduled location, Flood damage is not covered and a reservation of rights letter must be issued within "
                    "10 business days."),
              ("table", [["Cause of Loss", "Exclusion Code", "Restoring Endorsement", "Coverage Position"],
                         ["Flood / surface water", "EXCL-FLD", "MM-CP-E101 (scheduled locations only)", "Covered only if E101 attached and location scheduled"],
                         ["Earth movement", "EXCL-EQ", "None available", "Not covered"],
                         ["Mechanical breakdown", "B.2.d", "MM-CP-E205", "Covered up to $100,000 if E205 attached"],
                         ["Windstorm / hail", "None (covered peril)", "MM-CP-E310 changes deductible", "Covered, apply 2% or 5% deductible"],
                         ["Fire with impaired sprinkler", "MM-CP-E415 4.3", "None", "Not covered if insured knew of impairment and did not notify"],
                         ["Fungus / mold", "EXCL-MOLD", "None available", "Not covered except limited $15,000 clean-up"]],
               [1.4 * inch, 0.9 * inch, 1.9 * inch, 2.3 * inch]),
              ("pb",),
              ("h2", "SECTION 3 - RESERVES AND AUTHORITY"),
              ("table", [["Adjuster Level", "Reserve Authority", "Payment Authority", "Escalation"],
                         ["Adjuster I", "$25,000", "$15,000", "Adjuster II"], ["Adjuster II", "$100,000", "$75,000", "Claims Supervisor"],
                         ["Claims Supervisor", "$500,000", "$350,000", "Claims Manager"], ["Claims Manager", "$2,000,000", "$1,500,000", "VP Claims; notify reinsurance above $1,000,000"]],
               [1.4 * inch, 1.4 * inch, 1.4 * inch, 2.3 * inch]),
              ("p", "3.1 An adjuster must not set a reserve or issue a payment above his or her authority. 3.2 Initial reserves must "
                    "be set within 5 business days of FNOL and reviewed every 30 days."),
              ("h2", "SECTION 4 - PROOF OF LOSS AND PAYMENT"),
              ("p", "4.1 Under MM-CP-0010 Section E.3(d) the insured must submit a signed, sworn proof of loss within 60 days of our "
                    "request. The adjuster may extend this period in writing. 4.2 Under Section E.4 we must state our coverage "
                    "position within 30 days of receiving the proof of loss and pay undisputed amounts within 30 days. 4.3 When a "
                    "percentage deductible applies under MM-CP-E310 or MM-CP-E101, the adjuster must document the Limit of Insurance "
                    "used to calculate the deductible and the resulting dollar amount."),
              ("h2", "SECTION 5 - VACANCY AND PROTECTIVE SAFEGUARDS"),
              ("p", "5.1 For any theft, vandalism, sprinkler leakage or water damage claim the adjuster must determine whether the "
                    "building was vacant for more than 60 consecutive days before the loss (MM-CP-0010 Section E.5). If so, the loss "
                    "is not covered. 5.2 For fire losses at premises with MM-CP-E415, the adjuster must obtain evidence that the "
                    "scheduled protective safeguards were operational, or that any impairment was reported to us within 48 hours."),
              ("h2", "SECTION 6 - SUBROGATION AND SALVAGE"),
              ("p", "6.1 The adjuster must evaluate subrogation potential on every claim above $10,000 and must preserve evidence. "
                    "6.2 Salvage must be offered for sale within 30 days of payment where the recovery is expected to exceed $2,500."),
          ])


# --------------------------------------------------------------------------- 6
def state_filings():
    build("06_state_filings_MM-2025.pdf",
          "State Form and Rate Filing Register - Commercial Property",
          "Meridian Mutual Insurance Company (fictional). Summary of filings submitted to state insurance regulators.",
          [["Register ID", "MM-FILINGS-CP-2025"], ["Prepared", "08/15/2025"],
           ["Filings Covered", "MM-FL-2025-0142, MM-TX-2025-0098, MM-NY-2025-0211"],
           ["Forms Covered", "MM-CP-0010, MM-CP-1030, MM-CP-E101, MM-CP-E205, MM-CP-E310, MM-CP-E415, MM-CP-FL-01"]],
          [
              ("h2", "FILING 1 - FLORIDA (FL) - MM-FL-2025-0142"),
              ("p", "1.1 Filing Type: Form and Rate. Submitted 03/10/2025. Approved 06/15/2025. Effective 07/01/2025 for new and "
                    "renewal business. Tracking number MMIC-134000142. 1.2 Overall rate change +6.2%. Territory FL-T03 factor "
                    "revised from 1.30 to 1.45. 1.3 Conditions of approval: MM-CP-FL-01 Florida Amendatory Endorsement must be "
                    "attached to every Florida policy; MM-CP-E310 must display the hurricane deductible in dollars and percent; "
                    "the insurer must acknowledge claims within 14 calendar days."),
              ("table", [["Form", "Edition", "Status", "Action"],
                         ["MM-CP-0010", "01/2025", "Approved", "Replaces Ed. 07/2022"],
                         ["MM-CP-1030", "01/2025", "Approved", "Replaces Ed. 07/2022"],
                         ["MM-CP-E101", "06/2025", "Approved", "New form"],
                         ["MM-CP-E205", "01/2025", "Approved", "No change"],
                         ["MM-CP-E310", "03/2025", "Approved", "Mandatory in Tier 1 coastal counties"],
                         ["MM-CP-E415", "01/2025", "Approved", "No change"],
                         ["MM-CP-FL-01", "07/2025", "Approved", "Mandatory on all FL policies; replaces Ed. 01/2023"]],
               [1.3 * inch, 1.0 * inch, 1.0 * inch, 3.1 * inch]),
              ("h2", "FILING 2 - TEXAS (TX) - MM-TX-2025-0098"),
              ("p", "2.1 Filing Type: Form and Rate. Submitted 02/20/2025. Approved 05/30/2025. Effective 07/01/2025. Tracking number "
                    "MMIC-134000098. 2.2 Overall rate change +4.8%. Territory TX-T01 factor 1.35 unchanged. 2.3 Conditions of "
                    "approval: claims must be acknowledged within 15 business days; MM-CP-E310 mandatory in territory TX-T01."),
              ("table", [["Form", "Edition", "Status", "Action"],
                         ["MM-CP-0010", "01/2025", "Approved", "Replaces Ed. 07/2022"],
                         ["MM-CP-1030", "01/2025", "Approved", "Replaces Ed. 07/2022"],
                         ["MM-CP-E101", "06/2025", "Approved", "New form"],
                         ["MM-CP-E205", "01/2025", "Approved", "No change"],
                         ["MM-CP-E310", "03/2025", "Approved", "Mandatory in TX-T01"],
                         ["MM-CP-E415", "01/2025", "Approved", "No change"]],
               [1.3 * inch, 1.0 * inch, 1.0 * inch, 3.1 * inch]),
              ("pb",),
              ("h2", "FILING 3 - NEW YORK (NY) - MM-NY-2025-0211"),
              ("p", "3.1 Filing Type: Form and Rate. Submitted 06/05/2025. Status: Pending regulator review. Requested effective date "
                    "01/01/2026. Tracking number MMIC-134000211. 3.2 Forms MM-CP-E101 and MM-CP-E310 were not included in this filing "
                    "and must not be used in New York. 3.3 Until approval, no Commercial Property policy may be issued on form "
                    "MM-CP-0010 in New York (see MM-UW-CP-2025 Section 2.3)."),
              ("table", [["Form", "Edition", "Status", "Action"],
                         ["MM-CP-0010", "01/2025", "Pending", "New form for NY"],
                         ["MM-CP-1030", "01/2025", "Pending", "New form for NY"],
                         ["MM-CP-E205", "01/2025", "Pending", "New form for NY"],
                         ["MM-CP-E415", "01/2025", "Pending", "New form for NY"],
                         ["MM-CP-E101", "06/2025", "Not filed", "Not available in NY"],
                         ["MM-CP-E310", "03/2025", "Not filed", "Not available in NY"]],
               [1.3 * inch, 1.0 * inch, 1.0 * inch, 3.1 * inch]),
              ("h2", "SECTION 4 - FILING COMPLIANCE RULES"),
              ("p", "4.1 A form may be attached to a policy only in a state where this register shows the status Approved for that "
                    "form and edition on or before the policy effective date. 4.2 When a form edition is replaced, the superseded "
                    "edition must not be used on new business after the effective date of the replacing filing and must be replaced "
                    "at the first renewal. 4.3 Compliance must review this register at every renewal cycle and notify Underwriting of "
                    "any withdrawn or disapproved form within 5 business days. 4.4 Rate changes approved in a filing apply to policies "
                    "effective on or after the filing effective date and must be implemented in Rate Manual MM-RM-CP-2025."),
              ("h2", "SECTION 5 - FORM TO STATE CROSS-REFERENCE"),
              ("table", [["Form", "FL", "TX", "NY"],
                         ["MM-CP-0010 Ed. 01/2025", "Approved", "Approved", "Pending"],
                         ["MM-CP-1030 Ed. 01/2025", "Approved", "Approved", "Pending"],
                         ["MM-CP-E101 Ed. 06/2025", "Approved", "Approved", "Not filed"],
                         ["MM-CP-E205 Ed. 01/2025", "Approved", "Approved", "Pending"],
                         ["MM-CP-E310 Ed. 03/2025", "Approved", "Approved", "Not filed"],
                         ["MM-CP-E415 Ed. 01/2025", "Approved", "Approved", "Pending"],
                         ["MM-CP-FL-01 Ed. 07/2025", "Approved", "N/A", "N/A"]],
               [2.4 * inch, 1.3 * inch, 1.3 * inch, 1.3 * inch]),
          ])


if __name__ == "__main__":
    policy_form(); endorsements(); uw_guidelines(); rate_manual(); claims_manual(); state_filings()
