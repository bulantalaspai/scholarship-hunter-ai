# Scholarship source quality report

**Audit date — 2026-11-25.** This is an offline audit of the tracked catalogue
and evidence manifest, plus a live local Qwen extraction run on archived
excerpts. The source verification dates are 2026-11-11 for the original two
records and 2026-11-12 for the other 20. This audit did not refresh those dates.

## Catalogue audit

| Check | Finding |
| --- | --- |
| Identity and provenance | 22 unique programme/provider/cycle identities. All 22 have a primary official URL and matching recorded provenance. The manifest contains 69 distinct primary and supporting URLs. |
| Institution, destination and degree | Provider and destination are recorded for all 22. All are master's routes. Four lack a structured study-field list. Multi-country destinations can reflect different mobility paths. |
| Funding and amount | 16 fully funded and 6 partially funded award descriptions. All 22 record tuition terms. One lacks a living-stipend description. Published amounts can apply only to a specific intake. |
| Deadlines and intake | 12 future deadlines, 2 past and 8 unknown. Two records lack a recorded cycle. A future deadline alone cannot establish that applications are open. |
| Nationality | Eight lack a structured nationality list. Documented restrictions, routes, quotas and prior-award exclusions require individual review. |
| Language | Twelve lack a scalar IELTS threshold. Other tests, equivalent evidence, component scores and exemptions can change the applicable result. |
| GPA and prior degree | All 22 lack a scalar GPA/scale pair. Conditional or inverse-grade criteria remain in the evidence. Additional conditions are recorded for all 22, including prior-degree information where documented. Zero have complete current structured eligibility rules. |
| Collection permission | 22 primary URLs across 21 official hosts are registered for manual use. Terms and robots evidence for automated access is pending for every entry. |

The past deadlines belong to the documented MEXT Kazakhstan and Stipendium
Hungaricum Kazakhstan calls. The CYBERSURE 2026 award amount does not establish
the 2027 rate. EMIMEP retains an intake ambiguity, AMASE has route-specific
deadlines, and CyberMACS lacks a verified next intake. These gaps stay visible in
the programme notes and the per-record evidence manifest.
[Per-record evidence and gaps](../backend/data/catalogue_evidence.json)

Run the same offline audit from the repository root.

```powershell
\.venv\Scripts\python.exe -m backend.app.catalogue_quality --as-of 2026-11-25 --evidence backend/data/catalogue_evidence.json
```

## Six-programme pilot

The inputs were six manually archived official funding excerpts accessed on
2026-11-12, identified by their unchanged manifest IDs. They cover programmes
already in the catalogue and exercise duplicate detection without introducing
new active records. Provider pages attempted and successfully fetched during the
pilot were both **0** because collection permission was unreviewed. Excerpts read
from the archive were **6 of 6**. [Frozen source manifest](../evaluation/data/source_annotations.json)

The initial live local Qwen run rejected all six outputs. Five had invalid
schema fields and one repeated a JSON key. After adding a schema constraint to
the collector's Ollama request, a second run with the same model and excerpts
staged six drafts. The table counts populated fields with exact source spans,
before human assessment of whether the span supports the field.

| Fixture | Programme | Populated / 13 | Missing | Catalogue overlaps | Comparable discrepancies | Wording checks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| S01 | SMACCs | 1 | 12 | 1 | 0 | 0 |
| S02 | EDISS | 2 | 11 | 1 | 0 | 2 |
| S03 | DEAI | 2 | 11 | 1 | 0 | 2 |
| S05 | CyberMACS | 1 | 12 | 1 | 0 | 1 |
| S06 | IMLEX | 1 | 12 | 1 | 0 | 0 |
| S07 | DENSYS 2.0 | 1 | 12 | 1 | 0 | 1 |
| **Total** | | **8 / 78** | **70** | **6** | **0** | **6** |

All six drafts were `pending_review` with **0 approved and 0 published**.
Each matched an existing primary URL. No draft contained a deadline. Every
draft lacked destination, degree level, subject, funding classification, intake,
nationality, GPA, language and prior-degree fields. Four drafts lacked a funding
amount. Six wording differences need interpretation. For example, the model
assigned “EDISS” to the provider field and a generic scholarship label to the
programme-name field. An exact span alone cannot verify either mapping.

The excerpts focus on funding and omit much of the application evidence. Zero
comparable discrepancies means no directly comparable funding classification or
deadline was flagged. It does not establish agreement across all facts. The
pilot measures observed extraction and staging behavior and supplies no academic
accuracy estimate. Human reviewers still need current official pages and must
verify award type, scope, intake and field mappings before approving anything.

The run used local Ollama `qwen3:4b-instruct`; backend tests use scripted
model and provider transport responses. Reproduce the pilot using the
[collection instructions](SCHOLARSHIP_COLLECTION.md). Its raw summary and draft
audit stayed in the ignored `.local-run/collection/` directory.

## Verification

- **749 backend tests** passed with warnings treated as errors. Tests use
  temporary databases, mocked provider transport and scripted model replies.
- **207 Vitest tests** and **22 Chromium tests** passed. Chromium exercised
  the real local FastAPI application against a temporary catalogue, with mocked
  AI responses for controlled scenarios.
- Ruff lint and format, ESLint, TypeScript, Vite build, installed dependency
  checks and the Git whitespace check passed. The npm advisory registry
  reported zero vulnerabilities for the frontend dependency tree.
