# Programme lookup aliases

The local alias registry covers the 22 catalogue identities. Each entry contains
its complete scholarship name, official source URL, catalogue verification date
and a derivation basis. Aliases use acronyms already present in the catalogue
names, recognizable name fragments and the recorded DAAD provider. These lookup
labels preserve the existing programme routes and eligibility evidence.
[Machine-readable registry](../backend/data/programme_aliases.json)

## Resolution rules

1. Unicode NFKC normalization and case folding precede word matching. Punctuation,
   underscores and whitespace become word boundaries. Visually similar letters
   from different alphabets retain their identities.
2. Complete catalogue names take precedence. The longest overlapping phrase wins.
   Up to three explicitly named programmes can be retained. A shared canonical
   name or a larger set of requested programmes requires clarification.
3. Aliases match complete words. Specific phrases such as `DAAD STEM` take
   precedence over the contained provider alias. `DAAD` alone offers both stored
   DAAD schemes. `Erasmus Mundus` offers the corresponding catalogue programmes.
   A specific acronym can qualify an umbrella phrase, such as
   `Erasmus Mundus SMACCs`. A conjunction preserves separate requested choices.
4. Additional name qualifiers must occur in the matched records' names, providers,
   degree levels, destinations or study fields, or belong to the documented
   generic query vocabulary in the resolver. For example, `MEXT Kazakhstan`
   identifies the stored embassy route. `MEXT China`, `KAIST PhD scholarship` and
   `SMACCs unrelated award` produce a no-match response. Funding-preference words
   stay separate from deterministic eligibility checks.
5. A previously unrecognized explicit name can receive a conservative spelling
   match when it has at least 12 normalized characters and three words.
   `SequenceMatcher` similarity must reach 0.90. The best different-programme
   competitor must be at least 0.08 behind. Close competitors produce ambiguity.
   An existing name followed by unsupported qualifiers stays unresolved.
6. Short acronym typos stay unresolved. Generic subject abbreviations `AI`, `CS`
   and award abbreviation `EMJM` are excluded from the registry. Programme ID
   mappings come from the current catalogue records.

The resolver recognizes explicit `Assess`, `Evaluate`, `Check eligibility for`,
`Tell me about`, `Show details for`, `Look up`, quoted names and `Find programme
called` requests. General discovery requests continue through catalogue matching.
The tool's `programme_name` argument supplies an explicit name directly.

## Alias inventory

| Lookup label | Catalogue identity or scope |
| --- | --- |
| DAAD | Both stored DAAD scholarships |
| DAAD Master Studies | Master Studies for All Academic Disciplines |
| DAAD STEM | Study scholarships for STEM disciplines |
| SMACCs | SMACCs EMJM scholarships |
| EDISS | Engineering of Data-intensive Intelligent Software Systems |
| DEAI | Data Engineering and Artificial Intelligence |
| CYBERSURE | Cybersecurity and Assurance |
| CyberMACS | Applied Cybersecurity |
| IMLEX | Imaging and Light in Extended Reality |
| DENSYS, DENSYS 2.0 | Decentralised Smart Energy Systems |
| EMIMEP | Industry in Microwave Electronics and Photonics |
| EMSSE | Sustainable Systems Engineering |
| CoDaS | Communications Engineering and Data Science |
| AMASE | Advanced Materials Science and Engineering |
| E-PiCo+, EPiCo+ | Electric Vehicle Propulsion and Control |
| EU-CORE | Control of Renewable Energy Systems |
| JEMARO | Japan-Europe Master on Advanced Robotics |
| IFRoS | Intelligent Field Robotic Systems |
| EMINENT | Embedded Intelligence Nanosystems Engineering |
| Stipendium Hungaricum | Stored Kazakhstan master's route |
| MEXT, MEXT Research Students | Stored Kazakhstan embassy master's route |
| KAIST, KGPS, KAIST KGPS | Global Presidential Scholarship master's route |
| GIST | International master's scholarships |
| Erasmus Mundus | Shared umbrella alias requiring a specific programme |

## Source maintenance and limits

The source dates remain the catalogue snapshot dates of 2026-11-11 and 2026-11-12.
This registry adds local name mappings using existing records. New requirements,
funding facts and source verification dates require the existing curation process.
New aliases should include their canonical identity and source basis. A changed
source URL or an alias date newer than the record causes a visible validation
failure. Missing files, invalid JSON, duplicate normalized aliases and generic
subject abbreviations also fail validation.

The resolver returns `not_requested`, `matched`, `ambiguous` or `not_found` with
official-source options and preserved verification dates. Fuzzy matches identify
their spelling interpretation in the response message. Human readers can inspect
the complete route before using its deterministic eligibility assessment.
