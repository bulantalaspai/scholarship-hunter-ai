# Scholarship collection and review

Phase 8A adds a local operator workflow for gathering official evidence, drafting
structured fields with Qwen, and reviewing candidates before publication.
The [source quality report](SCHOLARSHIP_SOURCE_QUALITY.md) records the catalogue
audit and measured pilot outcomes.

## Existing catalogue

The 22 scholarship records came from manual official-source research. The first
two were recorded on 2026-11-11 and 20 more on 2026-11-12. The team kept reviewed
facts in `backend/data/curated_scholarships.json`, with programme links and
evidence gaps in `SOURCES.md` and `catalogue_evidence.json`. The existing
`backend.app.import_catalogue` command imports curated JSON into SQLite,
preserving identity and preventing stale imports from replacing newer records.
[Catalogue provenance](../backend/data/SOURCES.md)

The application reads the active catalogue and uses a separate structured-rules
table for deterministic eligibility. The agent's existing official-page tool
fetches short excerpts for explanation. The collection CLI owns its own policy
registry and staging database. A pending extraction remains outside the API and
eligibility engine.

## Source policy

The [registry](../backend/collection/sources.json) records exact HTTPS entry
URLs, the organization and host, last catalogue verification date, permitted
method, terms and robots review status, evidence, review date, minimum request
interval, and notes. All 22 programme entries are manual-only because current
permission for automated collection has yet to be established.

To enable a reviewed source, check the publisher's terms and robots rules for
the exact path, collection user agent and request frequency. Record both decisions
and their evidence in the registry with the review date. The collector also
requires the exact URL to pass the official transport allowlist. Keep ambiguous
or disallowed sources manual-only and use an operator-supplied official excerpt
or an authorized provider API. Phase 8A implements manual entry and bounded HTTPS.

Each live invocation can fetch one approved page. The transport validates DNS
answers, connects to a pinned public address with HTTPS certificate validation,
blocks every redirect in collector mode, and rejects unsupported content and
common access barriers. Limits are six seconds total, 64 KiB on the body and
1,000 characters on the extracted excerpt. Common access-barrier detection can
miss provider-specific login or paywall screens. The reviewer checks the original
source before treating the excerpt as evidence.

Rate limits apply across each exact host and persist across invocations. The
default minimum interval is 60 seconds. An attempted request is reserved before
connection. Server refusals, timeouts, redirects and other fetch errors suspend
the host. The collector makes no automatic retries. The ignored
`.local-run/collector_access.sqlite3` records URL, UTC time, outcome and excerpt
hash. With collection stopped, an operator can inspect the failed request and
resolve the issue, including any provider retry interval, before clearing that
host's suspension flag in `collection_access`. Retain `next_allowed` and the
request history. Keep the host suspended when permission or the retry interval
remains unclear.

## Run and review

Use the existing repository virtual environment and installed
`qwen3:4b-instruct` served by local Ollama. Run commands from the repository root.
The dry run shows a plan without contacting a provider or the model or creating a
staging database. The six pilot excerpts come from the frozen official-source
manifest and retain their original retrieval dates.

```powershell
\.venv\Scripts\python.exe -m backend.collection pilot --dry-run
\.venv\Scripts\python.exe -m backend.collection pilot
\.venv\Scripts\python.exe -m backend.collection list
\.venv\Scripts\python.exe -m backend.collection inspect DRAFT_ID
```

For a new review, supply a small UTF-8 excerpt of the public programme source
with its actual retrieval date. Keep private information out of local inputs.
The manual path accepts up to 2,400 UTF-8 bytes. Add `--compare-db` with an
existing SQLite catalogue path to compare with its current records. The default
comparison uses the tracked curated catalogue.

```powershell
\.venv\Scripts\python.exe -m backend.collection collect 'REGISTERED_URL' --manual-text .local-run/source.txt --retrieved-on YYYY-MM-DD
```

Qwen receives the excerpt as untrusted data in one bounded local request with
tool access disabled. It returns structured fields with verbatim spans and
programme, admission, funding or unclear scope. Local schema validation rejects
malformed results. Unsupported spans become null and their field names are
logged. The draft retains the exact source URL, retrieval date, excerpt and
SHA-256. Any confidence value comes from the model. A human checks that the
words actually support the field and scope, including qualifications and
exceptions. Even an exact quote can be assigned to the wrong field.

The queue starts drafts in `pending_review`. A reviewer inspects the source,
identifies the award and cycle, checks dates and scope, and records
`needs_more_evidence`, `rejected` or `approved` with an operator identifier
and rationale. The inspector shows potential catalogue matches, related staged
drafts, comparable discrepancies, wording differences and parseable expired
deadlines. Review date and decision history are recorded in SQLite.

Approval uses a reviewer-written single `CatalogueRecord` JSON with the same
official URL and a current documented verification date. Supply a JSON mapping
from each populated record field to one or more exact spans in the staged
excerpt. The map excludes `official_source_url`, `last_verified_at`,
`eligibility_rules`, null fields and unknown funding. Keep unsupported fields
null and confirm that each span supports the reviewed value. Approval requires
original manual or permitted live evidence. Archived pilot fixtures cannot be
published. Structured eligibility policies use the existing dedicated rules
review workflow.

```powershell
\.venv\Scripts\python.exe -m backend.collection decide DRAFT_ID needs_more_evidence --reviewer REVIEWER --rationale 'Confirm current award and scope.'
\.venv\Scripts\python.exe -m backend.collection decide DRAFT_ID approved --reviewer REVIEWER --rationale 'Reviewed current official terms.' --record .local-run/reviewed-record.json --evidence .local-run/reviewed-evidence.json
\.venv\Scripts\python.exe -m backend.collection publish DRAFT_ID --catalogue-db PATH_TO_INITIALIZED_LOCAL_DB
```

Publication is explicit and insert-only. It rechecks the target catalogue for
duplicates and inserts the new record and a local receipt in one SQLite
transaction with rollback journaling. An identical publication retry returns
the existing ID. Potential overlaps involving the same programme, current or
prior calls, or alternate awards require separate reconciliation. This workflow
does not refresh existing records or export local approvals into the tracked
seed. The staging database and audit logs stay under ignored local paths.
