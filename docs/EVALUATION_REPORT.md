# Scholarship Hunter AI evaluation and reliability

Assessment date **2026-11-12**. Experiments use the 22-record catalogue and the installed local **qwen3:4b-instruct** through **Ollama 0.40.16**, with Python **3.14.2** on Windows. The project reports an RTX 3050 with 6 GB VRAM. Runtime GPU utilization was unmeasured.

The deterministic baseline produced candidates for **19/20 profiles**. The model produced validated selections for **3/20**. The combined model and deterministic-fallback response covered **12/20**. The source-excerpt probe measured **77.27% precision, 91.89% recall and 83.95% F1**. Proposal-level targets remain **NOT EVALUABLE** under the annotation and coverage limits below.

## Data and annotation provenance

| Evaluation unit | Unique sample size | Annotation scope |
| --- | ---: | --- |
| Synthetic student profiles | 20 | Qualification, completion, subject, nationality, GPA scales, missing scores, funding preferences and start years |
| Eligibility cases | 60 | Three programme families across the same 20 profiles |
| Source-backed negative gold cases | 30 | 20 closed MEXT calls and 10 DAAD full-funding preference conflicts |
| Provisional eligibility cases | 20 | 19 `needs_verification` expectations and one past-intake failure |
| Unresolved eligibility cases | 10 | Expected verdict is null |
| Relevance judgments | 80 | 50 verified negatives and 30 unresolved values |
| Source-extraction examples | 12 | 37 explicit field/value annotations from 12 official pages |
| Citation judgments | 24 | 20 supported and four unresolved claim/source pairs |

An AI research assistant prepared the annotations through independent official-source inspection before observing engine or extraction-model outputs. Team/instructor adjudication is pending. Each case names its programme, label status, rationale and official URLs. The negative gold subset contains one class and two repeatedly used evidence families. The ten funding-preference labels apply the application's documented funding convention. Programme admission remains unresolved. Full annotation definitions and provenance are available with the dataset. [Dataset documentation](../evaluation/data/README.md), [eligibility cases](../evaluation/data/eligibility_cases.json), [source annotations](../evaluation/data/source_annotations.json)

Source-extraction excerpts contain at most 25 quoted words per unique page. Annotations describe fields explicitly present in each excerpt. Currency symbols normalize to the stated currency code. Numeric IELTS values describe the quoted test route, with alternatives represented separately. All 22 production records retain their existing facts and source dates.

## Experimental protocol

Two complete trials used identical profile, catalogue, annotation and implementation hashes. Each trial executed 20 baseline requests, 20 real agent recommendation requests, 60 real case-specific agent audits and 12 real extraction probes. The unique population remains 20 profiles, 60 eligibility cases and 12 excerpts. The second trial used native process permissions after the first exposed restricted external-network access. Both trials completed with exit code 0 and are retained. The native-process trial supplies the main tables.

The baseline calls the existing matching endpoint function against temporary SQLite data, including its database query and ranking work. It assesses all 22 records and returns up to three candidates without confirmed failures. The agent uses the same profiles, data and server-controlled assessment date. Recommendation prompts come from the shared profile file. Case-specific prompts additionally name the target programme and one published destination. Gold labels and expected extraction fields are excluded from model prompts.

Agent classification measurements use assessments actually obtained through model-requested tools. Missing target assessments count as unsuccessful end-to-end gold cases in the JSON confusion matrix. Provisional agreement is reported separately. Fallback assessments never populate that model-assessment cache.

Inference uses a 4,096-token context, 384 output tokens, temperature 0 and disabled thinking. The model digest is `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`. The runtime enforces four model rounds, eight attempted tool calls, a 90-second total deadline, 45-second model-call deadlines and the existing 3,300-token input-size estimate. Web retrieval retains the approved-URL, public-IP, TLS, redirect, timeout and size checks.

