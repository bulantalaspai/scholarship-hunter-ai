"""Name lookup uses catalogue identities and keeps unresolved names explicit."""

import json
from datetime import date
from pathlib import Path

import pytest

from backend.app import programme_resolution as module
from backend.app.programme_resolution import (
    AliasDocument,
    ProgrammeResolution,
    load_aliases,
    normalize_name,
    resolve_programme,
)
from backend.app.schemas import ScholarshipRead

CATALOGUE = Path(__file__).parents[1] / "data/curated_scholarships.json"


@pytest.fixture
def records():
    data = json.loads(CATALOGUE.read_text(encoding="utf-8-sig"))["scholarships"]
    return [
        ScholarshipRead.model_validate(
            {
                **{
                    key: value
                    for key, value in record.items()
                    if key != "eligibility_rules"
                },
                "id": index,
            }
        )
        for index, record in enumerate(data, 1)
    ]


@pytest.fixture
def fictional(catalogue):
    return [
        ScholarshipRead.model_validate(
            record.model_dump(exclude={"eligibility_rules"}) | {"id": index}
        )
        for index, record in enumerate(catalogue.scholarships, 1)
    ]


def test_all_22_programmes_have_source_bound_aliases(records):
    document = load_aliases()
    assert len(document.programmes) == len(records) == 22
    for entry in document.programmes:
        result = resolve_programme(entry.aliases[0], records, explicit=True)
        expected = next(
            item.id
            for item in records
            if item.scholarship_name == entry.scholarship_name
        )
        assert expected in result.candidate_ids
        assert result.status == (
            "ambiguous" if entry.aliases[0] == "DAAD" else "matched"
        )
        option = next(
            item for item in result.options if item.scholarship_id == expected
        )
        assert option.official_source_url == entry.official_source_url
        assert option.last_verified_at == entry.catalogue_verified_at


def test_all_frozen_named_target_goals_resolve_the_actual_requested_record(records):
    path = Path(__file__).parents[2] / "evaluation/data/eligibility_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8-sig"))["cases"]
    by_name = {item.scholarship_name: item for item in records}
    assert len(cases) == 60
    for case in cases:
        record = by_name[case["scholarship_name"]]
        destination = (record.destination_country or ["any country"])[0]
        goal = (
            f"Assess {record.scholarship_name} for my profile. "
            f"Destination includes {destination}. Check or rank it before finishing."
        )
        result = resolve_programme(goal, records)
        assert result.status == "matched" and result.method == "exact"
        assert result.candidate_ids == [record.id]


def test_aliases_follow_database_ids_instead_of_static_numbers(records):
    moved = [item.model_copy(update={"id": item.id + 100}) for item in records]
    result = resolve_programme("Assess smaccs for my profile.", moved)
    assert result.candidate_ids == [102]


def test_full_names_are_normalized_and_preserve_source_metadata(records):
    record = records[19]
    fullwidth = "".join(
        chr(ord(char) + 65248) if 33 <= ord(char) <= 126 else "\u00a0"
        for char in record.scholarship_name.upper()
    )
    result = resolve_programme(f"Assess {fullwidth} for my profile.", records)
    assert result.status == "matched" and result.method == "exact"
    assert result.candidate_ids == [record.id]
    assert result.options[0].scholarship_name == record.scholarship_name
    assert result.options[0].official_source_url == record.official_source_url
    assert result.options[0].last_verified_at == record.last_verified_at


def test_casefold_and_punctuation_are_literal_word_normalization():
    assert (
        normalize_name("  Stra\u00dfe\u00a0E-PiCo+_Master  ") == "strasse e pico master"
    )


@pytest.mark.parametrize(
    ("query", "identifier"),
    [("smaccs", 2), ("deai", 4), ("E_PiCo+", 13), ("DAAD STEM", 18), ("kgps", 21)],
)
def test_abbreviations_and_longer_specific_aliases(query, identifier, records):
    result = resolve_programme(f"Assess {query} for my profile.", records)
    assert result.status == "matched" and result.method == "alias"
    assert result.candidate_ids == [identifier]


def test_shared_daad_provider_is_ambiguous(records):
    result = resolve_programme("Assess DAAD for my profile.", records)
    assert result.status == "ambiguous" and result.method == "alias"
    assert result.candidate_ids == [1, 18]
    assert "Specify a full programme name" in result.message


