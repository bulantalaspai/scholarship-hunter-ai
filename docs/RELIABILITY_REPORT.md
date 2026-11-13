# AI agent retrieval and reliability

## Scope and reproducibility

Phase 6C uses the frozen Phase 6B population of 20 synthetic student profiles,
60 named-programme eligibility cases and 12 source-excerpt extraction examples.
All runs use the same 22-record catalogue and assessment date of **2026-11-12**.
The live experiments ran on **2026-11-13** with local Ollama and
`qwen3:4b-instruct`. No annotation values or catalogue requirements were changed.

The historical native-process trial supplies the complete before comparison.
A fresh before-edit reproduction repeated all 20 general recommendation requests
and three diagnostic case requests against merged main `6323ce1`. It reproduced
3/20 raw responses and 12/20 responses with the existing fallback. The fresh
trial's three case requests are a diagnostic subset. The final after trial
executes the complete 20/60/12 protocol.

Experiment JSON records input and implementation hashes, model digest and options,
per-round prompt sizes, actual dispatch outcomes, selections and elapsed service
times. Implementation hashes identify the tested working files above the recorded
base commit. The comparator verifies identical inputs, assessment date and request
populations. A fresh rerun uses a new output path. Earlier experiment files remain
available. [Phase 6B report](EVALUATION_REPORT.md),
[fresh reproduction](../evaluation/results/reliability_before_2026-11-13.json),
[after experiment](../evaluation/results/reliability_after_2026-11-13.json),
[comparison](../evaluation/results/reliability_comparison_2026-11-13.json)

## Reproduced root causes

1. **Search filters excluded named targets.** In fresh `P01-MEXT-CLOSED`, Qwen
   applied Japan, Computer Science and full-funding filters. The target has an
   unknown field list and was excluded. Qwen checked IMLEX ID 7 and returned a
   different programme. In `P01-DAAD-FUNDING`, a full-funding filter excluded the
   requested partial award. The full historical trial assessed zero of the 30
   source-checked negative targets.
2. **Serial checks consumed the model budget.** The fresh DAAD diagnostic searched
   once and separately checked IDs 6, 9 and 11. Four rounds elapsed without a
   final selection. Ten of the 20 general requests stopped at a budget limit.
3. **Fallback depended on model discovery.** It could recover only IDs returned
   by model-requested searches. Incorrect filtering therefore reduced both raw
   model and assisted coverage. A valid partial selection could also omit other
   deterministic candidates from the public response.
4. **Selection validation exposed missing tool work.** Earlier recorded replies
   selected searched IDs without checking/ranking them. Grounding rejection
   correctly withheld those selections. The previous report contains that trace.
5. **Context and evidence have separate effects.** Historical real prompts reached
   1,452 reported tokens with zero context-budget stops. Missing reviewed policies
   still prevent complete eligibility conclusions across the catalogue. Retrieving
   a page cannot establish unreviewed rules. The observed filter and round-budget
   failures have direct tool-trace evidence.

## Changes

- The existing deterministic matching service discovers candidates before model
  inference. General requests retain the complete pool without confirmed failures,
  together with the first three ranked assessments. Full-name target matching uses
  Unicode normalization and word boundaries and retains confirmed negative targets.
- Qwen receives up to three discovered IDs and their official URLs. It chooses
  tools and arguments from this context and live results. Compact instructions
  encourage batch ranking and reserve a final response round. Individual checks,
  searches and approved page fetching remain available.
- Bootstrap assessments never populate the model-tool assessment cache. Final raw
  selections require genuinely checked/ranked IDs. Explicit named-target requests
  also reject substitution of other programmes. Public `discovery_candidates`
  persist alongside partial or empty model selections.
- Qwen can select actual requirement keys for explanations. The server validates
  the references and renders the engine's original requirement results. All
  classifications, explanations, official URLs and verification dates come from
  the existing services.
- Handled inference outages, timeouts, invalid responses and busy requests return
  HTTP 200 with `status` equal to `model_error`, an explicit error category and
  cached discovery. Invalid requests retain HTTP 422. Confirmed failures remain
  ineligible. The separate fallback list contains only `needs_verification`.
