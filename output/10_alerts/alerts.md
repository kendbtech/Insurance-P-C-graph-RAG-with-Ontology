# Layer 6 enforcement log

## Bind POL-FL-0100 -> rejected (3 alerts)
Coastal FL bind with no FL-01, no E310, flood zone AE not scheduled -> expect 3 underwriter alerts

- to **Underwriter** | rule R07 | record `policy/POL-FL-0100` | Florida policies must include MM-CP-FL-01 Florida Amendatory Endorsement (MM-UW-CP-2025 4.2).
- to **Underwriter** | rule R08 | record `policy/POL-FL-0100` | MM-CP-E310 is mandatory for locations in FL Tier 1 coastal counties (FL-T03) and TX-T01 (MM-UW-CP-2025 4.3).
- to **Underwriter** | rule R09 | record `location/LOC-0100` | A location in flood zone A/AE/V/VE must be scheduled under MM-CP-E101 unless a Flood Exclusion Acknowledgment is signed (MM-UW-CP-2025 4.4).
## FNOL CLM-0200 -> rejected (2 alerts)
Flood claim at an UNscheduled location on the valid FL policy -> expect adjuster alert (R01 exclusion stands)

- to **Adjuster** | rule R01 | record `claim/CLM-0200` | Flood is excluded (EXCL-FLD, MM-CP-1030 B.1.g via MM-CP-0010 Section B.1). Check for a restoring endorsement.
- to **Adjuster** | rule R02 | record `claim/CLM-0200` | MM-CP-E101 restores Flood only for scheduled locations and only for COV-A / COV-B (sublimit $250,000, 5% deductible).
## Bind POL-TX-0300 -> accepted (0 alerts)
Clean TX bind -> expect accepted, 0 alerts
