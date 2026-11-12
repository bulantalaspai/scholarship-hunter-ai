# Scholarship Hunter AI

A course project for students from Kazakhstan seeking fully funded master's
scholarships abroad. See [PROPOSAL.md](PROPOSAL.md) for the planned application.

## Current scope: Phase 6B

The React/TypeScript application now supports scholarship discovery, details,
student profiles, eligibility results, and grouped matches. The original
connection check and health endpoint are preserved. The FastAPI/Pydantic v2 backend provides a local SQLite scholarship
catalogue through SQLAlchemy 2.0, an explicit curated-JSON importer, and read-only
search/detail endpoints. Phase 3 adds stateless, deterministic eligibility
checks and grouped profile matching. The catalogue now contains **22 real,
source-backed scholarship records** (20 additions and two preserved originals):
16 full-award schemes and six partial-award schemes. It is not a list of guaranteed
or currently open opportunities. All 22 still need further applicant-specific
eligibility verification.

An optional, model-directed local Ollama agent now selects candidates through
four validated tools. Existing catalogue, eligibility, ranking and health APIs
work independently of Ollama. Applicant accounts remain outside the scope.
Phase 6B adds synthetic evaluation data, reproducible baseline and real-model
experiments, and deterministic candidates when a model run has no validated
selection. Measured results and annotation limits are documented in
[the evaluation report](docs/EVALUATION_REPORT.md).
No database server, paid API, cloud account,
credentials, or personal student data is required. All application data stays
in a local SQLite file. Development servers bind to `127.0.0.1` only.

## Local setup (Windows PowerShell)

Use the existing root `.venv` with Python **3.14.2**, Node.js **24.19.0**, and
npm **11.17.0**. Commands use `npm.cmd` to avoid PowerShell's `npm.ps1` execution
policy restriction; no execution policy change or virtual environment activation
is required.

From the repository root, install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
```

For a fresh checkout without `.venv`, create it once with
`py -3.14 -m venv .venv` before installing dependencies. Do not recreate an
existing compatible environment.

Start the backend in one terminal from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Startup creates missing catalogue tables but never imports records automatically.
Use the import instructions below to populate the catalogue.

Start the frontend in a second terminal from the repository root:

```powershell
npm.cmd --prefix frontend run dev
```

Open **http://127.0.0.1:5173**. The page checks the API automatically and supports
retrying after a failure. Checks time out after five seconds. Ports 5173 and
8000 must be available; the frontend does not silently choose another port.

Import the curated records using the database instructions below before browsing.
A fresh, unseeded database correctly shows an empty catalogue; the UI never
substitutes demonstration records.

## Using the frontend

- **Home** (`#/`): enter a study field to begin searching, open your profile,
  or retry the existing API connection check.
- **Explorer** (`#/explore`): browse cards and apply country, study-field, and
  funding filters together. Filters and pagination live in the hash URL, so
  browser Back/Forward and shared search links work. Country is an exact name;
  field is a literal substring search. There is no unsupported name/keyword API.
- **Scholarship details** (`#/scholarships/{id}`): read funding descriptions,
  deadlines, requirements and caveats, with official links and verification dates.
  Missing data is visibly unconfirmed; a source date does not prove a call is open.
- **My profile** (`#/profile`): enter only academic information, scores and funding
  preferences. A detail-page eligibility action preserves the selected scholarship.
  GPA and scale must be supplied together; optional blank scores stay null.
  Degree completion can explicitly remain unspecified. Validation errors are
  linked to controls and move focus to the first field needing correction.
- **Eligibility results** (`#/results/{id}`): view the backend verdict, separate
  admission/funding/application checks, missing information, explanations,
  suggestions and supporting sources. Unverified conditions are never converted
  into positive results. A check never guarantees admission or an award.
- **My matches** (`#/matches`): compare the submitted profile against the catalogue.
  Eligible, Needs verification and Ineligible records remain separate, with
  global counts, backend ranking explanations and pagination. When none are
  verified eligible, the interface says so explicitly.