- The frontend validates the additional contract, preserves canonical candidates,
  shows model-selected explanation points and displays each record once. Browser
  tests exercise recovery and a real catalogue deadline failure.

Resource limits remain four model rounds, eight attempted tool calls, a 90-second
overall deadline, 45 seconds per inference call, a 4,096-token context, 384 output
tokens and the 3,300-token conservative input estimate. Tool results remain bounded
to 3,200 UTF-8 bytes and page text to 600 characters. Official-page URL, DNS, IP,
redirect, TLS, timeout and body-size checks retain their existing behavior.

## Measured comparison

### General recommendation requests

Each column uses the same 20 profiles. All returned general-request candidates
retain `needs_verification`. The past-intake profile P20 has confirmed failures
and produces no viable candidates.

| Measure | Phase 6B | Fresh before edit | Phase 6C |
| --- | ---: | ---: | ---: |
| Deterministic baseline coverage | 19/20, 95% | 19/20, 95% | 19/20, 95% |
| Raw model candidate coverage | 3/20, 15% | 3/20, 15% | 19/20, 95% |
| Model plus deterministic assistance | 12/20, 60% | 12/20, 60% | 19/20, 95% |
| Raw model abstentions | 17/20, 85% | 17/20, 85% | 1/20, 5% |
| Model budget stops | 10/20 | 10/20 | 0/20 |
| Model transport/protocol failures | 0/20 | 0/20 | 0/20 |
| Successful attempted tool calls | 68/69, 98.55% | 68/69, 98.55% | 29/29, 100% |
| Mean service latency | 3.514 s | 4.431 s | 4.471 s |
| Median service latency | 3.127 s | 3.738 s | 4.250 s |
| P95 service latency | 6.390 s | 7.013 s | 5.742 s |
| Mean model rounds | 4.00 | 4.00 | 2.45 |
| Responses with model-selected explanation points | Feature absent | Feature absent | 19/20 |

A successful tool attempt includes a validated empty search result. The final
baseline mean latency is 0.003321 seconds. Adding Qwen has a substantial inference
cost. The observed mean model latency exceeds both before trials.

Canonical discovery retained **57/57 baseline top-three occurrences** and
**335/335 viable candidate-pool occurrences** across profiles. These are repeated
profile/programme pairs drawn from 22 programmes. This engineering retention recall
is 100%. Relevant or truly eligible candidate recall remains **NOT EVALUABLE**.
Assisted top-three retention increased from 28/57 to 57/57. Before trials did not
expose a complete discovery-pool ID list, so their full-pool retention is unmeasured.

Three of 20 responses needed canonical candidates omitted from a valid partial
model selection. No general request needed the separate fallback list. Before-edit
fallback supplied nine responses with otherwise empty model selections. The
persistent discovery list therefore has a distinct role even when raw response
coverage equals assisted coverage.

### Named-target audits and classification preservation

| Measure | Phase 6B model tools | Phase 6C model tools | Phase 6C canonical discovery |
| --- | ---: | ---: | ---: |
| Requested target assessed | 8/60, 13.33% | 26/60, 43.33% | 60/60, 100% |
| Source-checked negative target assessed | 0/30 | 11/30 | 30/30 |
| Negative-label agreement among assessed targets | NOT EVALUABLE | 11/11 | 30/30 |
| Provisional expectation agreement | 8/20 | 15/20 | 20/20 |
| Named-target raw selections returned | 15/60 | 14/60 | Separate deterministic assessments |
| Budget stops | 9/60 | 30/60 | Cached results retained |
| Successful attempted tool calls | 182/189, 96.30% | 118/127, 92.91% | Discovery has separate attribution |
| Mean case service latency | 3.504 s | 4.531 s | Included in response latency |

The historical 15 raw case responses can contain substitute programmes. The new
scope validator rejects such substitutions. Fourteen final raw case selections
contain the requested target. Model tools assessed twelve ineligible targets,
including eleven source-checked negatives and one provisional past-intake case.
Their presence in the assessment cache supplies separate evidence from a final
model selection.

