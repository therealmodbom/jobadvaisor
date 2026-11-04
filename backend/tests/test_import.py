import json
import threading
import time

import pytest
from conftest import FakeStructuredModel, ToolScriptModel, write_json
from fastapi.testclient import TestClient
from test_intake_duplicates import FIELDS
from test_triage_graph import POLICY_PACK, Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import ImportMapping
from jobadvaisor.intake import imports as imports_module
from jobadvaisor.intake.entries import Entry
from jobadvaisor.intake.imports import ImportBusyError, Imports, import_entry
from jobadvaisor.intake.ladder import is_gone
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

PLACEHOLDER = "http://jobs.example.invalid"
FIXTURE = (REPOSITORY_ROOT / "fixtures/import/stellenliste.md").read_text()
MAPPING = {"status_column": "Stand", "assessment_column": "Priorität",
           "values": {"Bewerbung raus": "applied", "Absage": "done", "kein Interesse": "done",
                      "Stelle weg": "skip"}}
FRESH = {"imported": 5, "duplicate": 0, "skipped_status": 1, "skipped_gone": 2, "failed": 2}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr("jobadvaisor.intake.fetch.TIMEOUT_SECONDS", 1)
    root = tmp_path / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    harness = Harness(tmp_path, root)
    http = TestClient(create_app(
        Runs(harness.graph, harness.context),
        Intake(root, FakeStructuredModel(*[FIELDS] * 20), ContentGuard(None, {}),
               loop_model=ToolScriptModel(plan=[]))),  # a dead link ends the loop at once
        raise_server_exceptions=False)
    return http, root


def upload(http, content: str | bytes, mapping: dict | str = MAPPING, path="/imports"):
    """Post `content` as the list file, with `mapping` (a dict, or the raw form text)."""
    data = content.encode() if isinstance(content, str) else content
    return http.post(path, files={"file": ("liste.md", data, "text/markdown")},
                     data={"mapping": mapping if isinstance(mapping, str) else json.dumps(mapping)})


def fixture_list(site: str) -> str:
    return FIXTURE.replace(PLACEHOLDER, site)


