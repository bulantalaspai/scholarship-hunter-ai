# Curated catalogue provenance

The two records in `curated_scholarships.json` were checked against official
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