The final case trial recorded **29 schema-invalid rounds**, **25 outside-target
selection rounds** and **nine blocked checks of undiscovered IDs**. It had zero
unassessed-ID selection rounds, zero invalid-explanation-reference rounds and zero
transport/protocol failures. Thirty requests reached the model budget. These
remaining failures limit model-directed named-target assessment despite canonical
recovery. Historical observers lacked the two new rejection categories, so those
historical counters cannot establish an absence of scope or explanation failures.
Raw model prose is discarded, which limits diagnosis within the schema-error group.

All 68 emitted raw assessments and 117 emitted canonical assessments across general
and named-case responses matched their deterministic baseline statuses when joined
by profile ID and scholarship ID. This checks classification preservation. The
case labels are AI-authored draft annotations, so the agreement figures provide
no independent gold-standard accuracy claim. Canonical case results comprise
31 ineligible and 29 needs-verification verdicts. Ten DAAD cases have unresolved
expected labels and remain excluded from label-agreement scoring.

Across all 80 agent requests, the model executed **156 actual tool attempts**,
with **147 successful** and **nine blocked**. It chose 64 searches, 50 rankings and
42 checks. It requested no page fetches in this final trial. All four tools remain
covered by dispatch and security regression tests. Maximum reported prompt size was
1,448 tokens, maximum input estimate was 3,105 and context-budget stops were zero.

### Extraction and source support

The twelve real extraction probes again produced 34 true positives, ten false
positives and three false negatives. Preliminary precision is **77.27%**, recall
**91.89%** and F1 **83.95%**, matching the historical run. No extraction change is
included in this phase. Independent human review of the short-excerpt annotations
is pending.

| Emitted general-request claim scope | Linked | Supported in draft audit | Unsupported in draft audit | Unresolved |
| --- | ---: | ---: | ---: | ---: |
| Raw model programme names and funding labels | 108/108 | 100 | 0 | 8 |
| Canonical programme names and funding labels | 114/114 | 104 | 0 | 10 |

Link presence is 100% within this scope. Support auditing covers 92.59% of raw
claims and 91.23% of canonical claims. Complete requirement explanations,
student-specific conclusions and the remaining source pairs require review.
Overall unsupported-factual-claim rate remains **NOT EVALUABLE**. The zero counts
above apply only to the audited name/funding occurrences.

## Trace examples and error analysis

The complete experiment file contains every model round and attempted tool.
The following examples come from the final recorded trial.

- **P01 general request** chose `rank_scholarships([2, 3, 4])`, followed by
  `check_eligibility(2)` and `check_eligibility(3)`. All three dispatches succeeded.
  Its final selection retained the three needs-verification records and selected
  canonical requirement keys for explanations.
- **P02-MEXT-CLOSED** searched Japan/Artificial Intelligence/full funding, then
  successfully checked pre-discovered target ID 20. The assessment retained the
  failed deadline and unresolved admission requirements. The model later reached
  its final-response budget. Canonical discovery still returned the requested
  ineligible target with its official embassy URL and verification date.
- **P01-DAAD-FUNDING** searched Germany/Computer Science and ranked IDs 6, 9 and 11.
  It tried selecting those substitutes in two final rounds. Both received
  `outside_named_target`. The raw selection stayed empty, while canonical target
  ID 1 retained `ineligible` and its failed funding-preference condition.

An additional real HTTP smoke request used a separate current-date synthetic
profile and disposable SQLite database. It returned **HTTP 200**,
`needs_verification`, selected IDs **2, 3 and 4**, and took **6.84 seconds** including
HTTP/application handling. Qwen chose an empty EU-filter search and then ranked
the pre-discovered IDs. It demonstrates recovery without requiring a successful
model search. This smoke request is excluded from benchmark denominators.
[HTTP smoke response and trace](../evaluation/results/reliability_http_smoke_2026-11-13.json)

## Annotation review and proposal targets

The frozen `verified_gold` label denotes AI-authored, source-checked negative
annotations awaiting human adjudication. Source-checked negative agreement and
provisional expectation agreement have separate denominators. Canonical discovery
receives separate attribution from actual model-requested assessments.

The review package contains seven items for **Talaspay Bulan**, **Sayat Nuradil**
and **Tursbekov Darkhan**, covering closed calls, funding preference, missing
admission evidence, unsupported extraction booleans, payment-period semantics,
relevance and citation support. It contains **zero completed human reviews**.
Each item includes evidence references and an empty reviewer/date/decision/rationale
template. [Human-review package](../evaluation/review/README.md)