Requests ran sequentially in fixed order after diagnostic warm-up. Per-request service latency includes tool/database work and local inference. Startup, catalogue import, checkpoint writing, HTTP/UI transport and earlier warm-up are excluded. The combined response includes model attempt time and fallback computation. P95 uses the nearest-rank definition. One observation per profile in each environment supports descriptive timing. Confidence intervals and causal improvement claims require a broader randomized design.

All results, model-round diagnostics, actual tool attempts, source metadata and normalized hashes are recorded in the two experiment files. [Native-process trial](../evaluation/results/native_2026-11-12.json), [restricted-process trial](../evaluation/results/local_2026-11-12.json)

The JSON records the checkout commit before this evaluation commit and hashes of the tested working files. The pull request includes those hashed implementation and dataset files.

## Core metrics and proposal targets

| Metric | Measured evidence | Proposal target | Target decision |
| --- | --- | --- | --- |
| Three-class eligibility accuracy | Baseline 30/30 on source-backed negative gold cases. Agent assessed 0/30 gold targets. | At least 90% | **NOT EVALUABLE** with missing gold classes and pending adjudication |
| Requirement extraction | Preliminary excerpt probe precision 77.27%, recall 91.89%, F1 83.95% | F1 at least 85% | **NOT EVALUABLE** for the application target with draft short-excerpt annotations |
| Recommendation Precision@3 | Zero profiles have three verified eligible/relevant opportunities | At least 80% | **NOT EVALUABLE** |
| Citation coverage and support | All sampled name/funding claims have links. Support audit coverage varies from 40.00% to 91.23%. | 100% factual citation coverage | **NOT EVALUABLE** for complete claim support |

### Eligibility cases

| Measure | Baseline | Real agent case audits |
| --- | ---: | ---: |
| Evaluated case requests | 60 cases from 20 full-catalogue assessments | 60 case-specific requests |
| Target assessments available | 60/60 | 8/60, 13.33% |
| Gold target assessments available | 30/30 | 0/30 |
| Correct source-backed negative gold cases | 30/30, 100.00% | 0/30 end-to-end completion |
| Wrong verdicts among assessed gold cases | 0/30 | **NOT EVALUABLE**, no gold target verdicts emitted |
| Provisional expectation agreement | 20/20 | 8/20, 40.00% |
| Verified `eligible` gold examples | 0 | 0 |

The agent's JSON end-to-end gold score is 0.00% because all 30 entries occupy the `missing_or_invalid` column. This measures failure to retrieve and assess the named targets. Conditional verdict accuracy for those targets is **NOT EVALUABLE**. All eight available agent target verdicts concern provisional cases. The baseline's negative-only score and provisional agreement require the stated class and evidence limits.

### Source-excerpt extraction probe

This evaluation-only task asks local Qwen for bounded flat JSON using the supplied excerpt. The production recommendation endpoint uses curated facts and deterministic rules. Excerpt annotations are held separately from model input.

| Count or metric | Result |
| --- | ---: |
| Examples with model outputs | 12/12 |
| Annotated non-null assertions | 37 |
| Predicted non-null assertions | 44 |
| True positives | 34 |
| False positives | 10 |
| False negatives | 3 |
| Precision | 34/44 = 77.27% |
| Recall | 34/37 = 91.89% |
| F1 | 68/81 = 83.95% |

Scoring matches exact typed field/value pairs. Wrong values count once as a false positive and once as a false negative. Unsupported non-null fields count as false positives, including `false` flags and the literal string `unknown`. Omitted/null fields make no positive assertion. The same counts occurred in both trials.

Eight false positives were unsupported boolean assertions about IELTS exclusivity or tuition coverage. Two involved stipend-period values, including a duration substituted for a payment period and `monthly` used where the contract requests `month`. Three expected period assertions were missed. These errors show the need for explicit evidence checks before extracted fields become executable eligibility rules.

### Citation coverage and source support

The sampled claim scope covers emitted programme names and published funding labels in ranking explanations. The independent annotations join the exact programme, field, value and cited URL. Unreviewed pairs remain unresolved. Repeated claims across profiles count as output occurrences.

