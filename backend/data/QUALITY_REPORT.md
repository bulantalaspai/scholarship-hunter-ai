# Catalogue data quality report

**Snapshot: 2026-11-12.** This report covers 22 source-backed scholarship records: 20 additions and the two unchanged original records. Verification describes the cited catalogue facts, not an open call, complete eligibility review, or award guarantee.

| Measure | Count |
| --- | ---: |
| Total / unique scholarship records | 22 |
| Records with official source metadata and documented review | 22 |
| New records reviewed 2026-11-12 | 20 |
| Original records retained at 2026-11-11 | 2 |
| Fully funded award schemes | 16 |
| Partially funded award schemes | 6 |
| Unknown funding classification | 0 |
| Complete current structured eligibility policies | 0 |
| Records requiring further eligibility verification | 22 |
| Duplicate identity keys | 0 |
| Same programme/provider in multiple cycles | 0 |

## Completeness and dates

| Missing or unencoded field | Records |
| --- | ---: |
| `eligible_study_fields` | 4 |
| `eligible_nationalities` | 8 |
| `minimum_gpa` | 22 |
| `gpa_scale` | 22 |
| `minimum_ielts` | 12 |
| `living_stipend` | 1 |
| `application_deadline` | 8 |
| `application_cycle` | 2 |

All records have a provider, destination, master's level, tuition description, official source URL, verification date and additional conditions. NULL never means unrestricted or waived. GPA fields remain unencoded for conditional, country-specific or inverse-scale requirements (for example EMINENT's German grade criterion); the original terms remain in text. Missing numeric IELTS often means alternative tests/exemptions exist, not absence of a language condition. JEMARO's living support is unverified; IFRoS explicitly excludes it.

Deadlines relative to 2026-11-12: **2 past, 12 future, 0 today, 8 unknown**. Past MEXT and Stipendium Hungaricum calls are retained as historical, dated records, never rolled into a new cycle. A future deadline does not prove that a call is open.

## Review limits

- No complete executable eligibility rules were created from free-text pages. All 22 records retain unresolved requirements; confirmed failures, such as expired deadlines or funding-preference mismatches, can still produce `ineligible`.
- Full funding refers to the specified award's supported tuition and living-funding terms, not automatic selection or reimbursement of every ancillary charge. Partial-only JEMARO/IFRoS awards are distinct from historical EMJM full awards. DAAD, Stipendium Hungaricum and GIST exclusions remain explicit.
- CYBERSURE publishes 2027 admissions but labels scholarship rates/counts as 2026; the 2027 amount is unconfirmed. CyberMACS has no verified next intake/deadline. DEAI reports portal maintenance. AMASE has route-dependent deadlines, so the scalar date is null.
- EMIMEP's application body gives 2026/2027 dates but retains an older title; the applicable intake needs confirmation. DENSYS's January deadline uses the provider's questionable CEST label; no timezone correction or old-calendar rollover is invented.
- Generic scholarship schemes and funded study subjects do not establish a student's acceptable prior qualification. Admission, scholarship selection, nationality quotas, language alternatives and other individual conditions need separate review.

## Excluded research leads

| Lead | Official evidence / reason for exclusion |
| --- | --- |
| BDMA | [Official source](https://bdma.ulb.ac.be/): Official homepage says EC funding ended and directs new applicants to successor DEAI; omitted rather than count obsolete opportunity. |
| EMAI | [Official source](https://www.upf.edu/web/emai/scholarships-fees): Live 2027-2029 page mainly selects self-funded students; general EMS terms do not verify current scholarship availability. Current admission dates are explicitly self-funded. Omitted. |
| EMECS | [Official source](https://emecs.eit.uni-kl.de/): Official host not accessible for live verification; collection stopped and no record added. |
| SE4GD | [Official source](https://se4gd.lutsoftware.com/): Original programme ended August 2026 and has no new intakes; renewal is conditional. |
| MAIA | [Official source](https://maiamaster.org/admission/faqs/): FAQ says no EMJMD scholarships for 2026-2028. Renewal does not establish a funded 2027 call. |
| MIR | [Official source](https://www.master-mir.eu/admission-requirements/): Admission page says EMJMD unavailable for 2025/26 despite a generic old funding page. No current funded cycle verified. |
| FIPDes | [Official source](https://www.fipdes.eu/%3FFIPDes-application-Calendar-Deadlines): Current official calendar says no Erasmus Mundus awards for 2025-2027 or 2026-2028; no confirmed 2027 award. |
| SmartNet | [Official source](https://smartnet.astonphotonics.uk/participation-fees_and_scholarships/): Official funding information is tied to 2020-2022; no current funded intake verified. |

An inaccessible official host (EMECS) stopped collection for that programme. No record was invented to replace inaccessible or unsupported evidence.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m backend.app.catalogue_quality --as-of 2026-11-12 --evidence backend/data/catalogue_evidence.json
```

The CLI performs no network requests or database writes. [QUALITY_REPORT.json](QUALITY_REPORT.json) contains per-record gaps, dates and missing fields; [catalogue_evidence.json](catalogue_evidence.json) maps each programme to official-source paraphrases. [SOURCES.md](SOURCES.md) retains original evidence and the expansion index. This offline report checks completeness and provenance coverage; it cannot independently authenticate a curator's source claims.

## Executed compatibility checks

- Backend: **377 tests passed**, with warnings treated as errors. Coverage includes the unchanged-record fingerprints, import/idempotence, all catalogue pages/details, filters, conservative eligibility, source allowlists and model-directed tool dispatch with a mocked model.
- Frontend: **103 unit/integration tests passed** and **16 Chromium browser tests passed**. Browser assertions now use actual catalogue totals and navigate the larger ranked result set. ESLint, TypeScript, production build, Ruff lint/format and Python dependency checks passed.
- Local application import: **20 created, 0 updated, 2 unchanged**. Both original IDs and facts were checked before/after. Repeating the import returned **22 unchanged**, with no updates or deletions. SQLite files remain local and ignored by Git.
- Optional real Qwen/Ollama smoke: HTTP 200 in **6.03 seconds**, four model rounds, one executed search. `search_scholarships(field="Computer Science", funding_type="fully_funded")` found nine matches and returned three candidates. Invalid model selections were rejected; the final result was `no_matches` with no grounded recommendations. This is a model-quality limitation, not evidence that no scholarships exist. The deterministic APIs and scripted agent integration tests passed. No generated facts or eligibility overrides were exposed.

The browser runner initially completed assertions but stalled when its Windows process-tree cleanup was sandboxed. The authorized rerun completed with exit 0 and released both local test-server ports. No product changes were needed for teardown. These checks do not establish the academic accuracy, extraction or recommendation-quality targets in PROPOSAL.md.
