# KBA Matching Audit 2026-06

This report audits KBA FZ10 records parsed from `data/raw/kba/fz10_2026_06.xlsx` against the current `config/vehicles.yaml` master data. It is an audit artifact only; it does not modify master data and must not be treated as an automatic import mapping.

## Summary

- Source file: `data/raw/kba/fz10_2026_06.xlsx`
- Data period: 2026-06
- Parsed RegistrationRecord total: 60
- Record-level exact matches: 2
- Brand missing from master data: 50
- Brand matched but model missing: 7
- Ambiguous records: 1

## Status Definitions

- `exact_match`: KBA source value exactly equals configured canonical value.
- `alias_match`: KBA source value maps through a configured alias.
- `normalization_match`: KBA source value matches after case, spacing, punctuation, or accent normalization.
- `missing_master_data`: no safe corresponding master-data entry exists.
- `ambiguous`: a candidate exists but should not be selected without human review.

## Successful Exact Matches

| KBA brand | KBA model | Canonical brand | Canonical model | Brand status | Vehicle status | Candidate | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NIO | EL6 | NIO | EL6 | exact_match | exact_match | NIO EL6 | KBA model exactly equals a configured canonical_model for the matched brand. |
| XPENG | G6 | XPENG | G6 | exact_match | exact_match | XPENG G6 | KBA model exactly equals a configured canonical_model for the matched brand. |

## Unmatched Brands

| KBA brand | KBA model | Canonical brand | Canonical model | Brand status | Vehicle status | Candidate | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ALFA ROMEO | GIULIA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| ALPINE | A110 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| ASTON MARTIN | SONSTIGE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| BENTLEY | BENTAYGA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| CADILLAC | ESCALADE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| CITROEN | BERLINGO |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| DACIA | BIGSTER |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| DEEPAL | S05 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| DONGFENG | BOX |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| FERRARI | 12CILINDRI |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| FIAT | 500 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| FORD | CAPRI |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| GEELY | E5 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| HONDA | CIVIC |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| HYUNDAI | BAYON |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| INEOS | GRENADIER |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| IVECO | DAILY |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| JAC | SONSTIGE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| JAECOO | 5 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| JEEP | AVENGER |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| KGM | ACTYON |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| KIA | CEED |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LAMBORGHINI | URUS |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LAND ROVER | DEFENDER |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LEXUS | ES |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LOTUS | ELETRE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LUCID | AIR |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LYNK & CO | 01 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MAN | TGE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MAZDA | 2 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MINI | MINI |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MITSUBISHI | ASX |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MORGAN | SONSTIGE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| NISSAN | ARIYA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| OMODA | 5 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| OPEL | ASTRA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| PEUGEOT | 2008 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| POLESTAR | 2 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| PORSCHE | 911 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| RENAULT | ARKANA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| ROLLS ROYCE | CULLINAN |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| SEAT | ARONA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| SMART | 1 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| SUBARU | CROSSTREK |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| SUZUKI | ACROSS |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| TOGG | T10F |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| TOYOTA | AYGO |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| VINFAST | VF 6 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| VOLVO | 60 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| ZEEKR | 001 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |

## Brand Matched But Vehicle Missing

| KBA brand | KBA model | Canonical brand | Canonical model | Brand status | Vehicle status | Candidate | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUDI | A1 | Audi |  | normalization_match | missing_master_data | Q4 e-tron | Matched brand exists, but model is not in current master data. Configured models for brand: Q4 e-tron. |
| BMW | 1ER | BMW |  | exact_match | missing_master_data | iX1 | Matched brand exists, but model is not in current master data. Configured models for brand: iX1. Current target is iX1; do not map BMW 1ER to iX1. |
| BYD | ATTO 2 | BYD |  | exact_match | missing_master_data | Atto 3, Seal U | Matched brand exists, but model is not in current master data. Configured models for brand: Atto 3, Seal U. Current targets are Atto 3 and Seal U; do not map Atto 2 to Atto 3. |
| LEAPMOTOR | B05 | Leapmotor |  | normalization_match | missing_master_data | C10 | Matched brand exists, but model is not in current master data. Configured models for brand: C10. |
| MERCEDES | A-KLASSE | Mercedes-Benz |  | alias_match | missing_master_data | EQA | Matched brand exists, but model is not in current master data. Configured models for brand: EQA. |
| SKODA | ELROQ | Škoda |  | normalization_match | missing_master_data | Enyaq | Matched brand exists, but model is not in current master data. Configured models for brand: Enyaq. |
| TESLA | MODEL 3 | Tesla |  | normalization_match | missing_master_data | Model Y | Matched brand exists, but model is not in current master data. Configured models for brand: Model Y. Current target is Model Y; do not map Model 3 to Model Y. |

