# Human annotation review

This first batch contains seven review items for **Talaspay Bulan**, **Sayat
Nuradil** and **Tursbekov Darkhan**. It covers decisive negative conditions,
incomplete eligibility evidence, extraction errors and unresolved relevance and
citation support. Each member can review any item. No human decisions have been
recorded.

The frozen Phase 6B files use `verified_gold` for AI-authored, source-checked
negative labels. Human adjudication is pending. In this package those labels are
classified as **AI-generated provisional annotations**. Unresolved judgments
retain null values. Model predictions and deterministic verdicts supply no
independent evidence for approving a label.

## Review procedure

1. Open the referenced synthetic profile and annotation by its identifier or JSON
   pointer. Read the linked official source and identify the exact edition,
   scholarship scheme and condition. The benchmark assessment date remains
   **2026-11-12**.
2. Record the source passage or section supporting each reviewed claim, the
   source access date and any disagreement. A changed live page may leave the
   historical claim unresolved. Document that difference explicitly.
3. Append a copy of `human_review_template` to that item's `human_reviews` array.
   Enter your name, ISO review date, decision, reviewed value, rationale and
   evidence. Use `accept`, `revise` or `unresolved` as appropriate. Keep an
   unsupported eligibility or relevance value null.
4. Preserve the AI annotation snapshot and frozen benchmark inputs. Human
   decisions can support a separately versioned evaluation after their evidence
   and scope have been checked. Disagreements remain visible in the review
   records.

Admission, scholarship funding and the application's funding-preference rule
have separate scopes. The DAAD funding-preference example requires checking both
the official tuition exclusion and the synthetic preference. A complete
admission verdict requires additional evidence. `needs_verification` remains
appropriate when the supplied information cannot establish a condition.

## Contents and measurement limits

- [Review batch](review_batch.json) contains source references, AI annotation
  snapshots, questions and empty human-review arrays.
- [Frozen provenance](../data/README.md) defines the assessment conventions and
  evidence families.
- [Source annotations](../data/source_annotations.json) contain the bounded
  extraction excerpts and claim-level support judgments.

The batch has **0 human-reviewed items**. Proposal-level three-class eligibility
accuracy, extraction F1, Precision@3 and complete factual citation support remain
**NOT EVALUABLE** as independently validated academic targets. This small batch
starts the review. Positive eligibility examples, representative sources and
broader claim audits remain necessary for those measurements.
