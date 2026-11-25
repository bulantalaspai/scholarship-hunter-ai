# Phase 8C independent evidence review sheet

Duplicate this sheet for each reviewer and keep completed copies in an ignored local directory. Review the same seven Phase 8B inputs and the same 13 field slots for both runs. These short, deliberately selected English excerpts are a diagnostic sample. Keep the resulting observations separate from the frozen evaluation annotations and from catalogue approval.

**Reviewer ID** ____________________

**Review date (UTC)** ____________________

**Run-to-label mapping (held by coordinator until scoring ends)** ____________________

## How to review

1. Read the original UTF-8 file for each case in `.local-run/collection/phase-08b/`. Compare its exact bytes or SHA-256 with the baseline and revised draft provenance. Preserve the original bytes, line breaks and fragment order. Keep the original retrieval date attached to every reading of the frozen excerpt. If an input or hash differs, record the difference and exclude that pair from the comparison.
2. Fill the **Excerpt** column for all 91 slots before seeing model outputs. Use `supported`, `insufficient`, or `conflict`. In your local notes, record the smallest complete source span and include its line numbers or character offsets, conditions, scope and any relevant date. Count every slot, including missing evidence. Keep facts from supplementary pages outside these labels.
3. Have the coordinator prepare outputs A and B in randomized order with run identity held back. The coordinator can read `.local-run/collection/phase-08c/baseline.json` and inspect the matching revised draft by its full ID with the commands below. Give the reviewers only values and evidence needed to score, with run names and timestamps removed. Reviewers compare each populated value with its cited span and then read the surrounding frozen excerpt. Label empty values `insufficient` if the excerpt lacks support. Record any omitted supported value as `supported` in **Excerpt** and `omitted` in the run column.

```powershell
$stage = '.local-run/collection/phase-08c/review.sqlite3'
.\.venv\Scripts\python.exe -m backend.collection --stage-db $stage list
.\.venv\Scripts\python.exe -m backend.collection --stage-db $stage inspect FULL_DRAFT_ID
```

4. Record disagreements before adjudication. Ask a second reviewer to label the same input independently. Preserve both readings and record the agreed label with an evidence-based rationale. Report agreement and unresolved cases separately. Keep exact source passages, dates and decisions local. Recording a label here leaves the draft in its existing review state.

| Label | Meaning |
| --- | --- |
| `supported` | The exact cited passage supports this field and the claimed value, scope, cycle, and qualifications. |
| `misattributed` | The cited phrase is present but belongs to another field, entity, amount category, cycle, scope, or qualification. Record literal mismatches separately in notes. |
| `insufficient` | The supplied excerpt cannot establish the field. If a run populates it anyway, record the output as unsupported in notes. |
| `conflict` | Two relevant statements differ and the available context cannot reconcile their cycles, scope, or authority. Retain both provenance trails. |
| `omitted` | The run returned null although the excerpt could support a value. This label applies only to run columns. |

For funding, assess amount, currency, cadence and payment scope individually in **Evidence / notes** even though `funding_amount` is one comparison slot. For dates, distinguish opening, deadline, intake, publication and retrieval. For admissions, keep language alternatives, threshold scale and prior qualifications as written. Treat a location in an award title as a clue that needs explicit destination evidence.

## Frozen field grid

### Chevening Kazakhstan

