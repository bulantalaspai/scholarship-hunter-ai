# Curated catalogue provenance

The original two records in `curated_scholarships.json` were checked against official
programme pages on **2026-11-11**. This is a small starting catalogue, not an
exhaustive list or a statement that applications are open. Recheck the linked
terms before relying on funding, conditions, or dates.

| Record | Official evidence | Interpretation |
| --- | --- | --- |
| DAAD: Study Scholarships – Master Studies for All Academic Disciplines | [DAAD programme entry](https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200) | German master's funding; stipend confirmed, tuition excluded. Partial funding. Nationality-specific eligibility and deadline remain unknown. |
| SMACCs EMJM scholarship | [Funding](https://www.smaccs.eu/practical/scholarships/), [admission](https://www.smaccs.eu/admissions/admission-criteria/), [deadlines](https://www.smaccs.eu/admissions/deadlines/), [programme](https://www.smaccs.eu/) | Tuition exemption plus living support justify the full-funding classification. The deadline page supplies the 2027–2029 edition's scholarship deadline; English alternatives/exemptions and international mobility must be retained. |

The listed SMACCs fields summarize documented entry backgrounds, not an
exhaustive taxonomy. `Worldwide` is a published nationality scope, not a country
code. DAAD's broad subject description is not converted into an invented list.
Missing GPA, IELTS, nationality, or deadline information remains `null`.

Funding labels describe the award's published support, not a guarantee that every
student receives it or that every personal expense is reimbursed. The importer
checks data consistency, not source authenticity: a curator must review official
evidence before setting `data_kind` to `curated` or changing verification dates.

Fictional testing records live only under `backend/tests/fixtures/`, carry a
`fictional_demo` label, and are rejected by the application import command.

## Expansion verified on 2026-11-12

Twenty source-backed records were appended, bringing the catalogue to 22. The original two records and their verification dates were preserved. Admission conditions and award selection are kept separate in each record. Unknown, conditional and non-comparable criteria remain explicit. All facts use official programme, university or provider pages; secondary scholarship aggregators were not used as evidence.

See [catalogue_evidence.json](catalogue_evidence.json) for per-source claims and remaining gaps, and [QUALITY_REPORT.md](QUALITY_REPORT.md) for counts, exclusions and limitations. The links below are the new primary sources; supplemental admission, mobility and intake pages are recorded in the manifest and record notes.

| Source-backed scholarship record | Award classification | Primary official source |
| --- | --- | --- |
| EDISS Erasmus Mundus Scholarships - Engineering of Data-intensive Intelligent Software Systems | fully_funded | [Provider page](https://www.master-ediss.eu/scholarship/) |
| DEAI Full Scholarship - Data Engineering and Artificial Intelligence | fully_funded | [Provider page](https://deai.ulb.be/home/students/tuition-fees-scholarships/) |
| CYBERSURE Erasmus Mundus Scholarships - Cybersecurity and Assurance | fully_funded | [Provider page](https://www.cybersure-master.eu/scholarships-and-fees) |
| CyberMACS Erasmus Mundus Scholarships - Applied Cybersecurity | fully_funded | [Provider page](https://cybermacs.eu/scholarships/) |
| IMLEX Erasmus Mundus Scholarships - Imaging and Light in Extended Reality | fully_funded | [Provider page](https://www.imlex.org/fees-and-scholarships/) |
| DENSYS 2.0 Erasmus Mundus Scholarships - Decentralised Smart Energy Systems | fully_funded | [Provider page](https://densys.univ-lorraine.fr/fees-and-scholarships/) |
| EMIMEP European Master for Industry in Microwave Electronics and Photonics - Erasmus Mundus Scholarships | fully_funded | [Provider page](https://www.erasmus-mundus.emimep.eu/admission-applications/erasmus-scholarships/) |
| EMSSE European Master in Sustainable Systems Engineering - Erasmus Mundus Scholarships | fully_funded | [Provider page](https://emsse.eu/admission-and-scholarships/scholarships/) |
| CoDaS Communications Engineering and Data Science - Erasmus Mundus Scholarships | fully_funded | [Provider page](https://www.unite-codas-master.eu/scholarship.html) |
| AMASE Advanced Materials Science and Engineering - Full Erasmus Mundus Scholarships | fully_funded | [Provider page](https://www.eusmat.net/international-studies/master/amase/application/fees-and-scholarships/) |
| E-PiCo+ Electric Vehicle Propulsion and Control - Erasmus Mundus Scholarships | fully_funded | [Provider page](https://master-epico.ec-nantes.fr/english-version/admission/fees-scholarships-1) |
| EU-CORE European Master on Control of Renewable Energy Systems - Erasmus Mundus Scholarships | fully_funded | [Provider page](https://master-eu-core.ec-nantes.fr/admission/students/fees-scholarships) |
| JEMARO Japan-Europe Master on Advanced Robotics - Consortium Scholarships | partially_funded | [Provider page](https://jemaro.ec-nantes.fr/english-version/admission/jemaro-fees-and-scholarships) |
| IFRoS Intelligent Field Robotic Systems - Consortium Excellence Grants | partially_funded | [Provider page](https://ifrosmaster.org/ifros-applicants/fees-grants) |
| EMINENT Embedded Intelligence Nanosystems Engineering - Erasmus Mundus Scholarships | fully_funded | [Provider page](https://eminent-master.eu/scholarships/) |
| Study scholarships for STEM disciplines | partially_funded | [Provider page](https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=57742130) |
| Stipendium Hungaricum - master's scholarships (Kazakhstan route) | partially_funded | [Provider page](https://stipendiumhungaricum.hu/about/) |
| MEXT Research Students Scholarship - master's route (Kazakhstan embassy) | fully_funded | [Provider page](https://www.kz.emb-japan.go.jp/itpr_ru/11_000001_00641.html) |
| KAIST Global Presidential Scholarship (KGPS) - master's route | fully_funded | [Provider page](https://admission.kaist.ac.kr/intl-graduate/FinancialSupport/Scholarship/KAISTScholarship/) |
| GIST Scholarships - international master's students | partially_funded | [Provider page](https://www.gist.ac.kr/iadm/html/sub04/0401.html) |