- **AI recommendations** (`#/agent`): explicitly submit your in-memory profile
  and a short goal to the local model. Read deterministic assessments, missing
  evidence, sources and the actual tool-attempt trace. Nothing calls the model
  automatically; ordinary matches remain available when Ollama is offline.

Profiles exist only in React memory, with no cookies, local/session storage,
accounts or external authentication. Submitting requests sends the profile only
to the local FastAPI application using its existing POST endpoints; nothing is
saved in the application database. Use **Clear profile** on the profile page to
remove it, or refresh/close the tab. Direct result links after a refresh ask for
a new profile. Never put student scores or nationality into shared URLs.

The interface includes keyboard navigation, a skip link, visible focus, labeled
controls, status announcements, reduced-motion support, and layouts for mobile
through desktop. Loading, empty, invalid-link, not-found and retryable failure
states are explicit. Official links open a new tab safely. Requests are cancelled
when obsolete; health checks time out after 5 seconds and catalogue/eligibility
requests after 15 seconds. Unexpected response shapes, inconsistent eligibility
summaries and unsafe source URLs produce errors rather than guessed results.

No frontend dependencies were added. The app uses React, native hash navigation,
the browser Fetch API, and the existing Vite `/api` proxy. TypeScript contracts
mirror the actual backend schemas; the backend remains the decision authority.

- Health endpoint: **http://127.0.0.1:8000/api/health**
- Interactive API documentation: **http://127.0.0.1:8000/docs**
- OpenAPI schema: **http://127.0.0.1:8000/openapi.json**

Vite forwards `/api` requests to `http://127.0.0.1:8000`, keeping browser requests
on the same origin without permissive CORS settings. The frontend production
build is generated in `frontend/dist`; a deployed frontend will need an
equivalent `/api` reverse proxy. Production deployment is outside this phase.

## Database initialization and import

By default, the database is **`backend/data/scholarships.sqlite3`**, resolved
relative to the backend package rather than the terminal's working directory.
Database files and journals are ignored by Git. Initialize and populate it from
the repository root:

```powershell
.\.venv\Scripts\python.exe -m backend.app.import_catalogue init
.\.venv\Scripts\python.exe -m backend.app.import_catalogue import backend/data/curated_scholarships.json
```

Both commands are safe to repeat. Initialization creates missing tables without
dropping records; it is not a schema migration system. The importer validates
the whole file before writing and commits all records in a single transaction.
It prints JSON counts for `created`, `updated`, `unchanged`, and `skipped_older`.

Record identity is the normalized scholarship name, provider, and application
cycle, backed by a unique database constraint. Case and whitespace variations do
not create duplicate records; different cycles remain separate. Exact duplicates
within a file collapse, while conflicting duplicates reject the entire import.
Same-date or newer complete snapshots can update existing records without
changing their IDs; older verification dates cannot overwrite newer records.
An import is a complete record snapshot, not a patch: `null` replaces a prior
value with unknown information. No records are deleted by import. Renamed
programmes or corrected cycle identities need manual reconciliation.

To use another **local file**, configure the API and importer with the same path:

```powershell
$env:SCHOLARSHIP_DATABASE_PATH = 'C:\local-data\scholarships.sqlite3'
```

Alternatively, override the import command's path explicitly (before the subcommand):

```powershell
.\.venv\Scripts\python.exe -m backend.app.import_catalogue --database-path backend/data/other.sqlite3 init
```

Relative custom paths resolve from the current working directory. URLs and UNC
network shares are rejected. Do not configure a remote filesystem or cloud sync
location for the database.

### Curated JSON format and unknown values

Use [the curated JSON file](backend/data/curated_scholarships.json) as the import
template and [source notes](backend/data/SOURCES.md) for its official evidence.
The document has `schema_version: 1`, `data_kind: "curated"`, and a `scholarships`
array. Each record requires a nonblank name/provider, an official HTTPS source
URL, and a non-future ISO verification date. Unknown keys and invalid values are
rejected. Do not change verification dates without checking the sources again.
The importer reads local JSON only; it does not scrape or contact any API.

