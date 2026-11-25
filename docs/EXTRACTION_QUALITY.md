# Phase 8C scholarship extraction and evidence validation

**Run date — 2026-11-25.** The baseline and revised runs used the same seven
Phase 8B UTF-8 files, exact-byte SHA-256 inputs and original retrieval date.
Both used local Ollama with `qwen3:4b-instruct`. The original queue and pilot
artifacts remain available. The revised run used a separate local queue.
[Phase 8B pilot and official sources](CATALOGUE_EXPANSION_PILOT.md)

## Diagnosis

The Phase 8B extractor asked for an open-ended object with 13 optional
fields. On replay, all seven responses stopped normally. Qwen returned only
name and provider keys. There were zero JSON/schema failures and zero
nonliteral spans dropped, so transport, schema validation and exact matching
do not explain the omissions. The old exact-match rule admitted three clear
provider misattributions because it checked whether text occurred in the
input without checking what the text described.

| Frozen input | Evidence present | Evidence insufficient or omitted |
| --- | --- | --- |
| Chevening Kazakhstan | Route heading and the eligible UK taught master's description | Employer, sponsor identity, and date absent. A closed banner cannot supply a deadline. The revised model selected the degree span but abstained on name and destination. |
| Oxford Clarendon | Named fund, eligible graduate degrees and fees plus living support | No rate, currency, intake or deadline. The supplied span cannot set a fixed stipend or assign a nationality condition. |
| UCA Cambridge | Named award, master's and doctoral levels, and a list of applicant countries | No express provider relationship, funding terms, or dated call in this excerpt. |
| MAECI Italy | Call heading with destination and an academic year | The country and date fragments lack their eligibility and closing clauses. The revised model omitted the academic year even though the heading contains it. The source should be revisited separately for the complete closing statement. |
| Türkiye Scholarships | Graduate route, degree terms, destination and subjects | The monetary fragment lacks the stipend label and cadence. It does not support a complete payment observation. The revised model omitted the destination and supported-subject context. |
| ADB–Japan | Award heading, designated master's courses, citizenship fragment naming Kazakhstan, and tuition plus living support | Japan in the name cannot supply a study destination. The citizenship fragment can support Kazakhstan's inclusion but cannot establish an exhaustive list. No cash amount is stated. |
| McCall MacBain | Award, degree, general full-award wording and the 2027 cohort | The explicit June 2026 date is an opening date. The excerpt has no stipend, currency, payment period or deadline. Those payment figures were tested separately. |

## Extraction and review behavior

- The collector identifies candidate passages for each field using contextual
  relationships. A provider needs evidence that the organization funds or
  operates the award. Study destination needs a recognized country in a study
  clause. A deadline needs a valid date linked to an actual closing statement.
  GPA, language and prior degree need explicit requirement or accepted-evidence
  context. Qualifications, alternatives and scope remain part of the quote.
- Local Qwen receives the untrusted excerpt and short numbered options in one
  tool-free call. Each offered field must receive an allowed integer, with zero
  meaning abstention. Qwen cannot return a new quote, URL, date or review
  decision. With no supported options, extraction abstains without a model call.
  Staging rechecks the exact text and the field relationship of each new claim.
- Stipend observations retain exact source offsets, URL, retrieval date, amount,
  currency, cadence and payment scope. Publication year and intake cycle require
  explicit attribution. The collector leaves the scalar amount empty when
  competing observations differ and keeps the observations for review. It also
  abstains when multiple deadlines or cycles compete.
- The rules cover recognizable English constructions. An accepted span remains
  provisional and may need additional programme or cycle context. The rules
  can miss valid paraphrases and evidence spread across documents. The model
  can abstain despite usable evidence. Approval still requires independent
  review of the original source and a human-authored record.

## Measured comparison on the seven frozen excerpts

The denominator is the original 13 fields per excerpt. Structured stipend
metadata is additional and does not inflate the 91-field denominator.

| Measure | Baseline replay | Revised run |
| --- | ---: | ---: |
| Drafts with at least one field | 7 | 7 |
| Populated fields / 91 | 10 | 19 |
| Fields whose span occurs verbatim in the input | 10 | 19 |
| Fields passing the revised contextual rules | 7 | 19 |
| Clear field misattributions found in development review | 3 | 0 spotted |
| Nonliteral claims returned or retained | 0 | 0 |
| Funding conflicts evidenced in the frozen inputs | 0 | 0 |
| Model, schema or evidence validation failures | 0 | 0 |
| Real model calls | 7 | 7 |
| Median wall time per excerpt | 0.897 s | 0.830 s |

