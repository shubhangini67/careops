# Synthetic FHIR Fixtures (CareOps AI)

This directory contains **de-identified, synthetic** FHIR R4-style resources for local development and demos.

## Contents

| File | Resource types | Purpose |
|------|----------------|---------|
| `patients.json` | Patient | Anonymous patient demographics (no real PHI) |
| `encounters.json` | Encounter | OPD/admission visits linked to departments |
| `observations.json` | Observation | Capacity and workload signals (not clinical diagnoses) |
| `appointments.json` | Appointment | Scheduled visits driving bed/OPD demand |

## Privacy

- All identifiers are synthetic (`SYN-PAT-001`, etc.).
- Dashboards and API responses **never surface patient names or MRNs** — only department-level aggregates.
- Do not import real patient data into this repository.

## Importing Synthea Data Later

[Synthea](https://github.com/synthetichealth/synthea) generates realistic synthetic populations. To import later:

1. Run Synthea with `--exporter.fhir.export=true` for your target region.
2. Filter exported bundles to **Encounter**, **Appointment**, and **Observation** (capacity-relevant only).
3. Strip direct identifiers (name, address, telecom) — retain only internal surrogate IDs.
4. Map department codes to CareOps `departments` table slugs.
5. Place normalized JSON in this directory or load via `scripts/import_synthea_fhir.py` (future).

```bash
# Example Synthea run (not required for local demo)
java -jar synthea-with-dependencies.jar -p 100 Massachusetts
```

CareOps reads fixtures through `app.infrastructure.healthcare.fhir_store.FHIRStore`.