- `destination_country` is a nullable **list of country names** to preserve
  joint programmes' international mobility. A single string is also accepted
  on import and normalized to a list.
- `eligible_study_fields` and `eligible_nationalities` are nullable, nonempty
  lists of documented values. `null` means unknown; an empty list is rejected.
  `Worldwide` is a descriptive source scope, not a country code.
- Missing GPA, IELTS, funding amounts, restrictions, dates, or study fields stay
  `null`, never zero, an empty list, or an implied waiver. `funding_type` defaults
  to `unknown`; its other values are `fully_funded` and `partially_funded`.
- Minimum GPA requires a positive known scale and cannot exceed it. IELTS scores
  must be between 0 and 9. Alternative language evidence and conditional rules
  belong in `additional_requirements`; a numeric score alone is not an
  eligibility decision.
- `tuition_coverage` and `living_stipend` are nullable descriptions, preserving
  currency, duration and limitations. Fully funded records require both fields
  and a curator's review of official funding terms; the importer cannot prove
  that arbitrary source content is authentic. DAAD's initial record excludes
  tuition and is therefore **partially funded**.
- `application_deadline` and `last_verified_at` use ISO calendar dates
  (`YYYY-MM-DD`); the latter is required. Supplementary official links, caveats,
  and any uncertainty belong in `notes`. Import does not establish that a call
  is currently open, or that its deadline applies to every nationality.

### Verified data expansion and quality report

The 20 additions were reviewed against official programme, university or provider
pages on **2026-11-12**. The original two records and their **2026-11-11** source
dates are unchanged. The importer, schema and existing import command are reused;
there is no automatic scraping, separate database service or paid API.

- [Source index](backend/data/SOURCES.md) and
  [per-source evidence](backend/data/catalogue_evidence.json) document claims,
  supplementary admission/funding pages and unresolved conditions.
- [Quality summary](backend/data/QUALITY_REPORT.md) and
  [machine-readable report](backend/data/QUALITY_REPORT.json) record funding,
  null fields, duplicates, dates, per-record gaps and excluded research leads.
- The snapshot has **0 duplicate identities**, **16 fully funded** and **6
  partially funded** schemes. Eight deadlines are unknown; two are past and
  retained as closed historical calls. Future dates never prove opening status.
- No complete structured eligibility policy was inferred from narrative pages.
  Conditional language routes, non-comparable GPA criteria and scholarship
  selection conditions remain explicit. Admission and award selection are
  separate; all 22 require further eligibility verification.

Regenerate the offline JSON report without touching SQLite or contacting sources:

```powershell
.\.venv\Scripts\python.exe -m backend.app.catalogue_quality --as-of 2026-11-12 --evidence backend/data/catalogue_evidence.json
```

Omit `--as-of` to use the server's current UTC date. For a saved UTF-8 report in
Windows PowerShell, pipe to `Set-Content -Encoding utf8`; its plain `>` redirection
may otherwise write UTF-16. The CLI checks source metadata/provenance coverage and
completeness; authenticating official facts still requires manual source review.
Do not advance source dates or roll deadlines forward without that review.

New primary official URLs are individually added to the existing AI fetcher's
exact allowlist. Domain wildcards, arbitrary URLs and local-network access remain
disallowed. A source page can still fail the existing size, timeout or redirect
limits; the agent keeps missing evidence unresolved.

Fictional demo data is clearly labeled under `backend/tests/fixtures/` and is
never seeded at startup. The CLI rejects `data_kind: "fictional_demo"`; only tests
explicitly opt into importing it into temporary databases.

## Scholarship API

