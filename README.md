# Scholarship Hunter AI

A course project for students from Kazakhstan seeking fully funded master's
scholarships abroad. See [PROPOSAL.md](PROPOSAL.md) for the planned application.

## Current scope: Phase 2

The React/TypeScript connection-check page and original health endpoint are
preserved. The FastAPI/Pydantic v2 backend now provides a local SQLite scholarship
catalogue through SQLAlchemy 2.0, an explicit curated-JSON importer, and read-only
search/detail endpoints. The initial dataset contains two real, officially
verified programme records; it is not a list of guaranteed or currently open
opportunities.

AI agents, Ollama/Qwen, eligibility matching, applicant profiles, and a catalogue
frontend remain future work. No database server, paid API, cloud account,
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
official source URL, and verification date. No write endpoints are exposed.
The health endpoint retains its original JSON contract.

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
