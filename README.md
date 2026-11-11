# Scholarship Hunter AI

A course project for students from Kazakhstan seeking fully funded master's
scholarships abroad. See [PROPOSAL.md](PROPOSAL.md) for the planned application.

## Phase 1 scope

This phase provides a React/TypeScript frontend, a FastAPI backend using Pydantic
v2, and a working connection check. Scholarship discovery, profiles, eligibility,
ranking, SQLite persistence, and Ollama/Qwen integration are future phases.
No AI model, database, credentials, or paid APIs are needed to run Phase 1.

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
equivalent `/api` reverse proxy. Production deployment is outside Phase 1.

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

Backend tests exercise the real ASGI application, JSON contract, and API
documentation. Frontend tests cover loading, valid and invalid responses,
network failures, retry, and request cancellation.

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
frontend/src/            React UI, API client, and component tests
frontend/e2e/            Playwright integration tests
PROPOSAL.md              Academic proposal
pyproject.toml           pytest and Ruff configuration
```

Local `.vscode/`, `.venv/`, dependencies, build output, and test artifacts are
ignored by Git. Frontend dependency versions are recorded in `package-lock.json`;
Python direct dependencies are pinned in the backend requirements files.

The frontend pins a `minimatch` override to 11.0.1 because the current lint tools
request versions affected by [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249).
Linting and builds are checked with this override; remove it when upstream
dependencies adopt a patched version.