The following examples work after importing the curated file and starting the API:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/scholarships'
Invoke-RestMethod 'http://127.0.0.1:8000/api/scholarships/1'
Invoke-RestMethod 'http://127.0.0.1:8000/api/scholarships?country=Germany'
Invoke-RestMethod 'http://127.0.0.1:8000/api/scholarships?field=Engineering'
Invoke-RestMethod 'http://127.0.0.1:8000/api/scholarships?funding_type=fully_funded'
Invoke-RestMethod 'http://127.0.0.1:8000/api/scholarships?country=Finland&field=Engineering&page=1&page_size=10'
```

Use an ID returned by the list endpoint for detail requests. Country filtering
matches an entire destination name; field filtering finds a literal substring
within an individual documented field. Both ignore case (including Unicode),
and multiple filters combine with AND. SQL parameters are bound; `%` and `_`
are literal characters, not wildcard operators. Unknown fields or destinations
do not match filters; this does **not** mean an applicant is ineligible.

The list response has this shape, including for an empty catalogue:

```json
{"items": [], "total": 0, "page": 1, "page_size": 20}
```

`total` counts all matches before pagination. Results sort by stable record ID.
`page` defaults to 1 (range 1–1,000,000); `page_size` defaults to 20 (range 1–100).
An out-of-range result page is an empty list with the matching total. Blank or
overlong filters, unsupported funding values, invalid IDs, and unknown query
parameters return **422** with FastAPI's standard `detail` validation errors.
An absent positive ID returns **404** with `{"detail": "Scholarship not found"}`.
Detail responses return a scholarship object with explicit nullable fields,
official source URL, and verification date. No catalogue write endpoints are exposed.
The health endpoint retains its original JSON contract.

## Eligibility API

`POST /api/eligibility/check` accepts a scholarship ID and a student profile.
Use an ID returned by the catalogue. Profiles are evaluated in memory; they are
not saved to SQLite or logged by the application. Do not send names, contact
details, documents, or credentials. Extra input fields are rejected.

```powershell
$request = @{
  scholarship_id = 2
  profile = @{
    nationality = 'Kazakhstan'
    degree_level = 'bachelor'
    degree_completed = $true
    field_of_study = 'Computer Science'
    gpa = 3.5
    gpa_scale = 4.0
    ielts_overall = 7.0
    intended_start_year = 2027
    funding_preference = 'fully_funded'
  }
} | ConvertTo-Json -Depth 4
Invoke-RestMethod 'http://127.0.0.1:8000/api/eligibility/check' -Method Post -ContentType 'application/json' -Body $request
```

Nationality, degree level, field, start year, and funding preference are required.
Degree levels are `high_school`, `associate`, `bachelor`, `master`, `doctorate`,
and `other`. `degree_completed` is optional: omitting it does not prove completion.
GPA and scale may both be omitted (unknown), but must otherwise be supplied
together as finite numbers, with `0 <= gpa <= gpa_scale` and a positive scale.
IELTS overall is optional and must be a finite number between 0 and 9.
Funding preference is `fully_funded` or `any_funding` (full or partial acceptable).
Years are integer calendar years (1900–2200); a past start year fails the current
intake check. Invalid input returns 422; an absent scholarship returns 404.

The response includes the following fields (this is an illustrative **excerpt**
for an incompletely reviewed record, not a promise about any programme):

```json
{
  "scholarship_id": 2,
  "status": "needs_verification",
  "admission_status": "needs_verification",
  "funding_status": "needs_verification",
  "application_status": "needs_verification",
  "requirements": [
    {
      "requirement": "language",
      "scope": "admission",
      "status": "unknown",
      "explanation": "Language alternatives, exemptions, or test conditions are unresolved.",
      "suggestion": "Verify language evidence, exemptions, and required component scores."
    }
  ],
  "unknown_requirements": ["language"]
}
```

Full responses also contain the scholarship name, matched/failed/unknown
requirement names, deduplicated suggestions, an overall explanation, official
source URL, catalogue verification date, applicable rule sources and review date,
server evaluation date, and a disclaimer. Individual results are `met`, `failed`,
or `unknown`; the full requirement list is authoritative, while the name lists
are convenient summaries.

### Decision rules

- `eligible`: every modeled mandatory condition is positively verified.
- `ineligible`: at least one confirmed condition fails for this record and the
  supplied funding preference. Failures take precedence over unknowns.
- `needs_verification`: no confirmed failure exists, but at least one mandatory
  condition is unknown.

Admission, funding, and application statuses are calculated separately. Partial
funding can fail a full-funding preference while admission conditions still pass.
Neither admission checks nor advertised funding imply selection or an award.

Nationality and fields use normalized **exact** matches (Unicode, whitespace and
case normalization). Related fields, aliases, and grade equivalences are not
guessed. Nonmatching values are failures only when a curator has explicitly
verified an exhaustive restriction list. A catalogue `Worldwide` scope is
recognized. Other missing or non-exhaustive scopes require verification.

The awarded `degree_level` must be master; accepted **prior** qualifications are
a separate reviewed rule. An unfinished matching degree needs confirmation of
completion timing. GPA is compared only on exactly matching scales, without
ratio conversions. An absent GPA threshold is unknown unless an explicit
no-minimum rule is reviewed.

IELTS comparisons are decisive only for a reviewed unconditional IELTS-only
route. Conditional routes, alternatives, exemptions, and missing required
component scores remain unknown. A low overall score cannot disqualify a student
when another language route may apply. Suggestions are limited to documented
gaps and further verification, not promises of approval.

Deadline checks use the **server's UTC calendar date**. A passed deadline fails
for that record; it is never rolled forward to another year. Deadline-today is
unknown because time and timezone are not stored. A future deadline does not
prove a call is open. Intake years come from explicit reviewed rules, never from
parsing a descriptive application-cycle label. Opening status and funding
availability must be reviewed separately.

### Curator-reviewed rules

Phase 2 records remain valid and unchanged. Their free-text notes are not parsed
into executable conditions. None of the 22 current real records has a complete
structured review, so they cannot receive an overall `eligible` result
until unresolved requirements are verified. Confirmed failures can still apply.

Curators can optionally add `eligibility_rules` to a record in the existing
JSON import format. For example, the following describes **fictional test
conditions only**, and must never be copied onto a real programme without evidence:

```json
{
  "source_urls": ["https://example.org/fictional-engineering"],
  "verified_at": "2026-01-01",
  "nationality_scope": "listed_only",
  "field_scope": "listed_only",
  "accepted_prior_degrees": ["bachelor", "master"],
  "gpa_requirement": "minimum",
  "language_requirement": "ielts_only",
  "minimum_ielts_component": null,
  "intake_year": 2027,
  "call_open": true,
  "funding_available": true,
  "no_additional_admission_requirements": true,
  "no_additional_funding_requirements": true
}
```

All unprovided rule conditions default to unknown/unreviewed. Nationality and
field scope may be `listed_only`, `any`, or `unknown`; listed-only rules use the
catalogue's nonempty lists. GPA requirement is `minimum`, `none`, or `unknown`.
Language requirement is `ielts_only`, `none`, `conditional`, or `unknown`.
Minimum rules require corresponding catalogue thresholds. Explicit waivers
cannot contradict numeric thresholds. A component minimum prevents an overall
IELTS score alone from satisfying the language condition.

The two `no_additional_*_requirements` assertions mean **no unmodelled mandatory
student conditions remain**, not merely that the page has been read. Experience,
prior awards, degree equivalence, component scores, or separate admission
requirements that are not represented in the profile must remain unresolved.
Opening and availability flags refer to applying for a published opportunity,
not to approval of an individual student's award.

Rules are stored in an additive `scholarship_eligibility_policies` table created
at initialization/startup; existing scholarship columns are unchanged. Foreign
keys are enforced. Each policy is bound to a fingerprint of all catalogue facts.
Changes invalidate a mismatched policy. Complete snapshot imports replace rules;
omitting rules removes the old policy. Policy-only updates are counted as updates,
and older facts or rule reviews cannot overwrite newer ones. All changes remain
in the same atomic import transaction.

Rule review dates must be non-future and on/after the catalogue verification date.
Only matching policies reviewed within **30 days** of evaluation are used. This
is a conservative review window, not a guarantee that a source has not changed.
Expired or invalid policies cannot prove eligibility; ask the provider to
reconfirm even within the window. No student request can supply rules, a review
date, or an evaluation-date override. The fictional example above is intentionally
historical and is not valid current evidence.

### Profile matching and ranking

`POST /api/eligibility/matches` takes `{ "profile": { ... }, "page": 1,
"page_size": 20 }` using the same profile contract. It returns separate
`eligible`, `needs_verification`, and `ineligible` arrays, plus global `counts`,
`total`, `page`, and `page_size`. Each item contains its complete `assessment`
and human-readable `ranking_reasons`.

All records are assessed before global pagination. Group order is eligible,
needs verification, then ineligible. Within a group, published full funding
precedes partial funding and unknown funding, then exact field matches precede
unmatched fields; record ID breaks ties. Confirmed preference failures stay in
the ineligible group. No eligibility percentages or admission probabilities are
generated. Counts cover all results, not only the page. Page bounds match the
catalogue API, and an empty database yields empty groups.

This simple matcher scans the local catalogue and is intended for the small
course-project dataset. It does not perform fuzzy matching, infer unstructured
restrictions, convert GPA scales, process alternative test documents, or assess
conditions absent from the profile. Additional profile fields and structured
rules require further design before those conditions can be automated safely.

## Local AI agent

Run the existing **Ollama 0.40.16** service on **127.0.0.1:11434** with the
already-installed **qwen3:4b-instruct** model. No SDK, model download, cloud
inference or new dependency is needed. Check availability locally:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/version
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Start FastAPI and Vite with the usual commands above. The **AI recommendations**
navigation item reuses the student profile form and requires an explicit request.
An Ollama outage never prevents startup or ordinary search/eligibility/matching.

### Request and response

`POST /api/agent/recommend` takes `profile` with the exact existing
`StudentProfile` schema and an optional trimmed `goal` (1–300 characters).
The serialized profile is limited to 1,500 UTF-8 bytes for the small context.
Synthetic example, from PowerShell:

```powershell
$body = @{
  profile = @{
    nationality = 'Kazakhstan'; degree_level = 'bachelor'; degree_completed = $true
    field_of_study = 'Computer Science'; gpa = 3.5; gpa_scale = 4.0
    ielts_overall = 7.0; intended_start_year = 2027
    funding_preference = 'fully_funded'
  }
  goal = "Find funded master's candidates related to my field."
} | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:8000/api/agent/recommend -Method Post -ContentType 'application/json' -Body $body
```

The typed response contains `status`, `model`, `evaluated_on`, `steps`,
`tool_calls`, `recommendations`, `message`, `warnings`, `tool_trace` and
`disclaimer`, plus `fallback_recommendations` and `fallback_reason`.
Each recommendation uses the existing `RankedProgramme` contract with a full
deterministic `assessment` and `ranking_reasons`, including official
source links, catalogue/rule review dates, unknowns and individual checks.
Statuses are `completed`, `needs_verification`, `no_matches` or `limit_reached`.
The overall agent status does not replace individual eligibility classifications;
confirmed failures still take precedence over unknown requirements.

When a completed model run has no grounded selection or reaches its budget,
the server can reassess its retrieved records and return up to three
`needs_verification` candidates in `fallback_recommendations`. The UI labels
these **Deterministic candidates to verify** and shows the reason, rule checks,
official links and dates. The model's status, recommendations and attempted-tool
trace retain their original values. Fallback assessment preserves the IDs
previously assessed by model-requested tools. Ollama transport/protocol errors use
the documented HTTP error responses and the ordinary matches link.

Trace entries expose validated tool arguments, a safe summary and outcome;
successful page reads also include their source and retrieval timestamp.
Rejected arguments, raw pages, model prose/thinking and student profiles are
not included in the trace. The application does not log or persist profiles,
prompts, traces or agent results. Only the local Ollama service receives the
profile; outbound source requests contain no profile or goal.

Validation errors return **422**, unavailable/busy Ollama **503**, inference
timeouts **504**, and invalid/truncated/oversized model responses **502**.
The frontend offers ordinary deterministic matching after errors. One AI request
per backend process is admitted at a time to avoid a GPU inference queue.

### Tools, grounding and limits

Qwen chooses tool calls and arguments from live results; there is no scripted
retrieve/check/rank sequence or automatic fallback pretending to be AI.

- `search_scholarships(country?, field?, funding_type?)`: the existing SQLite
  filters, with at most three candidates per search. Country means destination,
  not nationality. Omit filters to broaden the search.
- `fetch_official_page(url)`: reads only a discovered record's approved source.
  An additional exact URL allowlist covers the reviewed catalogue sources.
  HTTPS/443, public-IP checks on every hop, DNS-pinned TLS, at most two approved
  redirects, a six-second deadline, 64 KiB bodies and content-type limits apply.
  Environment proxies, private/local/reserved IPs, arbitrary query parameters
  and unapproved redirects are disallowed. DNS work is bounded to two workers.
- `check_eligibility(scholarship_id)`: the existing deterministic engine,
  always using the original submitted profile and the server's evaluation date.
- `rank_scholarships(scholarship_ids)`: the existing ranking service, at most
  three discovered IDs, with eligibility classifications preserved.

Every argument and service result is validated. Model-selected recommendations
require IDs discovered and assessed through model-requested tools. The model selects
IDs only; server services attach all facts and determine the displayed order.
Model-written claims, invented IDs and attempted classification/profile overrides
are rejected. Web excerpts are explicitly untrusted; they cannot update catalogue
facts, review dates or eligibility rules. Reading a page is not verification by
a curator, and missing evidence remains `needs_verification`.

Limits are **four model steps**, **eight total attempted tool calls** (invalid
attempts count), **90 seconds overall**, **45 seconds per model call**, and
**4,096 context tokens** with at most 384 output tokens. Tool results are bounded
to 3,200 UTF-8 bytes; page text is further reduced to 600 characters. A conservative
input-size heuristic stops oversized conversations before inference; reported
Ollama prompt-token counts are checked too. The heuristic is not a tokenizer.
Budget exhaustion returns an explicit model status. A separately labeled
deterministic fallback can accompany that response using retrieved records.

The 4B model may choose poor filters or miss candidates. This is a small curated
catalogue assistant, not an exhaustive scholarship search or a new eligibility
authority. All 22 current records still lack complete reviewed rules. Strict source
limits can reject large, compressed or redirected official pages; these failures
remain visible and never establish missing requirements. No automatic extraction,
database mutation, model downloads, accounts or admission guarantees are added.

### Optional real-model smoke test

Normal tests mock Ollama and network transport. To explicitly exercise the real
installed model against the typed endpoint using **synthetic academic input** and
a temporary database seeded from the unchanged curated catalogue:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.smoke_agent
```

