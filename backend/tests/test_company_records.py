"""The company record: model constraints, ID rule, loading and writing (`data-repository` →
Company records)."""

import re

import pytest
from conftest import POSTING, write_json

from jobadvaisor.data.loader import DataRepositoryError, load
from jobadvaisor.data.models import POSTING_ID_PATTERN, Company, company_id
from jobadvaisor.data.writer import read_company, write_company

RECORD = {"schema_version": "1", "name": "Acme GmbH", "size_class": "51-200", "founded": 2019,
          "source": "linkedin", "source_url": "https://www.linkedin.com/company/acme",
          "fetched_at": "2026-10-29T10:00:00Z"}


def test_company_id_reads_as_the_slugged_name_and_ends_in_a_hash_of_it():
    assert re.fullmatch(r"mueller-soehne-gmbh-[0-9a-f]{10}", company_id("Müller & Söhne GmbH"))


def test_company_id_fits_the_posting_id_pattern_even_for_a_very_long_name():
    assert len(company_id("a" * 100)) == 64
    assert re.fullmatch(POSTING_ID_PATTERN, company_id("a" * 100))


def test_names_that_slug_alike_get_ids_of_their_own():
    assert len({company_id("A+B"), company_id("A B"), company_id("a-b")}) == 3
    assert company_id("a" * 100 + "x") != company_id("a" * 100 + "y")  # cut slugs still differ


def test_company_id_ignores_case_and_spacing_only():
    assert company_id("  example   CORP ") == company_id("Example Corp")


def test_a_name_without_usable_characters_has_no_id():
    assert company_id("!!!") == "" == company_id("   ")


def test_valid_record_loads(data_repository):
    write_json(data_repository / "companies/acme-gmbh.json", RECORD)
    repository = load(data_repository)
    assert repository.companies["acme-gmbh"].size_class == "51-200"
    assert repository.companies["acme-gmbh"].founded == 2019


def test_company_of_finds_the_record_by_the_postings_company_name(data_repository):
    write_json(data_repository / f"companies/{company_id('Example Corp')}.json",
               {**RECORD, "name": "Example Corp"})
    repository = load(data_repository)
    assert repository.company_of(repository.postings["p1"]).name == "Example Corp"


def test_company_of_a_company_without_a_record_is_none(data_repository):
    repository = load(data_repository)
    assert repository.company_of(repository.postings["p1"]) is None


def test_company_of_never_hands_one_employers_facts_to_another_with_a_similar_name(
        data_repository):
    write_json(data_repository / f"companies/{company_id('Example+Corp')}.json",
               {**RECORD, "name": "Example+Corp"})
    repository = load(data_repository)
    assert repository.company_of(repository.postings["p1"]) is None  # p1 is "Example Corp"


def test_company_of_ignores_case_and_spacing_in_the_postings_name(data_repository):
    write_json(data_repository / f"companies/{company_id('Example Corp')}.json", RECORD)
    repository = load(data_repository)
    write_json(data_repository / "postings/p3.json", {**POSTING, "company": "  EXAMPLE  corp"})
    assert load(data_repository).company_of(load(data_repository).postings["p3"]) is not None
    assert repository.company_of(repository.postings["p1"]) is not None


def test_repository_without_companies_loads_as_before(data_repository):
    assert load(data_repository).companies == {}


def test_record_entered_by_hand_loads(data_repository):
    write_json(data_repository / "companies/acme-gmbh.json",
               {**RECORD, "source": "manual", "source_url": "https://www.example.com/"})
    assert load(data_repository).companies["acme-gmbh"].source == "manual"


def test_record_without_facts_loads(data_repository):
    bare = {key: value for key, value in RECORD.items() if key not in ("size_class", "founded")}
    write_json(data_repository / "companies/acme-gmbh.json", bare)
    company = load(data_repository).companies["acme-gmbh"]
    assert company.size_class is None
    assert company.founded is None


@pytest.mark.parametrize("override, constraint", [
    ({"founded": 19}, "founded"),
    ({"founded": 20190}, "founded"),
    ({"size_class": "many"}, "size_class"),
    ({"size_class": "51-200 employees"}, "size_class"),
])
def test_invalid_fact_fails_naming_file_and_field(data_repository, override, constraint):
    write_json(data_repository / "companies/acme-gmbh.json", {**RECORD, **override})
    with pytest.raises(DataRepositoryError) as error:
        load(data_repository)
    assert f"companies/acme-gmbh.json: {constraint}:" in str(error.value)


@pytest.mark.parametrize("size_class", ["1-10", "11-50", "1,001-5,000", "10,001+"])
def test_size_class_accepts_linkedin_ranges(size_class):
    assert Company(**{**RECORD, "size_class": size_class}).size_class == size_class


def test_write_company_round_trips_and_leaves_no_unset_fields(tmp_path):
    company = Company(**{key: value for key, value in RECORD.items() if key != "size_class"})
    path = write_company(tmp_path, "acme-gmbh", company)
    assert path == tmp_path / "companies/acme-gmbh.json"
    assert "size_class" not in path.read_text()
    assert read_company(tmp_path, "acme-gmbh") == company


def test_read_company_of_an_unknown_company_is_none(tmp_path):
    assert read_company(tmp_path, "nobody") is None


def test_write_company_rejects_an_unsafe_id(tmp_path):
    with pytest.raises(ValueError, match="must match"):
        write_company(tmp_path, "../x", Company(**RECORD))