| Proposal metric | Target | Decision and missing evidence |
| --- | --- | --- |
| Three-class eligibility accuracy | At least 90% | **NOT EVALUABLE**. Independent human review and positive eligible examples are pending. |
| Requirement extraction F1 | At least 85% | **NOT EVALUABLE** as an independently validated application target. The short-excerpt probe uses provisional AI annotations. |
| Precision@3 | At least 80% | **NOT EVALUABLE**. No profile has three independently verified eligible/relevant positive labels. |
| Complete factual citation support | 100% | **NOT EVALUABLE**. Name/funding link presence and limited support audits cover a subset of emitted claims. |

## Executed checks

| Check | Executed result |
| --- | --- |
| Backend pytest, warnings treated as errors | 505 passed |
| Frontend component/integration tests | 159 passed across six files |
| Chromium browser suite | 19 passed, exit 0 |
| Ruff lint and format check | Passed across 46 Python files |
| ESLint | Passed with zero permitted warnings |
| TypeScript and Vite production build | Passed |
| Python dependency consistency | No broken requirements |
| npm dependency tree | Passed |
| npm security audit | Zero reported vulnerabilities |
| Changed-file secret patterns and whitespace | Passed |

Initial development checks exposed assertions tied to the previous fallback/error
contract, a context-size regression in the four-tool injection scenario and an
incomplete grounding label in the evaluation observer. Regression tests cover the
corrected behavior. Windows denied access to an existing pytest temporary folder.
Final backend runs used a fresh temporary directory and completed with exit 0.
The observer now distinguishes unassessed IDs, named-target substitutions and
invalid explanation references without querying SQLite or changing tool caches.

Mocked unit/component/browser model replies support deterministic regression
testing. The recorded experiment uses the installed real local model. Browser
catalogue and eligibility journeys use a temporary SQLite database with the real
backend. Application profile data remains in local request memory.

## Reproduction

Run from the repository root with the existing environment and local Ollama.

```powershell
.\.venv\Scripts\python.exe -m backend.evaluation.run --real-model --output "$env:TEMP\scholarship-reliability.json"
.\.venv\Scripts\python.exe -m backend.evaluation.reliability --before evaluation/results/native_2026-11-12.json --after "$env:TEMP\scholarship-reliability.json" --fresh-before evaluation/results/reliability_before_2026-11-13.json --output "$env:TEMP\scholarship-comparison.json"
```

The runner supports `--resume` only when the checkpoint's data, code, date and
model signatures match. Experiments seed disposable SQLite data and perform
sequential requests. Latencies measure database/tool work and local inference.
They exclude process startup, catalogue import, checkpoint writes and HTTP/UI
transport. P95 uses nearest rank. One observation per profile supports descriptive
comparison. Model warm-up, plan variation, live page changes and normal machine
load limit causal inference.

## Remaining limitations

- Model tools still miss **34/60 named targets**, including **19/30 source-checked
  negatives**. Half the named requests reach the budget. Strict validation and
  deterministic recovery preserve visible failure assessments.
- Complete reviewed eligibility policies are absent for all 22 programmes.
  Discovery retention measures preservation of the engine's uncertain candidate
  pool. Independently judged relevance and true eligible-candidate recall require
  additional evidence.
- Full-name target routing is deterministic. Abbreviations, misspellings,
  natural-language destinations and preferences rely on model search. Broad
  canonical discovery may include destinations outside those free-text wishes.
- The public discovery assessment list and model context expose the first three
  candidates. The full retained ID list supports auditing and the catalogue API
  supports further exploration.
- Qwen chooses explanation points from validated requirement keys. Factual wording
  is rendered by the deterministic engine. Independent source support for every
  displayed claim remains pending.
- Source fetches can fail the existing network and content guards. Such failures
  supply no new eligibility evidence. Resource limits can still cause abstention.
- All synthetic profiles and label families come from a small academic benchmark.
  Human-reviewed positive cases, broader sources and repeated randomized trials
  remain necessary for generalization claims.
