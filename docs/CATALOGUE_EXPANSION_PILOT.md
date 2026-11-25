# Phase 8B controlled catalogue expansion pilot

**Run date — 2026-11-25.** The pilot used the Phase 8A collector on
`feature/catalogue-expansion`, based on the PR #11 merge `c3666d7`. All seven
candidate awards were absent from the 22-record curated catalogue and its alias
registry. The automatic and manual checks below cover programme identity and
evidence gaps. Publication and independent validation remain pending.

## Candidate and source review

Each candidate has one exact manual-entry URL in the collector registry. The
primary page supplied a short excerpt for Qwen. Supplementary pages informed
the review notes only, so their facts did not enter that draft's input. Course
admission requirements, scholarship eligibility, and award availability require
separate review.

| Candidate | Official evidence and remaining checks |
| --- | --- |
| Chevening Kazakhstan | The country page lists the Kazakhstan route, eligible one-year taught UK master's courses and a closed 2027–28 round. Confirm the next call and date, work and return requirements, course admission, and any award-specific limitations. [Country page](https://www.chevening.org/scholarship/kazakhstan/) · [Eligibility](https://www.chevening.org/resource-hub/guidance/eligibility/) |
| Oxford Clarendon Fund | Course fees and a living grant are published for eligible study, with no nationality restriction. The funding deadline varies by course in December or January. Confirm the chosen course, study mode and applicable stipend. Oxford gives a 3.7 GPA example in its selection guidance, which does not establish a universal minimum. [Fund](https://www.ox.ac.uk/admissions/graduate/fees-and-funding/funding/clarendon) · [Applicant guidance](https://www.ox.ac.uk/admissions/graduate/fees-and-funding/funding/clarendon/applicants) |
| University of Central Asia Cambridge Scholarship | The Trust names Kazakhstan and prioritizes UCA's founding states. It lists international tuition and maintenance, restricts subject areas, and calls for separate UCA and Cambridge applications. Confirm the specific award intake, eligible course, partner deadline and admission conditions. [Award page](https://www.cambridgetrust.org/scholarship/university-of-central-asia-cambridge-scholarship/) |
| MAECI Italy master's grants, Kazakhstan route | The embassy names Kazakhstan and Kyrgyzstan for its 2026/27 call. The 26 March 2026 deadline is past. The call distinguishes second-cycle master's study from other routes. Confirm the next call, local tuition exemptions and any charges before classifying funding or dating a new intake. [Embassy announcement](https://ambastana.esteri.it/ru/news/dall_ambasciata/2026/03/scholarships-to-study-in-italy-2026-2027-academic-year/) · [Official call](https://ambastana.esteri.it/wp-content/uploads/2026/05/Bando-26-27-ENG.pdf) |
| Türkiye Scholarships, graduate route | The provider describes tuition, a standard graduate stipend and supported disciplines. The eligibility page names age and percentage criteria and lists citizenship and enrollment exceptions. Confirm the next official call, course language and terms for the standard route. Keep the percentage in its published form and the scalar GPA null. [Full-time awards](https://www.turkiyeburslari.gov.tr/fulltimeprograms) · [Criteria](https://www.turkiyeburslari.gov.tr/scholarshipsprograms) · [2026 notice](https://turkiyeburslari.gov.tr/announcements/turkiye-scholarships-2026-applications-121) |
| ADB–Japan Scholarship Program | ADB explicitly lists Kazakhstan and publishes full tuition and a subsistence allowance. Japan funds the award, while study destinations depend on designated institutions. This scheme is distinct from the existing MEXT embassy route. Confirm host, named programme, deadline, prior experience, residency and return obligations. [Award page](https://www.adb.org/work-with-us/careers/japan-scholarship-program) |
| McCall MacBain Scholarship, McGill master's route | The provider lists a full award and separate finalist awards. The 2027 call is closed, and the international date depends on the applicant's previous institution. Provider overview and FAQ give inconsistent stipend figures, including two figures on the FAQ. Confirm the applicable rate with the provider and keep the amount null until reconciled. Also confirm programme, endorsement and the next call. [McGill listing](https://www.mcgill.ca/gradapplicants/funding/external/mccall-macbain-scholarship) · [Application](https://mccallmacbainscholars.org/apply/) · [Award overview](https://mccallmacbainscholars.org/program/) · [FAQ](https://mccallmacbainscholars.org/faq/) |

## Access policy

Seven primary pages were inspected through a reference browser. The collector
fetched **zero** provider pages and used **zero** APIs or exports. The offline
policy check returned `manual_review_required` for all seven. For five hosts,
the wildcard robots group had no restriction matching the chosen path. Two
robots files could not be read through the reference tool. A path without a
matching robots restriction does not establish permission for this workflow.
The registry records the observed policy evidence and keeps every entry
manual-only. None of the seven URLs entered the agent's HTTPS allowlist.

| Host | Terms evidence | Robots observation |
| --- | --- | --- |
| Chevening | Its privacy notice provides no collector authorization. Applicable terms granting that access were not located. [Privacy notice](https://www.chevening.org/about/privacy-notice/) | The wildcard admin restriction does not match the country page. [Robots](https://www.chevening.org/robots.txt) |
| Oxford | The legal notice addresses lawful use and copyright. It provides no explicit authorization for this workflow. [Legal notice](https://www.ox.ac.uk/legal) | Wildcard delay of 20 seconds and no disallow matching the fund page. [Robots](https://www.ox.ac.uk/robots.txt) |
| Cambridge Trust | Website privacy and cookie information provided no automated collection authorization. [Privacy](https://www.cambridgetrust.org/privacy-statement/) · [Cookies](https://www.cambridgetrust.org/cookies/) | The wildcard admin restriction does not match the award path. [Robots](https://www.cambridgetrust.org/robots.txt) |
| Italian Embassy in Astana | The embassy links to the ministry's legal notice. It addresses informational use and retained rights without granting automated access. [Legal notice](https://www.esteri.it/it/note-legali/) | Rules were unavailable through the reference tool. [Robots endpoint](https://ambastana.esteri.it/robots.txt) |
| Türkiye Scholarships | The public site's navigation and footer provided no applicable authorization. The application system's data notice addresses applicant information. [Public site](https://www.turkiyeburslari.gov.tr/fulltimeprograms) · [Data notice](https://tbbs.turkiyeburslari.gov.tr/OTS/Announcement/StudentAnno) | Rules were unavailable through the reference tool. [Robots endpoint](https://www.turkiyeburslari.gov.tr/robots.txt) |
| Asian Development Bank | ADB describes personal noncommercial use. Automation permission for the award path and client was not established. [Terms](https://www.adb.org/terms-use) | No wildcard disallow matched the award path. [Robots](https://www.adb.org/robots.txt) |
| McGill | University guidance directs readers to applicable conditions on individual materials. Collector authorization was not established. [Copyright guidance](https://www.mcgill.ca/copyright/faq) | Wildcard delay of 5 seconds. The graduate programme search rule does not match the funding page. [Robots](https://www.mcgill.ca/robots.txt) |

## Measured results

| Measure | Outcome |
| --- | --- |
| New candidates and primary source coverage | 7 candidates, 7 primary pages inspected, plus supporting sources noted above |
| Access policies | 7 reviewed, 0 cleared for automated collection |
| Collector provider pages attempted / retrieved | 0 / 0 |
| Manually supplied inputs / real Ollama calls | 7 / 7 in the main run |
| Staged drafts / extraction errors | 7 / 0 |
| Exact-span field completeness | 10 of 91 populated, 81 null. All populated spans were present in the submitted excerpts. |
| Catalogue overlap, related drafts, machine-comparable conflicts | 0 / 0 / 0 |
| Manual source conflicts | 1 stipend discrepancy to reconcile, on McCall MacBain |
| Pending / approved / published | 7 / 0 / 0 |
| Independently verified extraction accuracy | Not measured |

| Candidate | Populated / 13 | Null | Local draft ID prefix |
| --- | ---: | ---: | --- |
| Chevening Kazakhstan | 2 | 11 | `bff366cce275` |
| Oxford Clarendon Fund | 1 | 12 | `8997e1d307d9` |
| UCA Cambridge | 1 | 12 | `faa0b270908f` |
| MAECI Italy | 2 | 11 | `9e8647550d17` |
| Türkiye Scholarships | 2 | 11 | `a19a8fa5ec97` |
| ADB–Japan | 1 | 12 | `4cf0a3813140` |
| McCall MacBain | 1 | 12 | `98cd81338ea4` |

The extractor populated seven name fields and three provider fields. Degree,
destination, subjects, citizenship, funding classification and amount, intake,
deadline, GPA, language and prior-degree fields stayed null in every draft.
For example, Qwen used the Chevening country heading as both name and provider,
and placed a country name in MAECI's provider slot. Exact-span validation
cannot check whether a phrase supports the field. The automatic comparison had
no structured funding or deadlines to compare. Reviewers must confirm the
closed calls and current opportunities directly using the sources above.

A separate local diagnostic replayed the MAECI, Türkiye and ADB inputs with
the same model. The baseline stopped normally with the same limited field
coverage. An experimental schema requiring explicit nulls recovered three
exact-span fields for MAECI, including the historical deadline, but returned
only nulls for Türkiye and ADB. This experiment staged no extra drafts, and
the production extraction schema is unchanged.

## Reproduce the pilot

Use local Ollama with the installed `qwen3:4b-instruct` and the existing Python
environment. Run from the repository root. Manually review each official page
and prepare a small UTF-8 input in an ignored directory. Use verbatim fragments
from the single primary URL, with one fragment per line. For this run those
files were under `.local-run/collection/phase-08b/`. The local staging database
stores each exact excerpt, retrieval date, hash, claim and source URL for review.
The repository holds source links and summaries only.

```powershell
$stage = '.local-run/collection/phase-08b/review.sqlite3'
$url = 'https://www.chevening.org/scholarship/kazakhstan/'
\.venv\Scripts\python.exe -m backend.collection --stage-db $stage collect $url --dry-run
\.venv\Scripts\python.exe -m backend.collection --stage-db $stage collect $url --manual-text .local-run/collection/phase-08b/chevening-kz.txt --retrieved-on 2026-11-25
\.venv\Scripts\python.exe -m backend.collection --stage-db $stage list
\.venv\Scripts\python.exe -m backend.collection --stage-db $stage inspect DRAFT_ID
```

For a new run, use the actual retrieval date and an independent queue if
comparing runs. Start with the headline and the following page sections to
locate the input spans. Verify that the same source is displayed before using
it. The reviewer can find the original run in the local queue by ID.

| Local input | Page sections |
| --- | --- |
| `chevening-kz.txt` | Country title, closed banner, and master's-course search description |
| `clarendon.txt` | Fund title and quick facts on fees, living support and degree level |
| `uca-cambridge.txt` | First sentence of scholarship information, listing countries |
| `maeci-italy.txt` | Embassy title, countries at the end of the opening paragraph, and deadline |
| `turkiye.txt` | Graduate programme title, standard master's stipend and tuition bullets, and graduate-programme description |
| `adb-jsp.txt` | Award title, tuition and living support bullets, approved master's course criterion and Kazakhstan under citizenship |
| `mccall-macbain.txt` | The first two sentences of McGill's flagship graduate award listing |

## Review and scaling

The collector compares the drafts with the shipped catalogue and documented
aliases. It checks exact URLs and normalized names and flags related staged
drafts. Aliases or related awards that the rules cannot match need manual
reconciliation. The Phase 8A review gate requires original evidence, a genuine
human decision, a reviewed record and exact spans for populated fields before
publication. Apply that process to current calls and keep historical deadlines
tied to the original intake. No reviewer decisions were recorded.

To grow from 22 toward 50–60 programmes, first assemble a queue of 28–38
distinct awards after deduplication. Work in batches of 5–10 with confirmed
programme and award identities, independent admissions and scholarship checks,
and one disposition per candidate. Review terms before considering any new
automated fetch. Track coverage and unresolved fields by provider and intake.
Before claiming extraction accuracy or changing the default extractor, use a
separate, independently annotated sample that includes negative, conflicting
and partially documented fields.

## Regression checks

- Backend pytest with warnings treated as errors and Ruff lint and formatting
  checks passed. All 749 backend tests passed after the registry additions.
  Collector security tests use mocked DNS and provider transport.
- Vitest passed 207 tests and Playwright passed 22 Chromium tests. Chromium
  used an isolated temporary catalogue and mocked model responses where
  specified. ESLint, TypeScript, Vite production build, `pip check` and
  `npm ls --all` passed.
- The seven primary extraction calls and the six diagnostic calls used the
  installed Qwen model over local Ollama. The pilot made no live collector fetches.