def finished(http, import_id: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = http.get(f"/imports/{import_id}").json()
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("import did not finish")


def import_text(http, text: str, mapping: dict = MAPPING) -> dict:
    response = upload(http, text, mapping)
    assert response.status_code == 202, response.text
    return finished(http, response.json()["import_id"])


def run_import(http, site: str) -> dict:
    return import_text(http, fixture_list(site))


def stored_pack(root) -> dict:
    return json.loads((root / "policy-pack.json").read_text())


def test_a_fresh_import_counts_each_entry_and_marks_the_stored_postings(api, site):
    http, root = api
    state = run_import(http, site)
    assert state["status"] == "done" and state["error"] is None, state
    assert state["counts"] == FRESH
    assert state["total"] == state["done"] == 10 == sum(state["counts"].values())
    postings = load(root).postings.values()
    assert len(postings) == 5
    origins = sorted((p.origin.table, p.origin.fit, p.origin.status, p.status) for p in postings)
    assert origins == sorted([
        ("Offen", "A", "offen", "open"), ("Offen", "B", "offen", "open"),
        ("Offen", "C", "offen", "open"), ("Offen", "A", "Bewerbung raus", "applied"),
        ("Archiv", "B", "Absage", "done")])
    assert not list((root / "labels").glob("*"))  # the list rates nothing


def test_the_report_lists_the_entries_that_were_not_imported_in_list_order(api, site):
    http, _ = api
    state = run_import(http, site)
    assert set(state) == {"import_id", "status", "error", "total", "done", "counts",
                          "not_imported", "conflicts", "tables_left_out"}
    assert state["tables_left_out"] == [{"name": "Quellen", "entries": 2}]
    slow = state["not_imported"][3]  # the last attempt on the link is the browser's timeout
    assert slow["reason"].startswith("browser failed: ")
    slow["reason"] = "browser failed"
    assert state["not_imported"] == [
        {"row": "Wacholder Systems · DevOps Engineer · Stelle weg · C",
         "url": f"{site}/import-skipped.html", "outcome": "skipped_status",
         "reason": "Stelle weg"},
        {"row": "Eisvogel Analytics · Data Scientist · kein Interesse · C",
         "url": f"{site}/gone.html", "outcome": "skipped_gone", "reason": "HTTP 410"},
        {"row": "Birkenhain Digital · Frontend Engineer · Absage · B",
         "url": f"{site}/missing.html", "outcome": "skipped_gone", "reason": "HTTP 404"},
        {"row": "Mondscheibe Cloud · Site Reliability Engineer · offen · A",
         "url": f"{site}/slow.html", "outcome": "failed",
         "reason": "browser failed"},
        {"row": "Tannenhof Labs · QA Engineer · offen · C · Link fehlt noch",
         "url": None, "outcome": "failed", "reason": "kein Link"}]


def test_a_second_upload_imports_only_the_rest(api, site):
    http, root = api
    run_import(http, site)
    state = run_import(http, site)
    assert state["counts"] == {"imported": 0, "duplicate": 5, "skipped_status": 1,
                               "skipped_gone": 2, "failed": 2}
    assert len(state["not_imported"]) == 5
    assert len(load(root).postings) == 5


def test_the_preview_answers_tables_values_and_the_stored_mapping(api, site):
    http, root = api
    response = upload(http, fixture_list(site), path="/imports/preview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tables"] == [
        {"name": name, "entries": entries, "columns": columns}
        for name, entries, columns in [
            ("Offen", 4, ["Link", "Unternehmen", "Position", "Stand", "Priorität", "Kommentar"]),
            ("Archiv", 6, ["Link", "Unternehmen", "Position", "Stand", "Priorität", "Kommentar"]),
            ("Quellen", 2, ["Portal", "Link"])]]
    assert body["values"]["Stand"] == [
        "offen", "Bewerbung raus", "Absage", "Stelle weg", "kein Interesse"]
    assert body["values"]["Priorität"] == ["A", "B", "C"]
    assert "Link" not in body["values"]
    assert body["mapping"] is None
    assert "import_mapping" not in stored_pack(root)  # a preview stores nothing
    assert not (root / "postings").exists() or not list((root / "postings").glob("*"))
    run_import(http, site)
    assert upload(http, fixture_list(site), path="/imports/preview").json()["mapping"] == {
        **MAPPING, "values": MAPPING["values"]}


def test_the_preview_needs_no_mapping_and_rejects_a_file_that_is_not_utf8(api):
    http, _ = api
    bad = http.post("/imports/preview", files={"file": ("x.md", b"\xff\xfe\x00bad")})
    assert bad.status_code == 422 and bad.json()["error"] == "invalid upload"
    empty = http.post("/imports/preview", files={"file": ("x.md", b"# nothing\n")})
    assert empty.json() == {"tables": [], "values": {}, "mapping": None}


def test_the_mapping_is_stored_in_the_policy_pack_next_to_its_other_keys(api, site):
    http, root = api
    run_import(http, site)
    pack = stored_pack(root)
    assert pack["import_mapping"] == MAPPING
    assert {key: pack[key] for key in POLICY_PACK} == POLICY_PACK


@pytest.mark.parametrize("mapping", [
    "not json", "[]", '{"values": {"x": "maybe"}}', '{"status_column": 3}',
    '{"columns": "Stand"}'])
def test_an_invalid_mapping_is_refused_and_nothing_is_stored(api, site, mapping):
    http, root = api
    response = upload(http, fixture_list(site), mapping)
    assert response.status_code == 422 and response.json()["error"] == "invalid mapping"
    assert stored_pack(root) == POLICY_PACK


def test_an_upload_without_a_mapping_is_invalid(api):
    response = api[0].post("/imports", files={"file": ("x.md", b"# nothing\n")})
    assert response.status_code == 422


def test_without_a_status_column_every_table_with_links_is_imported_as_open(api, site):
    http, root = api
    state = import_text(http, fixture_list(site), {"values": {}})
    assert state["counts"]["skipped_status"] == 0
    assert state["total"] == 12  # the sources table counts too
    assert state["tables_left_out"] == []
    assert {p.status for p in load(root).postings.values()} == {"open"}


def test_a_stored_posting_gets_the_origin_and_keeps_its_status(api, site):
    http, root = api
    stored = http.post("/postings", data={"url": f"{site}/static.html"}).json()["posting_id"]
    assert http.patch(f"/postings/{stored}", json={"status": "applied"}).status_code == 200
    state = run_import(http, site)
    assert state["counts"]["imported"] == 4 and state["counts"]["duplicate"] == 1
    posting = load(root).postings[stored]
    assert posting.status == "applied"
    assert (posting.origin.table, posting.origin.fit, posting.origin.status) == (
        "Offen", "A", "offen")


def test_a_second_import_is_refused_while_one_computes_and_keeps_the_stored_mapping(
        api, site, monkeypatch):
    http, root = api
    release = threading.Event()
    monkeypatch.setattr(imports_module, "import_entry", lambda intake, entry, mapping:
                        release.wait(30) and ("imported", None, None))
    first = upload(http, fixture_list(site))
    assert first.status_code == 202
    try:
        second = upload(http, fixture_list(site), {"status_column": "Kommentar"})
        assert second.status_code == 409
        assert second.json()["error"] == "import in progress"
        assert first.json()["import_id"] in second.json()["detail"]
        assert stored_pack(root)["import_mapping"] == MAPPING
        assert http.get(f"/imports/{first.json()['import_id']}").json()["status"] == "running"
    finally:
        release.set()
    assert finished(http, first.json()["import_id"])["counts"]["imported"] == 10
    assert upload(http, "").status_code == 202  # free again


def intake_in(tmp_path) -> Intake:
    write_json(tmp_path / "policy-pack.json", POLICY_PACK)
    return Intake(tmp_path, FakeStructuredModel(), ContentGuard(None, {}))


def test_the_class_refuses_a_start_while_computing(tmp_path, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(imports_module, "import_entry", lambda intake, entry, mapping:
                        release.wait(30) and ("failed", None, "x"))
    imports = Imports(intake_in(tmp_path))
    first = imports.start([Entry("t", "r", None, None, None)], ImportMapping(), [])
    with pytest.raises(ImportBusyError, match=first):
        imports.start([], ImportMapping(), [])
    release.set()


def test_a_crashing_import_reports_the_exception_type_only(tmp_path, monkeypatch):
    def crash(intake, entry, mapping):
        raise RuntimeError("http://secret.example/job")

    monkeypatch.setattr(imports_module, "import_entry", crash)
    imports = Imports(intake_in(tmp_path))
    import_id = imports.start([Entry("t", "r", None, None, None)], ImportMapping(), [])
    while (state := imports.read(import_id))["status"] == "running":
        time.sleep(0.01)
    assert state["status"] == "failed" and state["error"] == "RuntimeError"
    assert "secret" not in json.dumps(state)


def test_a_list_without_entries_ends_with_total_zero(api):
    http, _ = api
    response = upload(http, "# Nothing here\n\nNo tables.\n")
    state = finished(http, response.json()["import_id"])
    assert (state["status"], state["total"], state["done"]) == ("done", 0, 0)
    assert state["not_imported"] == []


def test_a_byte_order_mark_is_ignored(api, site):
    http, _ = api
    table = (f"| Link | Stand |\n|---|---|\n| {site}/static.html | offen |\n").encode()
    response = upload(http, b"\xef\xbb\xbf" + table, {"status_column": "stand"})
    assert finished(http, response.json()["import_id"])["counts"]["imported"] == 1


def test_an_undecodable_upload_is_invalid(api):
    response = upload(api[0], b"\xff\xfe\x00bad")
    assert response.status_code == 422 and response.json()["error"] == "invalid upload"


def test_an_upload_without_a_file_is_invalid(api):
    assert api[0].post("/imports", data={"mapping": "{}"}).status_code == 422


def test_an_unknown_import_is_not_found(api):
    response = api[0].get("/imports/nope")
    assert response.status_code == 404
    assert response.json() == {"error": "not found", "detail": "no import nope"}


def attempt(url, outcome):
    return {"step": "plain", "url": url, "outcome": outcome}


@pytest.mark.parametrize("outcome", ["HTTP 404", "HTTP 410"])
def test_a_missing_page_is_gone(outcome):
    assert is_gone([attempt("http://a/x", outcome)], "http://a/x")


def test_another_address_or_failure_is_not_gone():
    assert not is_gone([attempt("http://a/redirect", "HTTP 404")], "http://a/x")
    assert not is_gone([attempt("http://a/x", "connection failed: ReadTimeout")], "http://a/x")
    assert not is_gone([attempt("http://a/x", "HTTP 500")], "http://a/x")


def test_an_entry_without_a_link_fails_with_the_reason_kein_link(tmp_path):
    entry = Entry("t", "r", None, "neu", None)
    assert import_entry(intake_in(tmp_path), entry, ImportMapping()) == (
        "failed", None, "kein Link")


def test_an_entry_whose_status_maps_to_skip_is_skipped_without_a_fetch(tmp_path):
    entry = Entry("t", "r", "http://unreachable.invalid/x", "stelle WEG", None)
    assert import_entry(intake_in(tmp_path), entry, ImportMapping(**MAPPING)) == (
        "skipped_status", None, "stelle WEG")


def test_an_unexpected_error_fails_the_entry_with_its_type_name_only(tmp_path, monkeypatch):
    def crash(intake, url, **_):
        raise RuntimeError("http://secret.example/x")

    monkeypatch.setattr(imports_module, "add_from_url", crash)
    entry = Entry("t", "r", "http://a.invalid/x", None, None)
    assert import_entry(intake_in(tmp_path), entry, ImportMapping()) == (
        "failed", None, "RuntimeError")


def test_a_validation_error_fails_the_entry_with_its_type_name_not_its_text(
        tmp_path, monkeypatch):
    def invalid(intake, url, **_):
        ImportMapping(values={"x": "nonsense"})  # raises pydantic's multi-line ValidationError

    monkeypatch.setattr(imports_module, "add_from_url", invalid)
    entry = Entry("t", "r", "http://a.invalid/x", None, None)
    assert import_entry(intake_in(tmp_path), entry, ImportMapping()) == (
        "failed", None, "ValidationError")


def list_with_status(site: str, url_path: str, status: str) -> str:
    """The fixture list with the status cell of the entry linking `url_path` replaced."""
    lines = []
    for line in fixture_list(site).splitlines(keepends=True):
        if line.startswith("|") and url_path in line:
            cells = line.split("|")
            cells[4] = f" {status} "
            line = "|".join(cells)
        lines.append(line)
    return "".join(lines)


def test_a_differing_status_is_named_and_the_app_status_stays(api, site):
    http, root = api
    stored = http.post("/postings", data={"url": f"{site}/static.html"}).json()["posting_id"]
    state = import_text(http, list_with_status(site, "/static.html", "Bewerbung raus"))
    assert state["counts"]["imported"] == 4 and state["counts"]["duplicate"] == 1
    posting = load(root).postings[stored]
    assert state["conflicts"] == [{"posting_id": stored, "title": posting.title,
                                   "company": posting.company, "status": "open",
                                   "list_status": "applied"}]
    assert posting.status == "open" and posting.origin.status == "Bewerbung raus"


def test_no_conflict_without_a_difference(api, site):
    http, _ = api
    http.post("/postings", data={"url": f"{site}/static.html"})
    state = run_import(http, site)  # the list says offen = open, the app says open
    assert state["counts"]["duplicate"] == 1 and state["conflicts"] == []


def test_no_conflict_for_an_empty_status_cell(api, site):
    http, _ = api
    stored = http.post("/postings", data={"url": f"{site}/static.html"}).json()["posting_id"]
    http.patch(f"/postings/{stored}", json={"status": "applied"})
    state = import_text(http, list_with_status(site, "/static.html", ""))
    assert state["counts"]["duplicate"] == 1 and state["conflicts"] == []


@pytest.mark.parametrize(("reason", "conflicts"), [("url", 1), ("text", 1), ("similar_text", 0)])
def test_only_a_url_or_exact_text_duplicate_can_conflict(api, site, monkeypatch, reason, conflicts):
    http, _ = api
    http.post("/postings", data={"url": f"{site}/static.html"})
    real = imports_module.add_from_url

    def add_with_reason(intake, url, **options):
        posting_id, posting, found, attempts = real(intake, url, **options)
        return posting_id, posting, found and reason, attempts  # only the stored one is a duplicate

    monkeypatch.setattr(imports_module, "add_from_url", add_with_reason)
    state = import_text(http, list_with_status(site, "/static.html", "Bewerbung raus"))
    assert state["counts"]["duplicate"] >= 1 and len(state["conflicts"]) == conflicts


def test_a_gone_link_is_skipped_without_looking_for_it_elsewhere(api, site, monkeypatch):
    def no_loop(*args, **kwargs):
        raise AssertionError("the intake loop ran on a gone link")

    monkeypatch.setattr("jobadvaisor.intake.postings.run_intake_loop", no_loop)
    state = import_text(api[0], f"| Link | Stand |\n|---|---|\n| {site}/gone.html | offen |\n")
    assert state["not_imported"][0]["outcome"] == "skipped_gone"
    assert state["not_imported"][0]["reason"] == "HTTP 410"


def found_elsewhere(monkeypatch, posting_id: str):
    """Make every entry's link lead to the stored `posting_id` as a duplicate by URL, as when
    the intake loop picks that posting's page for a link that could not be read."""
    def add(intake, url, **_):
        return posting_id, load(intake.root).postings[posting_id], "url", []

    monkeypatch.setattr(imports_module, "add_from_url", add)


def test_a_posting_found_through_another_link_keeps_its_mark_and_has_no_conflict(
        api, site, monkeypatch):
    http, root = api
    import_text(http, f"| Link | Stand |\n|---|---|\n| {site}/static.html | offen |\n")
    [(posting_id, before)] = load(root).postings.items()
    found_elsewhere(monkeypatch, posting_id)
    state = import_text(http, f"| Link | Stand |\n|---|---|\n| {site}/dead.html | Absage |\n")
    assert state["counts"]["duplicate"] == 1 and state["conflicts"] == []
    assert load(root).postings[posting_id].origin == before.origin


def test_a_posting_found_through_another_link_without_a_mark_gets_one(api, site, monkeypatch):
    http, root = api
    posting_id = http.post("/postings", data={"url": f"{site}/static.html"}).json()["posting_id"]
    found_elsewhere(monkeypatch, posting_id)
    import_text(http, f"| Link | Stand |\n|---|---|\n| {site}/dead.html | offen |\n")
    assert load(root).postings[posting_id].origin.status == "offen"


def test_a_new_posting_is_no_conflict(api, site):
    http, _ = api
    assert run_import(http, site)["conflicts"] == []


def test_a_conflict_is_dropped_once_the_status_matches_the_list(api, site):
    http, _ = api
    stored = http.post("/postings", data={"url": f"{site}/static.html"}).json()["posting_id"]
    state = import_text(http, list_with_status(site, "/static.html", "Bewerbung raus"))
    assert len(state["conflicts"]) == 1
    http.patch(f"/postings/{stored}", json={"status": "applied"})
    assert http.get(f"/imports/{state['import_id']}").json()["conflicts"] == []