| Input | Baseline populated | Revised populated |
| --- | ---: | ---: |
| Chevening Kazakhstan | 2 | 1 |
| Oxford Clarendon | 1 | 3 |
| UCA Cambridge | 1 | 3 |
| MAECI Italy | 2 | 2 |
| Türkiye Scholarships | 2 | 2 |
| ADB–Japan | 1 | 4 |
| McCall MacBain | 1 | 4 |

The baseline assigned a Chevening country heading, the name of Italy, and a
generic phrase about Turkish universities to provider slots. The revised
extractor left those slots null. The comparison documents completeness and a
development check for obvious errors. Independently verified semantic
accuracy, precision and recall are **not evaluable** until reviewers annotate
the excerpts. These seven inputs also informed development.
Baseline wall time ranged from 0.859 to 7.033 seconds and included the
initial model warm-up. The revised range was 0.752 to 1.084 seconds.
These timings cover extraction through validation and exclude SQLite writes.
The model was already warm for the revised run, so the comparison cannot
isolate a speed improvement.

## Separate McCall MacBain funding regression

The frozen McGill input contains no stipend, so its amount stayed null. A
separate offline regression used manually supplied short excerpts from three
official documents and produced four structured payment observations.

| Evidence | Observed rate and scope | Temporal treatment |
| --- | --- | --- |
| Historical brochure | CAD 2,000 per month during academic terms | Brochure timeline and dated McGill reporting tie this material to September 2023 entry. [Brochure](https://mccallmacbainscholars.org/wp-content/uploads/2022/06/2022-McCall-MacBain-Scholarships-Brochure-USA-WEB.pdf) · [McGill 2023 announcement](https://www.mcgill.ca/newsroom/channels/news/meet-first-global-cohort-mccall-macbain-scholars-347820) |
| FAQ scholarship coverage | CAD 2,300 per month during academic terms | Current FAQ coverage entry adjacent to 2027 application information. The stipend clause itself has no cycle. [FAQ](https://mccallmacbainscholars.org/faq/) |
| FAQ duplicated coverage entry | CAD 2,000 per month during academic terms | The clause has no stated cycle. Keep this occurrence separate from the dated historical observation. [FAQ](https://mccallmacbainscholars.org/faq/) |
| Programme overview | 2,300 per month during academic terms | The overview corroborates the higher figure and uses a bare dollar sign. Currency from this span alone stays null. [Programme overview](https://mccallmacbainscholars.org/program/) |

The parser flagged two comparable pairs with unresolved time scope. One pair
is the contradictory FAQ clauses and one compares the historical brochure
with the current FAQ. Both amounts remain available for review. The reviewer
must confirm the applicable award cycle and stipend with the provider before
approval. Academic-term coverage supplies no year-round payment guarantee.

## Reproduction and human review

The original files are under `.local-run/collection/phase-08b/`. Read the
existing `manual-inputs.json` for the seven input IDs and official URLs. The
baseline and revised timing summaries, the revised queue and the separate
stipend observations are in the ignored `.local-run/collection/phase-08c/`.
To repeat a collection run, use a fresh queue and the original retrieval date.
This example uses the first frozen excerpt.

```powershell
$queue = '.local-run/collection/phase-08c/replay.sqlite3'
$url = 'https://www.chevening.org/scholarship/kazakhstan/'
\.venv\Scripts\python.exe -m backend.collection --stage-db $queue collect $url --manual-text .local-run/collection/phase-08b/chevening-kz.txt --retrieved-on 2026-11-25
\.venv\Scripts\python.exe -m backend.collection --stage-db $queue list
\.venv\Scripts\python.exe -m backend.collection --stage-db $queue inspect FULL_DRAFT_ID
```

Use one blank review sheet per independent reviewer. Annotate the excerpt
first, then score blinded A/B output. Resolve identity, factual support, scope,
currency and chronology before proceeding to an approval decision.
[Human annotation package](EXTRACTION_QUALITY_REVIEW.md)

All seven revised drafts are pending review. Zero reviews or publications
were recorded. Permission and registry entries remain as recorded in Phase 8B.
The collector made no provider requests, and the active catalogue has 22 records.

## Verification

- **838 backend tests** passed with warnings treated as errors. Regression
  fixtures cover wrong-field exact quotes, absent evidence, dates and opening
  versus closing semantics, and conflicting amounts, currencies and periods.
- **207 frontend tests** and **22 Chromium tests** passed. Browser checks
  used temporary loopback servers and a temporary catalogue, with mocked
  AI responses for controlled cases.
- Ruff lint and formatting, ESLint, TypeScript, the Vite production build,
  installed dependency checks and the Git whitespace check passed.
- The before/after comparison used the real local model. The supplemental
  McCall MacBain regression exercised the separate deterministic funding
  parser with manually supplied official excerpts.