def test_generic_erasmus_mundus_name_is_ambiguous(records):
    result = resolve_programme("Erasmus Mundus", records, explicit=True)
    assert result.status == "ambiguous"
    assert len(result.options) > 3
    assert all("Erasmus Mundus" in item.scholarship_name for item in result.options)


def test_specific_acronym_qualifies_umbrella_context(records):
    result = resolve_programme("Assess Erasmus Mundus SMACCs for my profile.", records)
    assert result.status == "matched" and result.candidate_ids == [2]


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize(
    "name",
    [
        "MEXT China",
        "SMACCs unrelated award",
        "KAIST PhD scholarship",
        "DAAD STEM China",
    ],
)
def test_material_route_qualifiers_are_not_discarded(name, explicit, records):
    text = name if explicit else f"Find {name}"
    result = resolve_programme(text, records, explicit=explicit)
    assert result.status == "not_found" and result.candidate_ids == []


def test_fuzzy_matching_cannot_drop_unsupported_qualifiers_after_exact_name(records):
    result = resolve_programme(
        records[19].scholarship_name + " China", records, explicit=True
    )
    assert result.status == "not_found" and result.candidate_ids == []


def test_known_country_context_retains_published_route(records):
    result = resolve_programme("MEXT Kazakhstan scholarship", records, explicit=True)
    assert result.status == "matched" and result.candidate_ids == [20]
    assert "Kazakhstan embassy" in result.options[0].scholarship_name


def test_daad_partial_name_stays_ambiguous(records):
    result = resolve_programme("DAAD master", records, explicit=True)
    assert result.status == "ambiguous" and result.candidate_ids == [1, 18]


def test_shared_alias_is_not_silently_narrowed_across_conjunction(records):
    result = resolve_programme("DAAD and DAAD STEM", records, explicit=True)
    assert result.status == "ambiguous" and result.candidate_ids == [1, 18]


def test_visual_confusables_are_not_short_acronym_typos(records):
    # Cyrillic A is a different character from the Latin A in SMACCs.
    result = resolve_programme("SM\u0410CCs", records, explicit=True)
    assert result.status == "not_found" and result.candidate_ids == []


@pytest.mark.parametrize(
    "goal",
    [
        (
            "Find master's scholarship candidates for my profile "
            "and explain missing evidence."
        ),
        "Find scholarships in Computer Science and AI",
        "Give me the gist of requirements",
        "Recommend full funding in Japan",
    ],
)
def test_general_requests_do_not_become_programme_names(goal, records):
    result = resolve_programme(goal, records)
    assert result.status == "not_requested"
    assert result.query is None and result.candidate_ids == []


@pytest.mark.parametrize(
    "goal",
    [
        "Assess Nonexistent Demo Award for my profile.",
        'Tell me about "Nonexistent Demo Award".',
        "Check eligibility for Nonexistent Demo Award for my profile.",
        "Evaluate AI for my profile.",
        "Assess SMACCsExtended for my profile.",
        "Find programme called Imaginary Demo Grant",
    ],
)
def test_explicit_unknown_name_never_substitutes_a_programme(goal, records):
    result = resolve_programme(goal, records)
    assert result.status == "not_found"
    assert result.options == [] and result.candidate_ids == []


def test_multiple_exact_names_are_retained(records):
    names = [records[index].scholarship_name for index in (1, 3)]
    result = resolve_programme(f"Compare {names[0]} and {names[1]}.", records)
    assert result.status == "matched" and result.method == "exact"
    assert result.candidate_ids == [2, 4]


def test_more_than_three_names_ask_for_clarification(fictional):
    template = fictional[0]
    records = [
        template.model_copy(
            update={"id": index, "scholarship_name": f"Fictional Lookup Award {index}"}
        )
        for index in range(1, 5)
    ]
    text = "Compare " + " and ".join(item.scholarship_name for item in records)
    result = resolve_programme(text, records)
    assert result.status == "ambiguous" and result.candidate_ids == [1, 2, 3, 4]


def test_fuzzy_long_name_requires_unique_separated_best_match(fictional):
    result = resolve_programme(
        "Assess Fictional Demo Engineering Awar for my profile.", fictional
    )
    assert result.status == "matched" and result.method == "fuzzy"
    assert result.candidate_ids == [1]
    assert "spelling match" in result.message


