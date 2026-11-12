# Evaluation annotations

These files use synthetic academic inputs. They contain no student identities,
contact details or documents. The assessment date is fixed at **2026-11-12**.

The 20 profiles vary prior qualification, completion status, study field,
nationality, GPA scale, missing scores, funding preference and intended year.
Eighteen use Kazakhstan nationality, with one Uzbekistan and one India profile.
GPA scales include 4, 5, 10 and 100. Missing scores remain null. Profile P20 requests
2025 to expose handling of a past intended start year.

The 60 eligibility cases cover three programme families across all 20 profiles.
There are **30 verified gold negative labels**, **20 provisional expectations**
and **10 unresolved cases**. Cases identify the exact catalogue scholarship name
and official evidence URLs. Rationales refer to the evidence definitions below.

An AI research assistant authored the annotations through official-source
inspection independently of eligibility-engine and model outputs. Gold denotes a
decisive source-backed negative condition under the stated evaluation convention.
Team or instructor adjudication is pending. This is an initial annotation set.

## Label definitions

- `verified_gold` records a decisive negative condition that can be checked using
  the actual profile fields, fixed assessment date and cited source.
- `provisional` records an expected classification awaiting complete independent
  review. Most cases request `needs_verification` because the academic profile
  cannot establish all admission and award conditions.
- `unresolved` has a null expected classification or relevance judgment and is
  excluded from accuracy or positive-match denominators.

The system's overall eligibility classification incorporates funding preference.
DAAD funding-conflict labels concern that preference. Programme admission remains
unresolved. No case has a verified `eligible` label.

## Evidence definitions

### E-MEXT-CLOSED

The Kazakhstan embassy's published 2027 call closed on 29 May 2026 at 17:00 Astana
time. Its deadline precedes the fixed assessment date. Every associated label
concerns this closed catalogue record. Other national routes and future calls
require their own review. [Kazakhstan embassy call](https://www.kz.emb-japan.go.jp/itpr_ru/11_000001_00641.html)

### E-DAAD-TUITION

The provider excludes tuition fees from its general master's award. That coverage
conflicts with the synthetic profiles requesting full funding under the
catalogue's funding convention. Ten profiles supply that preference. [DAAD award terms](https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200)

### E-DAAD-UNRESOLVED

Ten profiles accept partial funding. That input supplies insufficient evidence
for a complete admission or scholarship verdict. Their expected classification
and relevance judgment remain null. [DAAD requirements](https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200)

### E-SMACCS-REVIEW

The programme publishes degree, language-route, component-score and individual
document conditions. The supplied fields cannot establish every condition.
Equivalence, alternatives, award selection and opening status require review.
Profiles reporting high school, associate or other qualifications do not establish
the absence of additional equivalent qualifications. Their labels remain
provisional. [Admission conditions](https://www.smaccs.eu/admissions/admission-criteria/)

### E-PROFILE-PAST

P20 explicitly requests a 2025 start, before the fixed 2026 assessment year.
Its provisional `ineligible` expectation describes this historical request. The
published scholarship record belongs to a later edition. [Published editions and deadlines](https://www.smaccs.eu/admissions/deadlines/)

### E-HUNGARY-CLOSED

The published 2026/27 application deadline was 15 January 2026. It precedes the
assessment date. Twenty negative relevance judgments concern this historical
catalogue call. [Official call announcement](https://stipendiumhungaricum.hu/news/application-is-on-for-the-2026-2027-stipendium-hungaricum-scholarship/)

All linked pages were opened for annotation review on **2026-11-12**. Facts are
paraphrased and no source-text passages are copied into these three data files.
Catalogue records and their existing review dates are maintained separately.

## Interpretation and sampling limits

`profiles.json` defines the shared inputs and goals for baseline and agent runs.
`eligibility_cases.json` contains static labels saved without executing the
eligibility engine. `relevance_judgments.json` contains 80 programme/profile
judgments across four programme families, with 50 verified negative judgments
and 30 unresolved judgments.

The gold accuracy subset has one class and heavily repeated conditions. Its
sample count represents profile/record pairs, with two decisive evidence families
and shared sources. It provides a limited negative-case accuracy measurement.
The proposal's three-class accuracy target remains **NOT EVALUABLE** because
verified positive and complete independently adjudicated uncertainty labels are
absent. Provisional-label agreement must be reported separately.

Recommendation Precision@3 remains **NOT EVALUABLE**. No profile has three
independently verified eligible and relevant opportunities. Unresolved judgments
must retain their null values during evaluation. Topic similarity, engine
classification and presence in a recommendation list cannot create a positive
relevance label.

Additional source-extraction and citation annotations are maintained in their own
files. Their sampling scope and review status should be considered separately
from the cases here.
