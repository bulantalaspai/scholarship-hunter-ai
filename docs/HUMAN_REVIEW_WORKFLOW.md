# Local scholarship review and publication

The dashboard uses the existing collection staging database. A reviewer can
compare a draft with its stored official-source excerpts, record field-level
decisions, and separately approve and publish a catalogue record. The seven
Phase 8C drafts start pending review. The active catalogue contains 22 records.

## Start a private session on Windows

From the repository root, start the API in a PowerShell window. If a local API
already uses port 8000, stop that instance before enabling review. Set
`SCHOLARSHIP_DATABASE_PATH` before startup if your intended catalogue uses a
different SQLite file. The review queue and catalogue must be separate files.

```powershell
$env:SCHOLARSHIP_REVIEW_STAGE = (Resolve-Path '.local-run/collection/phase-08c/review.sqlite3').Path
$env:SCHOLARSHIP_REVIEW_TOKEN = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))").Trim()
$env:SCHOLARSHIP_REVIEW_TOKEN
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

In another PowerShell window, run `npm.cmd --prefix frontend run dev` if the
frontend is stopped. Open `http://127.0.0.1:5173/#/review` and enter the key
shown in the private API terminal. Keep the key out of Git, logs, and messages.
The default permitted browser origins are `http://127.0.0.1:5173` and
`http://localhost:5173`. For another local port, set
`SCHOLARSHIP_REVIEW_ORIGINS` to the exact HTTP loopback origin or a comma-separated
list of exact origins. Keep the frontend proxy same-origin and forwarding the
browser Host header. Keep both services bound to loopback.

The pilot queue is a local artifact. If it is absent, recover the stored queue
or follow the manual replay instructions in [Extraction Quality](EXTRACTION_QUALITY.md).
The public catalogue uses a separate SQLite file. On a fresh checkout, install
the project dependencies and import `backend/data/curated_scholarships.json`
using the [SQLite setup commands](../README.md#database-initialization-and-import).
The public catalogue import supplies the 22 curated records. The review queue
comes from the separately staged manual excerpts.
The optional Phase 8C funding artifact displays the historical and current
McCall MacBain amounts with their periods and source context. The disputed
stipend stays blocked when that artifact is absent.

## Review the evidence

1. Select a draft. Compare its extracted fields with the stored excerpts,
   source URL, and retrieval date. Read the official source in your browser
   to confirm the scope and award cycle. Existing source-access policies still
   apply to any collection work.
2. For each field, choose **Accept**, **Reject**, or **Mark unresolved**. An
   acceptance requires a supported value and exact quotation from the staged
   source. Use a complete relevant excerpt of up to 400 characters per span.
   Confirm the quotation describes the same programme, field, and
   intake. For minimum scores, distinguish an explicit threshold from an
   example or alternative. For funding, retain currency, amount, payment
   period, and academic-term qualifiers when present.
3. Enter your reviewer name and rationale on each action. The service stamps
   the decision in UTC and retains earlier field decisions alongside the
   current one. Use **Request more evidence** when the draft cannot be approved.
   If new official evidence is required, stage a fresh manual excerpt in the
   same queue and link its context in your rationale. Do not edit the existing
   evidence or SQLite audit history directly.
4. Resolve core fields before selecting **Approve draft**. Approval requires
   accepted programme name, provider, destination, and degree level with
   supporting evidence. Optional fields without accepted evidence are omitted
   from the catalogue record. Unknown funding stays unknown. Conflicting values
   cannot be accepted through the dashboard. Inspect the resulting record and
   acknowledge the separate approval confirmation.
5. Select **Publish record** only after checking the approved record.
   Publication requires its own confirmation, identity, and rationale. It
   revalidates the approved snapshot, evidence, source, and duplicate identity
   against the active catalogue. Repeating a completed publication returns its
   original record ID. A failed check leaves the existing catalogue unchanged.

## Access and audit boundaries

- Review endpoints are disabled by default. They require a loopback request,
  trusted local Host and browser origin when supplied, and a bearer key.
  The dashboard keeps the key in page memory. Locking or reloading clears it.
- The key authenticates a local operator session. Names are self-attested and
  the SQLite audit is append-only through the application. Anyone with direct
  write access to the database can bypass those controls. Use this workflow on
  a trusted workstation with restricted access to the queue and catalogue.
- Use the shown loopback binding and disable proxy-header trust. Keep this route
  off public hosts and reverse proxies. The review API rejects `Forwarded`,
  `X-Forwarded-*`, and `X-Real-IP`, including when a server has already used
  them to rewrite the client address. A relay that deliberately strips those
  headers is indistinguishable from a local client. To revoke access, stop the
  review API, clear both `SCHOLARSHIP_REVIEW_*` settings for the queue and key,
  and restart normally. Generate a fresh key for each review session.

## Local verification

Stop the development servers before running Chromium tests. Playwright starts
its own API and frontend on the local development ports.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -W error
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run test:e2e
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

Automated approval and publication checks use synthetic drafts and temporary
SQLite databases. Human decisions for the seven pilot drafts remain pending.
