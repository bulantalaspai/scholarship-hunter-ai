# Independent human review

This package contains **284 AI-prepared provisional items** and **568 blank
review assignments**. It preserves the 60 frozen eligibility cases and all
20 synthetic profiles. The team's implemented protocol assigns two independent
reviewers per item and uses matching completed decisions for consensus. This
protocol is a project workflow choice.

| Review area | Items | Required decisions |
| --- | ---: | ---: |
| Eligibility | 60 | 120 |
| Extraction fields | 120 | 240 |
| Recommendation relevance | 80 | 160 |
| Citation support | 24 | 48 |

## Assigned files

- [Talaspay Bulan](talaspay_bulan.csv) has 189 assigned items.
- [Sayat Nuradil](sayat_nuradil.csv) has 190 assigned items.
- [Tursbekov Darkhan](tursbekov_darkhan.csv) has 189 assigned items.
- [Manifest](manifest.json) preserves item identifiers, proposed values, complete
  synthetic profiles, source references and assignment provenance.
- [Evidence excerpts](evidence.json) stores each excerpt once. The sheets link
  to the exact evidence identifier and official page.

All reviewer decisions, reviewed values, rationales, review dates, human evidence
references and evidence access dates are blank. The package contains **zero
completed human reviews**. The frozen `verified_gold` designation is retained
only as legacy metadata for AI-authored, source-checked proposals.

## Completing a review

1. Open your CSV using UTF-8 text encoding. Read the synthetic profile, proposed
   label, official evidence links and referenced excerpt. Eligibility and
   relevance items include the complete profile in a single JSON cell.
2. Visit the official page and verify the exact scholarship scheme, edition,
   nationality route and condition against the fixed assessment date of
   **2026-11-12**. Admission conditions and scholarship funding have separate
   scopes. A high GPA or English score cannot establish unspecified conditions.
3. Enter `accept`, `revise` or `unresolved` in `reviewer_decision`. Enter the
   independently reviewed typed value in `reviewed_value`, including for an
   accepted proposal. Use JSON syntax as shown below. An `accept` decision must
   retain the proposed value. A `revise` decision must change it.
4. Complete `rationale`, `review_date`, `review_evidence_url`,
   `review_evidence_excerpt_or_section` and `evidence_access_date`. Dates use
   `YYYY-MM-DD`. The evidence URL must use an official host associated with
   that programme. Citation-support items require the exact cited page, with
   section anchors allowed. Other review categories allow a new path on that
   programme's official host. Record a short passage or precise section reference
   supporting the specific claim and its scope.
5. Preserve the supplied item, profile, scholarship, source, reviewer and checksum
   fields. Discuss disagreements using the retained rationales. Edit a completed
   decision only after its reviewer has actually reconsidered the evidence.

| Category | Typed examples | Meaning |
| --- | --- | --- |
| Eligibility | `"eligible"`, `"ineligible"`, `"needs_verification"`, `null` | Human-confirmed uncertainty is a valid needs-verification class. Null is unresolved. |
| Extraction | `6.5`, `1400`, `true`, `false`, `"EUR"`, `"month"`, `"2027-01-13"`, `null` | Values follow the frozen excerpt's requested field contract. A reviewed null confirms absence from that bounded excerpt. |
| Relevance | `true`, `false`, `null` | A positive requires verified applicant eligibility and suitability. Null remains unresolved. |
| Citation support | `"supported"`, `"unsupported"`, `"unresolved"`, `null` | Judge the exact field/value/URL claim. A link alone supplies no support decision. |

Extraction includes all ten allowed fields for each of the twelve frozen excerpts.
There are 37 positive AI proposals and 83 proposed null absences. Those absences
require independent review. The complete ten-field coverage allows false-positive
scoring after an example is fully reviewed. Context from a full webpage must not
be used to introduce a fact absent from the bounded extraction excerpt.

Use a `reviewer_decision` of `unresolved` with a JSON `null` reviewed value when
you cannot decide. Complete the remaining attestation fields to explain the gap.
Unresolved decisions supply no final metric label. Human names on an assignment
sheet identify who should review it and carry no implication that review occurred.
Keep student names, contacts, application documents and other personal information
out of the review cells. The profiles supplied here are synthetic.

## Evidence provenance

Twelve source excerpts retain their frozen **2026-11-12** access dates. Three
short supplementary official excerpts from the Japan embassy and SMACCs admission
and deadline pages were checked by an AI assistant on **2026-11-13**. Catalogue
verification dates remain separately recorded in the manifest. Each source is
linked beside its excerpt and limitations. These preparation dates supply no
human-review attestation. [Evidence registry](evidence.json)

The Stipendium Hungaricum historical-call page could not be fetched during package
preparation. Its frozen curator paraphrase remains explicitly marked as requiring
verbatim and historical-call verification. No new source quote is attributed to
that inaccessible page. Reviewers should retain an unresolved judgment if the
historical claim cannot be independently established. The DAAD tuition excerpt
supports a funding-preference conflict under the application's convention and
supplies incomplete evidence for admission eligibility.

## Generate and validate

Run from the repository root using the existing Python environment.

```powershell
.\.venv\Scripts\python.exe -m backend.evaluation.reviews generate --output evaluation/human_review
.\.venv\Scripts\python.exe -m backend.evaluation.reviews validate --package evaluation/human_review --output "$env:TEMP\scholarship-human-reviews.json"
```

Generation refuses to replace any sheet containing human input, including a
partially completed row. Blank sheets can be regenerated reproducibly. Keep a
separate versioned copy before adopting a changed annotation protocol or source
snapshot.

Validation checks source and manifest hashes, immutable CSV fields, assignments,
unique and complete item coverage, typed values, source-host references, required
rationales and date ordering. Invalid input exits with code 2 and supplies no
partially accepted label set. The script records disagreements and excludes
pending, partial and unresolved items from consensus. Two matching completed
assigned reviews supply a `reviewed` item. Every completed attestation remains in
the output for inspection.

The validator can check the recorded attestations and their consistency. Human
identity, independent decision-making, actual page access and factual support
require external verification. Automated unit-test attestations exist only in
temporary test directories. They are fictional regression fixtures.

## Academic measurement status

Eligibility accuracy, extraction precision/recall/F1, recommendation Precision@3
and factual citation support need independent completed labels for their scored
items. All relevant human-label metrics currently remain **NOT EVALUABLE**.
Eligibility scoring excludes unresolved judgments, while a human-reviewed
`needs_verification` verdict is included as its own class. Precision@3 additionally
requires at least three independently verified eligible/relevant opportunities
per scored profile. A relevance `true` label requires a corresponding reviewed
`eligible` classification. The present dataset has no such completed positives.
