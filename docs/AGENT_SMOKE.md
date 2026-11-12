# Local agent smoke test

Executed on **2026-11-12** with Ollama **0.40.16**, the installed
**qwen3:4b-instruct**, and the unchanged two-record curated catalogue in a
temporary SQLite database. The application database was not accessed, and no
personal student information was used. Command:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.smoke_agent
```

Synthetic input: Kazakhstan, completed bachelor's, Computer Science, GPA 3.5/4,
IELTS 7, intended start 2027, fully funded preference. Goal:
“Find funded master's candidates related to my field.”

Result: **HTTP 200**, **2.18 seconds**, **3 model rounds**, **2 tool calls**.

| Round | Prompt tokens reported by Ollama | Model decision |
| --- | ---: | --- |
| 1 | 838 | `search_scholarships` |
| 2 | 962 | `check_eligibility` |
| 3 | 1,098 | Final selection: record 2 |

Actual execution trace:

```json
[
  {
    "step": 1,
    "name": "search_scholarships",
    "status": "ok",
    "arguments": {"field": "Computer Science", "funding_type": "fully_funded"},
    "summary": "Found 1 matching records; returned 1 candidates."
  },
  {
    "step": 2,
    "name": "check_eligibility",
    "status": "ok",
    "arguments": {"scholarship_id": 2},
    "summary": "Deterministic eligibility: needs_verification."
  }
]
```

Response excerpt (the actual endpoint also returned all requirement checks,
scope statuses, explanations, suggestions, warnings and ranking reasons):

```json
{
  "status": "needs_verification",
  "model": "qwen3:4b-instruct",
  "evaluated_on": "2026-11-12",
  "steps": 3,
  "tool_calls": 2,
  "recommendations": [{
    "assessment": {
      "scholarship_id": 2,
      "scholarship_name": "SMACCs Erasmus Mundus Joint Master (EMJM) Scholarships",
      "status": "needs_verification",
      "official_source_url": "https://www.smaccs.eu/practical/scholarships/",
      "last_verified_at": "2026-11-11",
      "rules_verified_at": null
    }
  }]
}
```

Nine conditions remained unknown, including complete rule evidence, prior-degree
rules, GPA, language conditions, funding availability, intake and opening status.
No eligibility or award was promised. The model chose not to fetch a page or call
the ranking tool in this run; these are available tools, not forced steps. Final
presentation still uses the deterministic ranking service. All four dispatch
paths are exercised with mocked model/network responses in automated tests.

An earlier live run exposed the model confusing nationality with destination:
three empty destination-filter searches produced an honest `no_matches`. The
tool descriptions now explicitly distinguish the two. Model search quality,
timing and chosen plan can vary; this smoke test does not establish the academic
evaluation targets in PROPOSAL.md or exhaustive catalogue coverage.