Input `chevening-kz.txt`. [Primary source](https://www.chevening.org/scholarship/kazakhstan/)

| Field | Excerpt | Run A | Run B | Evidence / notes |
| --- | --- | --- | --- | --- |
| Programme name · `scholarship_name` | | | | |
| Institution or provider · `university_or_provider` | | | | |
| Study destination · `destination_country` | | | | |
| Degree level · `degree_level` | | | | |
| Academic field · `eligible_study_fields` | | | | |
| Funding type · `funding_type` | | | | |
| Funding amount, currency and payment period · `funding_amount` | | | | |
| Application deadline · `application_deadline` | | | | |
| Intake or cycle · `application_cycle` | | | | |
| Eligible nationality · `eligible_nationalities` | | | | |
| GPA condition · `gpa_requirement` | | | | |
| IELTS or other language condition · `language_requirement` | | | | |
| Prior degree · `prior_degree_requirement` | | | | |

### Clarendon Fund

Input `clarendon.txt`. [Primary source](https://www.ox.ac.uk/admissions/graduate/fees-and-funding/funding/clarendon)

| Field | Excerpt | Run A | Run B | Evidence / notes |
| --- | --- | --- | --- | --- |
| Programme name · `scholarship_name` | | | | |
| Institution or provider · `university_or_provider` | | | | |
| Study destination · `destination_country` | | | | |
| Degree level · `degree_level` | | | | |
| Academic field · `eligible_study_fields` | | | | |
| Funding type · `funding_type` | | | | |
| Funding amount, currency and payment period · `funding_amount` | | | | |
| Application deadline · `application_deadline` | | | | |
| Intake or cycle · `application_cycle` | | | | |
| Eligible nationality · `eligible_nationalities` | | | | |
| GPA condition · `gpa_requirement` | | | | |
| IELTS or other language condition · `language_requirement` | | | | |
| Prior degree · `prior_degree_requirement` | | | | |

### University of Central Asia Cambridge Scholarship

Input `uca-cambridge.txt`. [Primary source](https://www.cambridgetrust.org/scholarship/university-of-central-asia-cambridge-scholarship/)

| Field | Excerpt | Run A | Run B | Evidence / notes |
| --- | --- | --- | --- | --- |
| Programme name · `scholarship_name` | | | | |
| Institution or provider · `university_or_provider` | | | | |
| Study destination · `destination_country` | | | | |
| Degree level · `degree_level` | | | | |
| Academic field · `eligible_study_fields` | | | | |
| Funding type · `funding_type` | | | | |
| Funding amount, currency and payment period · `funding_amount` | | | | |
| Application deadline · `application_deadline` | | | | |
| Intake or cycle · `application_cycle` | | | | |
| Eligible nationality · `eligible_nationalities` | | | | |
| GPA condition · `gpa_requirement` | | | | |
| IELTS or other language condition · `language_requirement` | | | | |
| Prior degree · `prior_degree_requirement` | | | | |

### MAECI Italy

Input `maeci-italy.txt`. [Primary source](https://ambastana.esteri.it/ru/news/dall_ambasciata/2026/03/scholarships-to-study-in-italy-2026-2027-academic-year/)

| Field | Excerpt | Run A | Run B | Evidence / notes |
| --- | --- | --- | --- | --- |
| Programme name · `scholarship_name` | | | | |
| Institution or provider · `university_or_provider` | | | | |
| Study destination · `destination_country` | | | | |
| Degree level · `degree_level` | | | | |
| Academic field · `eligible_study_fields` | | | | |
| Funding type · `funding_type` | | | | |
| Funding amount, currency and payment period · `funding_amount` | | | | |
| Application deadline · `application_deadline` | | | | |
| Intake or cycle · `application_cycle` | | | | |
| Eligible nationality · `eligible_nationalities` | | | | |
| GPA condition · `gpa_requirement` | | | | |
| IELTS or other language condition · `language_requirement` | | | | |
| Prior degree · `prior_degree_requirement` | | | | |

### Türkiye Scholarships

Input `turkiye.txt`. [Primary source](https://www.turkiyeburslari.gov.tr/fulltimeprograms)

| Field | Excerpt | Run A | Run B | Evidence / notes |
| --- | --- | --- | --- | --- |
| Programme name · `scholarship_name` | | | | |
| Institution or provider · `university_or_provider` | | | | |
| Study destination · `destination_country` | | | | |
| Degree level · `degree_level` | | | | |
| Academic field · `eligible_study_fields` | | | | |
| Funding type · `funding_type` | | | | |
| Funding amount, currency and payment period · `funding_amount` | | | | |
| Application deadline · `application_deadline` | | | | |
| Intake or cycle · `application_cycle` | | | | |
| Eligible nationality · `eligible_nationalities` | | | | |
| GPA condition · `gpa_requirement` | | | | |
| IELTS or other language condition · `language_requirement` | | | | |
| Prior degree · `prior_degree_requirement` | | | | |

### ADB–Japan Scholarship Program

Input `adb-jsp.txt`. [Primary source](https://www.adb.org/work-with-us/careers/japan-scholarship-program)

| Field | Excerpt | Run A | Run B | Evidence / notes |
| --- | --- | --- | --- | --- |
| Programme name · `scholarship_name` | | | | |
| Institution or provider · `university_or_provider` | | | | |
| Study destination · `destination_country` | | | | |
| Degree level · `degree_level` | | | | |
| Academic field · `eligible_study_fields` | | | | |
| Funding type · `funding_type` | | | | |
| Funding amount, currency and payment period · `funding_amount` | | | | |
| Application deadline · `application_deadline` | | | | |
| Intake or cycle · `application_cycle` | | | | |
| Eligible nationality · `eligible_nationalities` | | | | |
| GPA condition · `gpa_requirement` | | | | |
| IELTS or other language condition · `language_requirement` | | | | |
| Prior degree · `prior_degree_requirement` | | | | |

### McCall MacBain Scholarship

Input `mccall-macbain.txt`. [Primary source](https://www.mcgill.ca/gradapplicants/funding/external/mccall-macbain-scholarship)

| Field | Excerpt | Run A | Run B | Evidence / notes |
| --- | --- | --- | --- | --- |
| Programme name · `scholarship_name` | | | | |
| Institution or provider · `university_or_provider` | | | | |
| Study destination · `destination_country` | | | | |
| Degree level · `degree_level` | | | | |
| Academic field · `eligible_study_fields` | | | | |
| Funding type · `funding_type` | | | | |
| Funding amount, currency and payment period · `funding_amount` | | | | |
| Application deadline · `application_deadline` | | | | |
| Intake or cycle · `application_cycle` | | | | |
| Eligible nationality · `eligible_nationalities` | | | | |
| GPA condition · `gpa_requirement` | | | | |
| IELTS or other language condition · `language_requirement` | | | | |
| Prior degree · `prior_degree_requirement` | | | | |

## Separate McCall MacBain chronology review

Review current and earlier stipend references independently of the frozen 91-slot comparison. Use dates printed on the source or independently verifiable dated snapshots. Keep the retrieval date, page publication or revision date, award cycle, and academic-term scope separate. If a source supplies no date or cycle, leave it unknown. Evaluate whether the figures describe the same award and period before treating them as a conflict or as a change over time. Leave the active amount unresolved when the source record cannot settle that question. [Award overview](https://mccallmacbainscholars.org/program/) · [Provider FAQ](https://mccallmacbainscholars.org/faq/) · [Application cycle](https://mccallmacbainscholars.org/apply/)

| Check | Observation or label | Official URL or local evidence locator |
| --- | --- | --- |
| Earlier amount, currency and cadence | | |
| Earlier publication date or cycle and scope | | |
| Current amount, currency and cadence | | |
| Current publication date or cycle and academic-term scope | | |
| Different periods or unresolved same-scope conflict | | |
| Other allowances or funding categories that may be confused with the stipend | | |
| Reviewer reconciliation and remaining verification | | |