| Output group | Linked claims | Audited and supported | Contradicted in audited scope | Unresolved | Audit coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline candidates | 114/114 | 104/104 audited | 0 | 10 | 91.23% |
| Raw agent selections | 10/10 | 4/4 audited | 0 | 6 | 40.00% |
| Deterministic fallback | 50/50 | 44/44 audited | 0 | 6 | 88.00% |

Reference presence measured 100% in this claim scope. No contradicted claims were found among the 104, four and 44 audited occurrences respectively. Review of all requirement explanations, temporal claims, student-specific conclusions and remaining source pairs is pending. These limits keep the proposal's complete citation-support target **NOT EVALUABLE**. Rejected model replies receive no public factual credit.

## Baseline versus local agent

The native-process recommendation comparison uses the same 20 profiles. Every returned candidate in this table carries `needs_verification`. None received an `eligible` classification.

| Measure | Deterministic baseline | Raw Qwen selection | Model plus fallback |
| --- | ---: | ---: | ---: |
| Requests with candidates | 19/20, 95.00% | 3/20, 15.00% | 12/20, 60.00% |
| Requests without candidates | 1/20, 5.00% | 17/20, 85.00% | 8/20, 40.00% |
| Transport/protocol exceptions | 0/20 | 0/20 | 0/20 |
| Model budget stops | 0 | 10/20 | Model status retained |
| Mean service latency | 0.001524 s | 3.514293 s | 3.514293 s |
| Median service latency | 0.001453 s | 3.126650 s | 3.126650 s |
| P95 service latency | 0.001570 s | 6.390165 s | 6.390165 s |
| Model-requested tool attempts | 0 | 69 | Same 69 attempts |
| Successful tool attempts | **NOT EVALUABLE**, zero attempts | 68/69, 98.55% | Same model attempts |

The fallback supplied candidates for nine additional requests. It operates on retrieved records, so unsuccessful discovery still limits coverage. A tool success means that dispatch returned validated data, including empty search results. Exception rate counts Ollama unavailable/timeout/protocol exceptions. Abstention counts responses without a model selection and includes budget stops and errors. These definitions preserve both failure and abstention information.

Across the 60 native case audits, 182/189 tool attempts succeeded, 15 requests returned model selections and 14 contained a candidate without a confirmed failure. One returned candidate retained an `ineligible` classification. The named-target assessment coverage remained 8/60.

### Environment comparison

| Recommendation-request measure | Restricted process | Native process |
| --- | ---: | ---: |
| Raw model candidate coverage | 3/20 | 3/20 |
| Model plus fallback coverage | 12/20 | 12/20 |
| Mean model request latency | 3.252903 s | 3.514293 s |
| P95 model request latency | 3.754722 s | 6.390165 s |
| Model budget stops | 9/20 | 10/20 |
| Successful tool attempts | 66/69 | 68/69 |

Across all 80 agent requests per trial, the restricted process recorded 13 failed official-page reads. The native process recorded five successful reads, four blocked reads and four retrieval errors. The trials share the same data, implementation, model digest and options. Permissions, observed plan variation and changing live page contents confound causal attribution in this environmental comparison.

## Error analysis and reliability changes

The earlier failure was reproduced with a synthetic Computer Science profile. Qwen searched successfully and received IDs 2, 3 and 4. It selected those IDs twice without obtaining eligibility assessments, and the validator rejected both selections. It then returned an empty selection. The largest reported prompt contained 1,172 tokens and the largest input estimate was 2,598. The recorded diagnostic includes the exact request and four-round trace. Its elapsed time was unrecorded. [Before-edit diagnostic](../evaluation/results/selection_failure_before_fix.json)

The current implementation provides explicit `assessment_required` feedback, a current remaining-step message and compact ranking replies that reuse earlier source metadata. The four/eight limits remain enforced. It also reassesses retrieved records for a separately labeled deterministic fallback containing only `needs_verification` results. Confirmed failures and reviewed eligible records retain their existing classifications and are excluded from this fallback. Fallback work leaves model-assessment authorization intact. API errors still expose the existing deterministic matching route.

