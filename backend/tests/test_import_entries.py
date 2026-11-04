import httpx
import pytest

from jobadvaisor.data.models import ImportMapping
from jobadvaisor.intake.entries import (
    mapped_status,
    parse_entries,
    parse_tables,
    preview,
    tables_left_out,
)
from jobadvaisor.settings import REPOSITORY_ROOT

HOST = "http://jobs.example.invalid"
FIXTURE = (REPOSITORY_ROOT / "fixtures/import/stellenliste.md").read_text()
MAPPING = ImportMapping(
    status_column="Stand", assessment_column="Priorität",
    values={"Bewerbung raus": "applied", "Absage": "done", "kein Interesse": "done",
            "Stelle weg": "skip"})
NO_MAPPING = ImportMapping()


def table(*rows: str, header="| Name | Link |", heading="## Liste") -> str:
    """A small list: `heading`, a header line and the given rows under a separator."""
    return "\n".join([heading, "", header, "|---|---|", *rows, ""])


def test_the_fixture_has_four_tables_three_with_a_link_column_and_one_without():
    tables = parse_tables(FIXTURE)

    assert [(t.name, t.columns[t.link], len(t.rows)) for t in tables] == [
        ("Offen", "Link", 4), ("Archiv", "Link", 6), ("Quellen", "Link", 2)]


def test_the_fixture_entries_with_the_mapping_leave_out_the_table_without_a_status_column():
    entries = parse_entries(FIXTURE, MAPPING)

    assert [(e.table, e.status, e.assessment) for e in entries] == [
        ("Offen", "offen", "A"), ("Offen", "offen", "B"), ("Offen", "offen", "C"),
        ("Offen", "Bewerbung raus", "A"), ("Archiv", "Absage", "B"),
        ("Archiv", "Stelle weg", "C"), ("Archiv", "kein Interesse", "C"),
        ("Archiv", "Absage", "B"), ("Archiv", "offen", "A"), ("Archiv", "offen", "C")]
    assert [e.url for e in entries[:4]] == [f"{HOST}/{page}.html" for page in (
        "static", "jsonld", "rendered", "import-applied")]
    assert entries[-1].url is None
    assert entries[5].row == "Wacholder Systems · DevOps Engineer · Stelle weg · C"


def test_the_tables_left_out_are_those_lacking_the_status_column_with_their_entry_counts():
    assert tables_left_out(FIXTURE, MAPPING) == [{"name": "Quellen", "entries": 2}]
    assert tables_left_out(FIXTURE, ImportMapping(status_column=" stand ")) == [
        {"name": "Quellen", "entries": 2}]
    absent = tables_left_out(FIXTURE, ImportMapping(status_column="Status"))
    assert [t["name"] for t in absent] == ["Offen", "Archiv", "Quellen"]


def test_no_table_is_left_out_without_a_status_column():
    assert tables_left_out(FIXTURE, NO_MAPPING) == []


def test_without_a_status_column_every_table_with_links_is_an_entry_table():
    entries = parse_entries(FIXTURE, NO_MAPPING)

    assert len(entries) == 12
    assert entries[-1].table == "Quellen"
    assert {e.status for e in entries} == {None}


def urls(text: str) -> list[str | None]:
    return [e.url for e in parse_entries(text, NO_MAPPING)]


def test_the_link_column_is_the_one_with_the_most_urls():
    text = table("| http://a.invalid/1 | http://b.invalid/1 |", "| no | http://b.invalid/2 |",
                 header="| A | B |")

    assert urls(text) == ["http://b.invalid/1", "http://b.invalid/2"]


def test_the_leftmost_column_wins_a_tie():
    text = table("| http://a.invalid/1 | no |", "| no | http://b.invalid/1 |", header="| A | B |")

    assert urls(text) == ["http://a.invalid/1", None]


def test_a_table_without_a_link_is_no_entry_table():
    assert parse_tables(table("| Anna | Berlin |")) == []