The command prints HTTP status, timing, actual per-round prompt-token counts,
requested tools, the complete response and execution trace. It never writes to
the application database or pulls a model. Exit codes: 0 for a completed response
(including no matches), 1 for an HTTP error, 2 for a step/context budget stop.
See [the recorded Phase 5 live example](docs/AGENT_SMOKE.md) for measured behavior
against the original two-record catalogue. The expanded catalogue can produce
different candidates and model-selected plans; normal limits still apply.

## Academic evaluation

[Evaluation data](evaluation/data/README.md) defines 20 synthetic profiles,
60 eligibility cases, 80 relevance judgments and 12 short official-source
extraction examples. Source-backed negative labels, provisional expectations
and unresolved judgments carry explicit statuses. Team adjudication is pending.

Run the deterministic baseline locally from the repository root:

```powershell
.\.venv\Scripts\python.exe -m backend.evaluation.run --output "$env:TEMP\scholarship-baseline-evaluation.json"
```

Run the installed local model on all 20 recommendation requests, 60 case-specific
audits and 12 extraction examples:

```powershell
.\.venv\Scripts\python.exe -m backend.evaluation.run --real-model --output "$env:TEMP\scholarship-evaluation.json"
```

Continue an interrupted run with the same output path:

```powershell
.\.venv\Scripts\python.exe -m backend.evaluation.run --real-model --resume --output "$env:TEMP\scholarship-evaluation.json"
```