The full trials identify additional limitations.

1. **Named-target retrieval fails.** In `P01-MEXT-CLOSED`, Qwen searched Japan with Computer Science and full-funding filters. The MEXT record has an unknown field list, so the search returned IMLEX. Qwen assessed IMLEX and selected it. In the DAAD audit, a full-funding filter excluded the named partial award. The agent search interface currently exposes country, field and funding filters.
2. **Serial checks consume the round budget.** Some plans spend the search round and three separate checking rounds on three candidates, leaving no final selection round. Across the 80 native requests, six ranking-tool calls occurred, alongside 165 searches and 74 individual checks. Repeated searches also occur.
3. **Context was sufficient for these failures.** The largest reported prompt across either full trial contained 1,452 tokens, with a maximum input estimate of 3,144. Zero context-budget stops occurred. Model step exhaustion and query/target routing dominated this sample.
4. **Missing evidence continues to limit verdicts.** The catalogue has zero complete reviewed eligibility policies. Language alternatives, component scores, prior-qualification equivalence and other conditions remain unresolved.
5. **Source retrieval needs visible failure handling.** Native access improved page-read outcomes, while URL/content guards and retrieval errors still limited evidence. Retrieved text cannot change the reviewed catalogue or rule classifications.
6. **Fallback has bounded reach.** It returns source-linked retrieved candidates with explicit missing evidence. It cannot recover a target that filtering never discovered. Its 60% combined coverage and request latency remain behind the deterministic baseline in this sample.

## Executed verification

| Check | Actual result |
| --- | --- |
| Backend pytest with warnings treated as errors | 457 passed |
| Frontend component/integration tests | 118 passed |
| Chromium browser suite | 17 passed, exit 0 |
| Ruff lint and formatting | Passed |
| ESLint | Passed |
| TypeScript and production build | Passed |
| Python dependency consistency | No broken requirements |
| npm dependency graph | Passed |
| npm vulnerability audit | 0 vulnerabilities |
| Real inference | Two complete trials, each with 80 agent workflows and 12 extraction probes |

Ordinary automated tests use mocked model/network responses with real service dispatch and temporary SQLite data. Real experiments use the installed Ollama model. Browser tests validate the separate fallback section using mocked AI replies and real deterministic assessments. The fallback screenshot was visually reviewed. Health, filtering, pagination, source protections, timeouts, injection containment and conservative classifications remain covered by regression tests.

## Reproduction and next steps

Run from the repository root in PowerShell with the existing environment and local Ollama model.

```powershell
.\.venv\Scripts\python.exe -m backend.evaluation.run --output "$env:TEMP\scholarship-baseline-evaluation.json"
.\.venv\Scripts\python.exe -m backend.evaluation.run --real-model --output "$env:TEMP\scholarship-evaluation.json"
.\.venv\Scripts\python.exe -m backend.evaluation.run --real-model --resume --output "$env:TEMP\scholarship-evaluation.json"
```

The baseline-only command marks unexecuted model metrics **NOT EVALUABLE**. The live runner creates a temporary database, writes an atomic checkpoint after each experiment and verifies normalized input/code hashes, model digest, Ollama version and assessment date on resume. Normalizing UTF-8/BOM and line endings permits equivalent Windows checkouts. Each output records full numerical values and trace diagnostics. Output contains synthetic academic data and public scholarship metadata.

Next steps are team adjudication of the draft labels, verified eligible and uncertainty gold cases, independently judged positive opportunities for Precision@3, and complete factual-claim audits. Retrieval experiments should test named-programme lookup and treatment of unknown filter fields on held-out cases. Planning experiments should measure batching or smaller candidate sets within the current budget. Repeated randomized trials and longer independently annotated source passages would broaden latency and extraction evidence. Any future changes should retain the current failed cases for regression evaluation.