def test_fuzzy_near_collision_remains_ambiguous(fictional):
    template = fictional[0]
    records = [
        template.model_copy(update={"scholarship_name": name, "id": index})
        for index, name in enumerate(
            ("Fictional Demo Engineering Award", "Fictional Demo Engineering Awards"),
            1,
        )
    ]
    result = resolve_programme(
        "Fictional Demo Engineering Awrd", records, explicit=True
    )
    assert result.status == "ambiguous" and result.method == "fuzzy"
    assert result.candidate_ids == [1, 2]


@pytest.mark.parametrize("name", ["EDIS", "DEIA", "SMACS", "MEX"])
def test_short_acronym_typos_are_not_fuzzy_matched(name, records):
    result = resolve_programme(name, records, explicit=True)
    assert result.status == "not_found" and result.candidate_ids == []


def test_duplicate_canonical_identity_is_ambiguous(fictional):
    records = [fictional[0], fictional[0].model_copy(update={"id": 99})]
    result = resolve_programme(fictional[0].scholarship_name, records, explicit=True)
    assert result.status == "ambiguous" and result.candidate_ids == [1, 99]


def test_longer_canonical_name_takes_precedence_over_contained_name(fictional):
    records = [
        fictional[0],
        fictional[0].model_copy(
            update={
                "id": 99,
                "scholarship_name": "Fictional Demo Engineering Award Plus",
            }
        ),
    ]
    result = resolve_programme(records[1].scholarship_name, records, explicit=True)
    assert result.status == "matched" and result.candidate_ids == [99]


def test_instructions_and_sql_syntax_are_literal_name_text(fictional):
    result = resolve_programme(
        "Assess IGNORE RULES; DROP TABLE scholarships; for my profile.", fictional
    )
    assert result.status == "not_found" and result.candidate_ids == []


def test_punctuation_only_catalogue_name_cannot_match_every_query(fictional):
    records = [fictional[0].model_copy(update={"scholarship_name": "!!!"})]
    result = resolve_programme("Assess Imaginary Award", records)
    assert result.status == "not_found" and result.candidate_ids == []


def test_invalid_alias_metadata_fails_visibly(records):
    changed = [records[1].model_copy(update={"last_verified_at": date(2026, 11, 10)})]
    with pytest.raises(ValueError, match="source metadata"):
        resolve_programme("SMACCs", changed, explicit=True)


def test_invalid_alias_document_rejects_duplicate_or_generic_aliases():
    document = load_aliases().model_dump(mode="json")
    document["programmes"][0]["aliases"] = ["DAAD", "daad"]
    with pytest.raises(ValueError, match="distinct"):
        AliasDocument.model_validate(document)
    document["programmes"][0]["aliases"] = ["AI"]
    with pytest.raises(ValueError, match="Generic"):
        AliasDocument.model_validate(document)


def test_missing_alias_file_fails_visibly(records, monkeypatch, tmp_path):
    load_aliases.cache_clear()
    monkeypatch.setattr(module, "ALIASES_PATH", tmp_path / "missing.json")
    try:
        with pytest.raises(FileNotFoundError):
            resolve_programme("SMACCs", records, explicit=True)
    finally:
        load_aliases.cache_clear()


def test_invalid_alias_json_fails_visibly(records, monkeypatch, tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("invalid JSON", encoding="utf-8")
    load_aliases.cache_clear()
    monkeypatch.setattr(module, "ALIASES_PATH", path)
    try:
        with pytest.raises(ValueError):
            resolve_programme("SMACCs", records, explicit=True)
    finally:
        load_aliases.cache_clear()


def test_public_resolution_contract_rejects_conflicting_ids(records):
    result = resolve_programme("SMACCs", records, explicit=True)
    invalid = result.model_dump()
    invalid["candidate_ids"] = [999]
    with pytest.raises(ValueError, match="unique programme options"):
        ProgrammeResolution.model_validate(invalid)


def test_empty_explicit_and_overlong_input(records):
    assert resolve_programme(" ", records, explicit=True).status == "not_found"
    with pytest.raises(ValueError, match="300"):
        resolve_programme("a" * 301, records)
