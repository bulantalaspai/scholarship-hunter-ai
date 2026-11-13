# Final retrieval and human evaluation

## Scope and interruption recovery

PR #8 was merged into main at `3e24562`. Phase 6D continues on
`feature/final-evaluation`. Before the usage interruption, the programme resolver,
alias registry, named-search scope handling, review package, validator, comparison
scripts and frontend lookup states were implemented. The 34 previous misses were
analyzed. The saved verification had reached 629 backend, 193 frontend and
20 browser tests, followed by additional review-provenance tests.

After resuming, the working changes and artifacts were inspected in place.
Concurrent catalogue-snapshot consistency and final-response repair feedback were
completed. The complete verification and real frozen benchmark were then executed.
The final result and commit contain the retained work and these completion steps.

## Methodology and sample sizes

The comparison uses the same 22 scholarship records, 20 synthetic profiles,
60 named-programme cases, 80 provisional relevance judgments and 12 official-source
extraction excerpts as Phase 6C. The assessment date stays **2026-11-12**. Source
records and frozen benchmark annotations retain their existing contents and dates.
The new alias registry has a separate implementation hash.

The three methods are the deterministic matching service, raw Qwen tool-directed
assessment/selection, and Qwen with retained deterministic candidates. General
coverage counts responses with candidates. Named-target recall uses the requested
programme identity, with tool-assessment recall and final-selection recall reported
individually. Canonical recovery has separate attribution. Confirmed failures
remain ineligible and unknown evidence remains needs-verification.

Real runs use the installed local `qwen3:4b-instruct` through Ollama. Limits stay
four model steps, eight attempted tool calls, a 4,096-token context, 384 output
tokens, 90 seconds overall and 45 seconds per model call. The conservative input
estimate stays capped at 3,300 tokens. Source-fetch security controls retain their
existing behavior. Mocked tests provide deterministic regression coverage.

Requests execute sequentially using temporary SQLite data. Timings include local
inference, tool work and discovery. Startup, catalogue import, checkpoint writing
and browser transport are excluded. P95 uses nearest rank. Experiment signatures
record normalized input/code hashes, alias configuration and the model digest.

## Investigation and implemented changes

All **34 missed targets** were already present in Phase 6C's deterministic
discovery. Their frozen prompts contained full canonical names. Name-normalization,
alias and abbreviation failures therefore have no measured contribution in those
34 cases. The new lookup behaviors receive dedicated regression tests.

The following observed conditions overlap across cases. They cannot be added to
form a partition of the failures.

| Observed condition among the 34 misses | Cases |
| --- | ---: |
| Search filters excluded the requested target | 34 |
| Recorded checks/rankings requested different IDs | 21 |
| Final selections violated the named-target scope | 17 |
| Structured final replies failed schema validation | 4 |
| Model budget exhausted | 18 |

The per-case analysis preserves actual searches, requested IDs, validation
outcomes and missing-target status. Blocked attempts whose IDs were omitted by
the earlier trace cannot identify the attempted ID. Raw invalid model prose was
discarded. [Phase 6C miss analysis](../evaluation/analysis/phase_6c_misses.json)

Two real before-edit diagnostics reproduced a DAAD substitution and a MEXT
schema failure. The MEXT reply exceeded four explanation keys twice. Schema
feedback now reports structural errors and safe server-defined relationship
messages, lists the permitted fields and retains the existing limits. The model
still chooses its tools, IDs and explanation keys. [Before-edit diagnostics](../evaluation/results/final_diagnostic_before_2026-11-13.json)

Programme lookup now supports Unicode NFKC/case normalization, source-bound local
aliases and conservative spelling matches for explicit long names. Shared aliases
offer programme choices. Unknown names and unsupported route qualifiers receive
clear no-match responses. Short acronym typos remain unresolved. Spelling matches
state their interpretation. [Alias inventory and matching thresholds](PROGRAMME_ALIASES.md)

Named searches retain the requested programme despite optional country, field or
funding filters and report the ignored filters explicitly. Existing eligibility
checks assess funding preferences and confirmed disqualifications. An explicit
user target can disambiguate a broader model alias. Another programme cannot
replace that target. Ambiguous and unknown goal names use zero model/tool steps.