The runner uses temporary SQLite data and records an atomic checkpoint after each
request. Resume verifies normalized input and implementation hashes, the fixed
assessment date, Ollama version and model digest. The JSON contains per-profile
results, case verdicts, model-round diagnostics, tool traces, timings and explicit
metric denominators. The extraction task is an evaluation-only excerpt probe.
Its annotations are excluded from model input.

The recorded experiment and its error analysis appear in
[EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md). Accuracy on source-backed
negative cases, draft-label agreement, source-excerpt extraction scores, reference
presence and audited source support have defined sample scopes. Proposal-level
targets remain **NOT EVALUABLE** where gold classes, independently verified
positive relevance or complete claim audits are missing. Ordinary test commands
below use mocked inference and source transport.

## Tests and checks

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m ruff format --check backend
.\.venv\Scripts\python.exe -m pip check
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

Backend tests use isolated temporary SQLite files, including the original health
tests. They cover schema creation and constraints, persistence, import and update,
duplicate prevention, transaction rollback, unknown requirements, filters,
pagination, invalid parameters, 404s, and API documentation. No live source
requests or production database writes occur during pytest. Frontend tests cover
loading, valid and invalid responses, network failures, retry, and cancellation.
Agent tests additionally exercise real tool dispatch behind scripted model replies,
malformed arguments/results, prompt injection, model-selected alternative plans,
unknown evidence, tool/context/time budgets, safe source fetching and Ollama
outages. Browser AI responses are mocked so browser tests do not require a GPU;
existing catalogue/eligibility browser flows still use the real local backend.

