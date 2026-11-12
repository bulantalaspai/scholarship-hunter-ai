# Scholarship Hunter AI

A course project for students from Kazakhstan seeking fully funded master's
scholarships abroad. See [PROPOSAL.md](PROPOSAL.md) for the planned application.

## Current scope: Phase 3

The React/TypeScript connection-check page and original health endpoint are
preserved. The FastAPI/Pydantic v2 backend now provides a local SQLite scholarship
catalogue through SQLAlchemy 2.0, an explicit curated-JSON importer, and read-only
search/detail endpoints. Phase 3 adds stateless, deterministic eligibility
checks and grouped profile matching. The initial dataset contains two real, officially
verified programme records; it is not a list of guaranteed or currently open
opportunities.

AI agents, Ollama/Qwen, stored applicant accounts, and a catalogue frontend
remain future work. No database server, paid API, cloud account,
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
into executable conditions. The two current real records have no complete
structured review and therefore cannot receive an overall `eligible` result
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

Install the browser once, then run the end-to-end tests:

```powershell
npm.cmd --prefix frontend exec -- playwright install chromium
npm.cmd --prefix frontend run test:e2e
```

End-to-end tests start both servers automatically, verify the real React → Vite
proxy → FastAPI connection, and check the mobile layout. Stop manually running
servers on ports 8000 and 5173 first. Test servers are stopped when the tests
finish. The first browser installation requires internet access.

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