## All Record-Level Audit Results

| KBA brand | KBA model | Canonical brand | Canonical model | Brand status | Vehicle status | Candidate | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ALFA ROMEO | GIULIA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| ALPINE | A110 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| ASTON MARTIN | SONSTIGE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| AUDI | A1 | Audi |  | normalization_match | missing_master_data | Q4 e-tron | Matched brand exists, but model is not in current master data. Configured models for brand: Q4 e-tron. |
| BENTLEY | BENTAYGA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| BMW | 1ER | BMW |  | exact_match | missing_master_data | iX1 | Matched brand exists, but model is not in current master data. Configured models for brand: iX1. Current target is iX1; do not map BMW 1ER to iX1. |
| BYD | ATTO 2 | BYD |  | exact_match | missing_master_data | Atto 3, Seal U | Matched brand exists, but model is not in current master data. Configured models for brand: Atto 3, Seal U. Current targets are Atto 3 and Seal U; do not map Atto 2 to Atto 3. |
| CADILLAC | ESCALADE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| CITROEN | BERLINGO |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| DACIA | BIGSTER |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| DEEPAL | S05 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| DONGFENG | BOX |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| FERRARI | 12CILINDRI |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| FIAT | 500 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| FORD | CAPRI |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| GEELY | E5 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| HONDA | CIVIC |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| HYUNDAI | BAYON |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| INEOS | GRENADIER |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| IVECO | DAILY |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| JAC | SONSTIGE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| JAECOO | 5 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| JEEP | AVENGER |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| KGM | ACTYON |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| KIA | CEED |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LAMBORGHINI | URUS |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LAND ROVER | DEFENDER |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LEAPMOTOR | B05 | Leapmotor |  | normalization_match | missing_master_data | C10 | Matched brand exists, but model is not in current master data. Configured models for brand: C10. |
| LEXUS | ES |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LOTUS | ELETRE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LUCID | AIR |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| LYNK & CO | 01 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MAN | TGE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MAZDA | 2 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MERCEDES | A-KLASSE | Mercedes-Benz |  | alias_match | missing_master_data | EQA | Matched brand exists, but model is not in current master data. Configured models for brand: EQA. |
| MG ROEWE | 3 |  |  | ambiguous | ambiguous |  | Brand candidate is ambiguous, so vehicle mapping is not evaluated automatically. |
| MINI | MINI |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MITSUBISHI | ASX |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| MORGAN | SONSTIGE |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| NIO | EL6 | NIO | EL6 | exact_match | exact_match | NIO EL6 | KBA model exactly equals a configured canonical_model for the matched brand. |
| NISSAN | ARIYA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| OMODA | 5 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| OPEL | ASTRA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| PEUGEOT | 2008 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| POLESTAR | 2 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| PORSCHE | 911 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| RENAULT | ARKANA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| ROLLS ROYCE | CULLINAN |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| SEAT | ARONA |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| SKODA | ELROQ | Škoda |  | normalization_match | missing_master_data | Enyaq | Matched brand exists, but model is not in current master data. Configured models for brand: Enyaq. |
| SMART | 1 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| SUBARU | CROSSTREK |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| SUZUKI | ACROSS |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| TESLA | MODEL 3 | Tesla |  | normalization_match | missing_master_data | Model Y | Matched brand exists, but model is not in current master data. Configured models for brand: Model Y. Current target is Model Y; do not map Model 3 to Model Y. |
| TOGG | T10F |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| TOYOTA | AYGO |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| VINFAST | VF 6 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| VOLVO | 60 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |
| XPENG | G6 | XPENG | G6 | exact_match | exact_match | XPENG G6 | KBA model exactly equals a configured canonical_model for the matched brand. |
| ZEEKR | 001 |  |  | missing_master_data | missing_master_data |  | Brand is not in current master data; vehicle cannot be safely matched. |

## Guardrails

- No fuzzy result in this report should be written to the database automatically.
- `registration_scope` remains geography only; it is not used for fuel type or model matching.
- The proposed YAML file is a review artifact only and is not loaded by runtime code.