Install the browser once, then run the end-to-end tests:

```powershell
npm.cmd --prefix frontend exec -- playwright install chromium
npm.cmd --prefix frontend run test:e2e
```

End-to-end tests start both servers automatically and seed the existing curated
records into a **temporary SQLite database**, never the local application database.
The test server fixes eligibility evaluation at **2026-11-12** so the recorded
source snapshot's outcomes do not drift as real deadlines pass; production still
uses its UTC clock. Tests exercise the real React → Vite → FastAPI flow, discovery,
filters, details, profile submission, conservative eligibility, matching groups,
empty/404/error recovery, refresh privacy, keyboard use and mobile overflow. The
original three connection tests remain intact. Stop manually running servers on
ports 8000 and 5173 first. Test servers stop after the run. The first browser
installation requires internet access.

Frontend Vitest tests cover the existing health check, complete runtime-validated
API contracts, profile validation, supported filters, detail/eligibility journeys,
all three verdicts, matching, privacy and failure recovery. All mock programme
records are explicitly fictional and restricted to test files. TypeScript is
checked by `npm.cmd --prefix frontend run build` before bundling.

The browser-test Python wrapper is also checked with Ruff:

```powershell
.\.venv\Scripts\python.exe -m ruff check backend frontend/e2e/start_test_api.py
.\.venv\Scripts\python.exe -m ruff format --check backend frontend/e2e/start_test_api.py
```

For a local build preview while the backend is running:

```powershell
npm.cmd --prefix frontend run preview
```

Open **http://127.0.0.1:4173**. This preview also proxies `/api` locally; it is
not a production server.

## Repository layout

```text
backend/app/             FastAPI application and response models
backend/tests/           pytest API tests
backend/tests/fixtures/  Explicitly fictional demo data for tests only
backend/data/            Reviewed source JSON and provenance; local ignored database
frontend/src/            React UI, API client, and component tests
frontend/e2e/            Playwright integration tests
PROPOSAL.md              Academic proposal
pyproject.toml           pytest and Ruff configuration
```

Local `.vscode/`, `.venv/`, SQLite files, dependencies, build output, and test artifacts are
ignored by Git. Frontend dependency versions are recorded in `package-lock.json`;
Python direct dependencies are pinned in the backend requirements files.

The frontend pins a `minimatch` override to 11.0.1 because the current lint tools
request versions affected by [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249).
Linting and builds are checked with this override; remove it when upstream
dependencies adopt a patched version.