def test_a_link_is_resolved_from_markdown_link_and_angle_bracket_syntax():
    text = table("| a | [Stelle](http://x.invalid/b?a=1) |", "| b | <http://x.invalid/c> |",
                 "| c | siehe http://x.invalid/d bitte |")
    assert [e.url for e in parse_entries(text, NO_MAPPING)] == [
        "http://x.invalid/b?a=1", "http://x.invalid/c", "http://x.invalid/d"]


def test_the_table_name_is_the_nearest_heading_without_markup_else_tabelle():
    text = "# Alles\n\n### **Neue** `Treffer`\n\n| N | L |\n|---|---|\n| a | http://x.invalid/a |\n"
    assert parse_tables(text)[0].name == "Neue Treffer"
    assert parse_tables("| N | L |\n|---|---|\n| a | http://x.invalid/a |\n")[0].name == "Tabelle"


def test_a_row_shorter_than_its_header_and_blank_rows_are_handled():
    text = table("|  |  |", "| nur Name |", "| a | http://x.invalid/a |")

    entries = parse_entries(text, NO_MAPPING)

    assert [(e.row, e.url) for e in entries] == [("nur Name", None), ("a", "http://x.invalid/a")]


def test_column_names_and_values_match_trimmed_and_without_case():
    text = table("| a | http://x.invalid/a | ** Offen ** |", header="| N | L |  STAND  |")
    text = text.replace("|---|---|", "|---|---|---|")
    mapping = ImportMapping(status_column=" stand ", values={" OFFEN": "applied"})

    [entry] = parse_entries(text, mapping)

    assert entry.status == "Offen"
    assert mapped_status(mapping, entry.status) == "applied"


def test_an_unmapped_or_empty_value_is_open():
    assert mapped_status(MAPPING, "etwas Neues") == "open"
    assert mapped_status(MAPPING, None) == "open"
    assert mapped_status(MAPPING, "stelle WEG") == "skip"


def test_values_match_as_the_form_matches_them_so_sharp_s_is_not_ss():
    mapping = ImportMapping(status_column="Stand", values={"weiß nicht": "skip"})

    assert mapped_status(mapping, "WEISS NICHT") == "open"
    assert mapped_status(mapping, "Weiß Nicht") == "skip"


def test_a_table_with_a_status_column_filter_drops_tables_lacking_it_case_insensitively():
    mapping = ImportMapping(status_column="STAND")

    assert {e.table for e in parse_entries(FIXTURE, mapping)} == {"Offen", "Archiv"}


def test_the_preview_lists_tables_columns_counts_and_values_in_first_seen_order():
    result = preview(FIXTURE)

    assert result["tables"][0] == {
        "name": "Offen", "entries": 4,
        "columns": ["Link", "Unternehmen", "Position", "Stand", "Priorität", "Kommentar"]}
    assert [t["name"] for t in result["tables"]] == ["Offen", "Archiv", "Quellen"]
    assert result["values"]["Stand"] == [
        "offen", "Bewerbung raus", "Absage", "Stelle weg", "kein Interesse"]
    assert result["values"]["Priorität"] == ["A", "B", "C"]
    assert "Link" not in result["values"]


def test_the_preview_leaves_out_columns_with_more_than_30_distinct_values():
    rows = [f"| {n} | http://x.invalid/{n} | {n % 2} |" for n in range(31)]
    text = table(*rows, header="| Nummer | Link | Rest |").replace("|---|---|", "|---|---|---|")

    values = preview(text)["values"]

    assert "Nummer" not in values
    assert values["Rest"] == ["0", "1"]
    assert "Nummer" in preview(text.replace("| 30 |", "| 29 |"))["values"]


def test_the_gone_page_answers_410_and_the_slow_page_after_the_delay(site):
    assert httpx.get(f"{site}/gone.html").status_code == 410
    assert httpx.get(f"{site}/gone.html").content == b""
    with pytest.raises(httpx.TimeoutException):
        httpx.get(f"{site}/slow.html", timeout=0.3)