Discovery compares the ID sets, names, source URLs and verification dates in its
ranked assessments and catalogue records. A mismatch produces a retry response.
Validated records are reused when seeding tool discovery.

## Measured retrieval and reliability

### Development regression and repair

The first complete Phase 6D development run reached 60/60 named-target tool
assessments. General raw coverage fell to 16/20, with two context-guard stops.
Its traces show the model supplying degree and subject strings through the new
`programme_name` argument during broad discovery. This produced unsuccessful name
lookups and extra calls despite the retained deterministic candidates.

The correction offers the programme-name argument only for resolved programme
requests, reuses the previous general-search instructions and serializes tool
messages compactly. Four tool names remain available and the model chooses the
calls. Resource limits retain their existing values. The initial observations and
their development-source hashes are retained. Current reproduction commands use
the final tested implementation. [Initial development run](../evaluation/results/final_initial_2026-11-13.json),
[initial comparison](../evaluation/results/final_initial_comparison_2026-11-13.json)

### Final frozen comparison

The final run completed 20 baseline requests, 20 real general agent requests,
60 real named-target audits and 12 real extraction probes on 2026-11-13.
Ollama reported version **0.40.16** with model digest
`0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
The final code/configuration hashes match the recorded implementation.
[Complete compact benchmark](../evaluation/results/final_2026-11-13.json),
[final comparison](../evaluation/results/final_comparison_2026-11-13.json)

| General requests, n=20 | Phase 6C | Final Phase 6D |
| --- | ---: | ---: |
| Deterministic baseline coverage | 19/20, 95% | 19/20, 95% |
| Raw Qwen candidate coverage | 19/20, 95% | 19/20, 95% |
| Qwen with deterministic assistance | 19/20, 95% | 19/20, 95% |
| Raw abstentions | 1/20 | 1/20 |
| Budget stops | 0/20 | 0/20 |
| Transport/protocol failures | 0/20 | 0/20 |
| Successful tool attempts | 29/29 | 30/30 |
| Mean agent service latency | 4.471 s | 3.757 s |
| Median agent service latency | 4.250 s | 3.144 s |
| P95 agent service latency | 5.742 s | 5.929 s |
| Mean model rounds | 2.45 | 2.50 |

General candidates all retain needs-verification. The past-intake profile P20 has
no viable candidates. The final deterministic baseline mean is 0.001753 seconds.
Mean agent latency decreased in this run, while its general-request P95 increased.
Single-trial timings support descriptive comparison.

| Named-target requests, n=60 | Phase 6C | Final Phase 6D |
| --- | ---: | ---: |
| Baseline target assessments | 60/60 | 60/60 |
| Target assessed through model-requested tools | 26/60, 43.33% | 60/60, 100% |
| Target in validated raw final selection | 14/60, 23.33% | 53/60, 88.33% |
| Target in assisted response | 60/60, 100% | 60/60, 100% |
| Model budget stops | 30/60 | 6/60 |
| Raw final abstentions | 46/60 | 7/60 |
| Successful tool attempts | 118/127, 92.91% | 128/128, 100% |
| Mean agent service latency | 4.531 s | 3.677 s |
| Median agent service latency | 4.450 s | 3.761 s |
| P95 agent service latency | 8.204 s | 4.205 s |

All 34 previously missed target assessments were recovered in the final trial.
This measures named catalogue retrieval and assessment completion. It supplies no
independent evidence that the programmes are eligible or relevant. All thirty
source-checked negative targets were assessed through actual model-requested tools.
Their labels remain provisional until human review.

The raw named selections include **24 ineligible assessments** and **29
needs-verification assessments**. These are responses to explicit assessment
requests. Seven ineligible targets remain absent from raw final selections, with
six budget stops and one empty selection. Canonical discovery preserves their
negative assessments, explanations, official URLs and verification dates.

Canonical discovery retains **57/57 baseline top-three occurrences** and
**335/335 viable profile/programme occurrences**. These are repeated pairs from
22 programmes. Two general responses need candidates omitted from a partial model
selection, compared with three previously. The explicit needs-verification fallback
list is unused in the final trial. Seven named responses need canonical negative
assessments absent from raw selections. Classification-preserving canonical
recovery and the separate unresolved-only fallback have different scopes.

All **108 emitted raw assessments** and **117 canonical assessments** across
general and named requests matched deterministic baseline classifications when
joined by profile ID and scholarship ID. This is an engineering integrity check.
Human-label eligibility accuracy remains NOT EVALUABLE.

### Tool behavior, schema failures and sources

The final model executed **158 actual tool calls**, all successful under the
validated-dispatch definition. It chose 50 searches, 59 eligibility checks and
49 rankings. It chose zero official-page fetches. All four tools retain mocked
regression/security coverage. A successful attempt can return a validated empty
search result.

The final named audits recorded **48 schema-invalid model rounds**. Error
occurrences include 19 excessive requirement lists, 13 forbidden extra fields,
eleven JSON syntax failures and eight explanation/selected-ID relationship
violations. Some replies contain multiple issues, so these counts exceed the
round count. The final trial has zero outside-target, unassessed-ID or invalid-key
selection rounds. Two general schema failures were repaired within the existing
budget. Zero context-guard stops occurred. The maximum reported prompt was
1,458 tokens, with maximum conservative estimate 3,252.

For `P01-MEXT-CLOSED`, Qwen searched the named route with Japan and Computer Science,
then checked target ID 20. Its first final reply exceeded four explanation keys.
The next reply validated and retained the ineligible classification.
For `P01-DAAD-FUNDING`, Qwen ranked and checked target ID 1, then failed final
validation through an extra field and an explanation-ID relationship. Its raw
selection remained empty. Canonical recovery retained the funding-preference
failure. Full traces are in the benchmark artifact.

| General-request name/funding claim scope | Linked claims | Human-audited support |
| --- | ---: | --- |
| Deterministic baseline | 114/114 | NOT EVALUABLE |
| Raw Qwen selections | 110/110 | NOT EVALUABLE |
| Qwen with deterministic assistance | 114/114 | NOT EVALUABLE |

Reference presence is 100% within this scope. Zero claim/source pairs have
completed human reviews. Complete factual support and unsupported-factual-claim
rate remain NOT EVALUABLE, including requirement explanations and student-specific
conclusions.

The twelve real excerpt probes again measured **77.27% provisional precision**,
**91.89% recall** and **83.95% F1**, with 34 true positives, ten false positives and
three false negatives against AI-authored source annotations. These are diagnostic
excerpt scores. Independent human extraction precision/recall/F1 remain
NOT EVALUABLE.

## Independent annotation package

The package contains **284 AI-prepared provisional items** and **568 blank review
assignments**. Two independently assigned reviewers per item is the implemented
project protocol. It is a team-workflow choice. Source proposals and actual human
decision fields are distinct.

| Area | Items | Assigned decisions |
| --- | ---: | ---: |
| Eligibility | 60 | 120 |
| Extraction fields | 120 | 240 |
| Recommendation relevance | 80 | 160 |
| Citation support | 24 | 48 |

The ten allowed extraction slots across twelve excerpts include provisional
absence values. A completed human null annotation denotes confirmed absence within
that excerpt. An unresolved decision supplies no gold value. This distinction
allows false-positive scoring after the required independent reviews.

| Reviewer | Sheet | Assignments |
| --- | --- | ---: |
| Talaspay Bulan | [talaspay_bulan.csv](../evaluation/human_review/talaspay_bulan.csv) | 189 |
| Sayat Nuradil | [sayat_nuradil.csv](../evaluation/human_review/sayat_nuradil.csv) | 190 |
| Tursbekov Darkhan | [tursbekov_darkhan.csv](../evaluation/human_review/tursbekov_darkhan.csv) | 189 |

The [manifest](../evaluation/human_review/manifest.json) supplies complete synthetic
profiles, programme identities, proposed labels and assignments. The
[evidence registry](../evaluation/human_review/evidence.json) stores official
excerpts, URLs, source dates, provenance and evidence gaps. Three supplementary
official-page excerpts were checked during AI preparation on 2026-11-13. Those
preparation dates supply no human attestation. The inaccessible Hungary historical
call retains a clearly marked frozen paraphrase requiring human verification.

The validator checks provenance, assignments, typed values, dates and evidence
references. It detects disagreements and excludes pending, partial and unresolved
items from consensus. Citation reviews must identify the cited page. A different
page on the same host supplies no support for the original citation. Final scoring
revalidates the actual CSV files. Edited derived snapshots cannot supply labels.
The script cannot authenticate reviewer identity, independence or actual source
support. Those require the team's documented review. [Review instructions](../evaluation/human_review/README.md)

## Academic metrics and proposal targets

Validation of the actual sheets records **0 completed reviews**, **0 human-reviewed
items** and **284 pending items**. All 568 reviewer-decision fields remain blank.
AI-authored legacy `verified_gold` labels supply no human gold-standard credit.

| Academic measure | Current result | Missing independent evidence |
| --- | --- | --- |
| Eligibility Accuracy | **NOT EVALUABLE** | Human consensus on eligibility cases and representative class coverage |
| Extraction Precision, Recall and F1 | **NOT EVALUABLE** | Reviewed field values and confirmed absences across the excerpt slots |
| Recommendation Precision@3 | **NOT EVALUABLE** | Human relevance judgments with at least three independently verified eligible/relevant positives per scored profile |
| Factual citation support | **NOT EVALUABLE** | Human judgments on exact claim/value/cited-page relationships |

The proposal targets of at least 90% accuracy, 85% extraction F1, 80% Precision@3
and 100% factual citation coverage remain unestablished. Provisional excerpt scores
and reference presence describe their explicitly measured scopes. They supply no
claim that these academic targets have been achieved.

## Executed verification

| Check | Actual result after resuming |
| --- | --- |
| Backend pytest with warnings treated as errors | 651 passed |
| Frontend unit/component/API tests | 193 passed across six files |
| Chromium browser tests | 20 passed, exit 0 |
| Ruff lint and formatting | Passed across 53 Python files |
| ESLint | Passed with zero permitted warnings |
| TypeScript and Vite production build | Passed |
| Python dependency consistency | No broken requirements |
| npm dependency tree and security audit | Passed, zero reported vulnerabilities |
| Human-review validation | 284 pending items, zero completed reviews |

The regression suites use mocked model/network responses. Browser catalogue,
eligibility and ambiguity-option records come from the real local test API and
a disposable SQLite database. The frozen benchmark uses real local Ollama
inference. Initial pre-interruption diagnostics and corrected test expectations
remain documented in the work history. Final checks above completed successfully.

## Reproduction

Run from the repository root using the existing environment and installed local
model. Store a new benchmark checkpoint at a fresh path.

```powershell
.\.venv\Scripts\python.exe -m backend.evaluation.reviews validate --package evaluation/human_review
.\.venv\Scripts\python.exe -m backend.evaluation.run --real-model --output "$env:TEMP\scholarship-final-run.json"
.\.venv\Scripts\python.exe -m backend.evaluation.final --before evaluation/results/reliability_after_2026-11-13.json --after "$env:TEMP\scholarship-final-run.json" --review-package evaluation/human_review --output "$env:TEMP\scholarship-final-summary.json"
```

The benchmark runner supports `--resume` only for matching code, data, model and
date signatures. The final comparator checks frozen populations and input hashes,
then validates the reviewer sheets. The recorded benchmark is stored as compact
JSON to retain per-request traces while limiting artifact size.

## Threats to validity and remaining work

- The benchmark has twenty profiles and three repeatedly used named-target
  programme families. It cannot establish population-wide retrieval performance.
- General coverage and deterministic-pool retention measure system behavior.
  Independent eligibility and relevance claims require completed human evidence.
- Temperature zero still permits observed plan variation. Single sequential
  observations, model warm-up and normal machine load limit latency conclusions.
- Aliases are catalogue-derived lookup mappings. New programme routes and short
  acronym spelling errors require explicit curation or clarification.
- The catalogue lacks complete reviewed eligibility policies. Missing conditions
  stay unresolved. Admission and scholarship selection require separate evidence.
- Reviewers must complete their assignments, inspect disagreements and the Hungary
  historical-source gap, and verify the exact claim/source relationships.
- The frozen dataset lacks independently verified eligible/relevant positives.
  Additional representative positive evidence requires a separately versioned
  future evaluation set. Existing cases retain their recorded definitions.
