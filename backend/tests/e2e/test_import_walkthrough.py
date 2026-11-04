"""Browser walkthrough of the job list import: choose a file, confirm the column mapping in the
form, report, pool, field correction, a second upload with the stored mapping and status
discrepancies. Real app (`create_app` served by uvicorn) over a temporary data repository, the
built frontend in Chromium, fake models. The tests share one server and run in order, each
building on the data of the one before; run them as a set: `pytest -m e2e` after
`npm --prefix frontend run build`."""

import json
import re
import threading
import time
import zlib

import pytest
import uvicorn
from conftest import ScriptedModel, ToolScriptModel, write_json
from playwright.sync_api import Page, expect, sync_playwright
from test_triage_graph import POLICY_PACK, Harness, add_posting

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
PLACEHOLDER = "http://jobs.example.invalid"
LIST = (REPOSITORY_ROOT / "fixtures/import/stellenliste.md").read_text()
LABELS = ["Importiert", "Schon vorhanden", "Übersprungen (Status)",
          "Übersprungen, Link nicht mehr erreichbar", "Fehlgeschlagen"]
MAPPING = {"Bewerbung raus": "applied", "Absage": "done", "kein Interesse": "done",
           "Stelle weg": "skip", "offen": "open"}  # the choices confirmed, by the list's value
MANUAL_TITLE = "Handverlesene Stelle"
WAIT = 60_000  # ms; an import of ten entries takes a few seconds, the slow link one more
ABSAGE = re.compile(r"^absage$", re.IGNORECASE)  # the label of the value, in either spelling
BEWERBUNG = re.compile(r"^bewerbung raus$", re.IGNORECASE)


def fill_by_text(schema, prompt) -> dict:
    """A field-fill answer that differs per posting text: title, company and location carry the
    text's checksum, so no two postings share a value."""
    n = zlib.crc32(prompt.encode()) % 10_000
    return {"title": f"Stelle {n}", "company": f"Firma {n}", "location_raw": f"Ort {n}"}


def inert_agent(messages):
    """The chat agent of the app under test: the walkthrough never chats, so any call is a
    test bug. Passing it keeps `Settings()` (and with it `local.env`) out of reach."""
    raise AssertionError("the walkthrough must not call the chat agent")


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    """The temporary data repository root: profile, policy pack (without an import mapping:
    the walkthrough confirms it in the browser) and one open posting `manual` that no import
    touches (it has no origin and no URL)."""
    root = tmp_path_factory.mktemp("e2e") / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    add_posting(root, "manual", MANUAL_TITLE)
    return root


@pytest.fixture(scope="module")
def app_url(data_root, tmp_path_factory):
    """Base URL of the real app on a free localhost port, over `data_root` with fake models
    (`fill_by_text` for fields, a loop that ends at once for dead links). Fails with a build
    hint when `frontend/dist` is missing; stops the server afterwards."""
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")
    patch = pytest.MonkeyPatch()
    thread = None
    try:
        patch.setattr("jobadvaisor.intake.fetch.TIMEOUT_SECONDS", 1)  # the slow link fails fast
        harness = Harness(tmp_path_factory.mktemp("e2e-state"), data_root)
        app = create_app(
            Runs(harness.graph, harness.context),
            Intake(data_root, ScriptedModel(fill_by_text), ContentGuard(None, {}),
                   loop_model=ToolScriptModel(plan=[])),
            agent=inert_agent, frontend=FRONTEND)
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, "the app did not start"
        yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    finally:
        if thread:
            server.should_exit = True
            thread.join(10)
        patch.undo()


@pytest.fixture(scope="module")
def page(app_url):
    """One Chromium page for the whole walkthrough (its session storage carries the import ID
    from step to step, as in a real tab); default timeout 10 s."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(10_000)
        yield page
        browser.close()


@pytest.fixture(scope="module")
def first_list(site):
    """The fixture list with its placeholder host replaced by the local page server and one
    status value spelled in two ways: the rejected entry says `absage`, the unreachable one
    `Absage`. Both must count as one value in the form."""
    text = LIST.replace(PLACEHOLDER, site)
    assert text.count("| Absage | B | Per Mail |") == 1
    return text.replace("| Absage | B | Per Mail |", "| absage | B | Per Mail |")


def upload(page: Page, app_url: str, text: str) -> None:
    """Open "Anzeige hinzufügen", choose the source "Liste", choose `text` as the list file and
    press "Weiter": the mapping form is the next thing on the page."""
    page.goto(f"{app_url}/#/hinzufuegen")
    page.get_by_role("group", name="Quelle der Anzeige").get_by_role("button", name="Liste").click()
    page.get_by_label("Liste als Markdown-Datei").set_input_files(
        {"name": "stellenliste.md", "mimeType": "text/markdown", "buffer": text.encode()})
    page.get_by_role("button", name="Weiter").click()
    expect(page.get_by_role("heading", name="Spalten zuordnen")).to_be_visible()


def report(page: Page):
    """The finished report's section; it appears only once the import is done."""
    return page.get_by_role("region", name="Ergebnis")


def titles_by_url(root) -> dict[str, str]:
    """Title of each imported posting (those with an origin) by its first URL, read from the
    data repository on disk."""
    return {p.urls[0]: p.title for p in load(root).postings.values() if p.origin}


def status_of(root, url: str) -> str:
    """The application status of the stored posting whose first URL is `url`, read from the
    data repository on disk."""
    [posting] = [p for p in load(root).postings.values() if p.urls and p.urls[0] == url]
    return posting.status


def test_the_form_shows_the_tables_and_takes_the_mapping(page, app_url, first_list):
    upload(page, app_url, first_list)
    tables = page.get_by_role("list", name="Tabellen in der Datei").get_by_role("listitem")
    expect(tables).to_have_text(
        ["Offen · 4 Einträge", "Archiv · 6 Einträge", "Quellen · 2 Einträge"])
    expect(page.get_by_text("Es werden nur Tabellen importiert")).to_have_count(0)

    page.get_by_label("Status-Spalte").select_option("Stand")
    expect(page.get_by_text("Es werden nur Tabellen importiert, die die Status-Spalte haben.")
           ).to_be_visible()
    expect(tables).to_have_text([
        "Offen · 4 Einträge", "Archiv · 6 Einträge",
        "Quellen · 2 Einträge · wird nicht importiert (Spalte „Stand“ fehlt)"])
    # One choice per distinct value; `absage` and `Absage` share one.
    values = page.get_by_role("group", name="Werte der Spalte „Stand“")
    expect(values.get_by_role("combobox")).to_have_count(len(MAPPING))
    expect(values.get_by_text("neu")).to_have_count(0)  # nothing is stored yet: all would be new
    expect(values.get_by_label(ABSAGE)).to_have_count(1)
    page.get_by_label("Bewerbung raus", exact=True).select_option(label="beworben")
    values.get_by_label(ABSAGE).select_option(label="erledigt")
    page.get_by_label("kein Interesse", exact=True).select_option(label="erledigt")
    page.get_by_label("Stelle weg", exact=True).select_option(label="überspringen")
    page.get_by_label(re.compile("Einschätzung")).select_option("Priorität")
    for label, value in (("Bewerbung raus", "applied"), (ABSAGE, "done"),
                         ("kein Interesse", "done"), ("Stelle weg", "skip"), ("offen", "open")):
        expect(values.get_by_label(label, exact=isinstance(label, str))).to_have_value(value)
    expect(page.get_by_label("Status-Spalte")).to_have_value("Stand")
    expect(page.get_by_label(re.compile("Einschätzung"))).to_have_value("Priorität")


def test_the_import_reports_each_outcome(page, data_root, site):
    page.get_by_role("button", name="Import starten").click()
    expect(report(page)).to_be_visible(timeout=WAIT)
    expect(report(page).get_by_role("term")).to_have_text(LABELS)
    expect(report(page).get_by_role("definition")).to_have_text(["5", "0", "1", "2", "2"])
    expect(page.get_by_text("fehlgeschlagenen Einträge erneut")).to_be_visible()
    expect(page.get_by_role("heading", name="Status weicht ab")).to_have_count(0)

    left_out = page.get_by_role("region", name="Nicht importiert", exact=True).get_by_role(
        "listitem")
    expect(left_out).to_have_count(5)
    expect(left_out.nth(0)).to_contain_text("Wacholder Systems")
    expect(left_out.nth(0)).to_contain_text("Übersprungen (Status): Stelle weg")
    expect(left_out.nth(1)).to_contain_text(f"{site}/gone.html")
    expect(left_out.nth(1)).to_contain_text("Link nicht mehr erreichbar: HTTP 410")
    expect(left_out.nth(2)).to_contain_text(f"{site}/missing.html")
    expect(left_out.nth(2)).to_contain_text("Link nicht mehr erreichbar: HTTP 404")
    expect(left_out.nth(3)).to_contain_text(f"{site}/slow.html")
    expect(left_out.nth(3)).to_contain_text(re.compile(r"Fehlgeschlagen: browser failed"))
    expect(left_out.nth(4)).to_contain_text("Tannenhof Labs")
    expect(left_out.nth(4)).to_contain_text("Fehlgeschlagen: kein Link")

    sources = page.get_by_role("region", name="Nicht importierte Tabellen").get_by_role("listitem")
    expect(sources).to_have_text(["Quellen · 2 Einträge · Status-Spalte fehlt"])

    stored = json.loads((data_root / "policy-pack.json").read_text())["import_mapping"]
    assert stored["status_column"] == "Stand" and stored["assessment_column"] == "Priorität"
    assert {k.lower(): v for k, v in stored["values"].items()} == {
        k.lower(): v for k, v in MAPPING.items()}
    assert status_of(data_root, f"{site}/import-applied.html") == "applied"
    assert status_of(data_root, f"{site}/import-rejected.html") == "done"  # via `absage`
    assert status_of(data_root, f"{site}/static.html") == "open"


def test_the_pool_shows_the_imported_postings_by_origin(page, app_url, data_root):
    page.goto(f"{app_url}/#/pool")
    headings = page.get_by_role("heading", level=3)
    # Without the filter the open view lists the 3 open imports and the manual posting.
    expect(headings).to_have_count(4)
    expect(page.get_by_role("link", name=MANUAL_TITLE, exact=True)).to_be_visible()
    page.get_by_role("button", name="Herkunft").click()
    expected = sorted(titles_by_url(data_root).values())
    assert len(expected) == 5 and MANUAL_TITLE not in expected
    expect(headings).to_have_count(5)
    assert sorted(page.get_by_role("heading", level=3).all_inner_texts()) == expected
    expect(page.get_by_text(re.compile(r"^Importiert aus "))).to_have_count(5)


def test_a_corrected_company_persists(page, app_url, data_root, site):
    title = titles_by_url(data_root)[f"{site}/jsonld.html"]
    page.get_by_role("link", name=title, exact=True).click()
    expect(page.get_by_role("heading", level=1, name=title)).to_be_visible()
    page.get_by_role("button", name="Bearbeiten").click()
    page.get_by_label("Firma", exact=True).fill("Korrigierte Firma GmbH")
    page.get_by_role("button", name="Korrekturen speichern").click()
    expect(page.get_by_role("button", name="Korrekturen speichern")).to_have_count(0)
    expect(page.get_by_text("Korrigierte Firma GmbH, ")).to_be_visible()
    page.reload()
    expect(page.get_by_text("Korrigierte Firma GmbH, ")).to_be_visible()
    assert [p.company for p in load(data_root).postings.values()
            if p.urls and p.urls[0].endswith("/jsonld.html")] == ["Korrigierte Firma GmbH"]


def test_a_differing_status_is_decided_per_posting(page, app_url, data_root, site,
                                                   first_list):
    titles = titles_by_url(data_root)
    # `static` says `bewerbung raus` and comes first, so the form submits that spelling as the
    # key while the reachable `import-applied` entry keeps `Bewerbung raus`: a backend that
    # matches values case-sensitively maps that one to open and reports a third discrepancy.
    changed = (first_list
               .replace("| offen | A | Passt zum Profil |",
                        "| bewerbung raus | A | Passt zum Profil |")
               .replace("| absage | B | Per Mail |", "| offen | B | Per Mail |")
               .replace("| offen | C | Eher Forschung |", "| Interview | C | Eher Forschung |"))
    assert changed.count("| bewerbung raus |") == 1 and changed.count("| Bewerbung raus |") == 1
    assert changed.count("| absage |") == 0 and changed.count("| Interview |") == 1
    upload(page, app_url, changed)

    # The form is prefilled with the mapping stored by the first import.
    expect(page.get_by_label("Status-Spalte")).to_have_value("Stand")
    expect(page.get_by_label(re.compile("Einschätzung"))).to_have_value("Priorität")
    expect(page.get_by_label(BEWERBUNG)).to_have_count(1)
    expect(page.get_by_label(BEWERBUNG)).to_have_value("applied")
    expect(page.get_by_label(ABSAGE)).to_have_value("done")
    expect(page.get_by_label("Stelle weg", exact=True)).to_have_value("skip")
    # The new value is marked "neu" and open until chosen; the known ones are not marked.
    values = page.get_by_role("group", name="Werte der Spalte „Stand“")
    expect(values.get_by_text("neu")).to_have_count(1)
    row = values.locator("div").filter(has=page.get_by_label("Interview", exact=True))
    expect(row.get_by_text("neu")).to_be_visible()
    expect(page.get_by_label("Interview", exact=True)).to_have_value("open")
    expect(page.get_by_role("list", name="Tabellen in der Datei").get_by_role("listitem").last
           ).to_contain_text("wird nicht importiert")
    page.get_by_role("button", name="Import starten").click()
    expect(report(page).get_by_role("definition")).to_have_text(
        ["0", "5", "1", "2", "2"], timeout=WAIT)

    section = page.get_by_role("region", name="Status weicht ab")
    opened, kept = (section.get_by_role("listitem", name=titles[f"{site}/{page_name}.html"],
                                        exact=True)
                    for page_name in ("static", "import-rejected"))
    expect(section.get_by_role("listitem")).to_have_count(2)
    expect(opened).to_contain_text("App: offen · Liste: beworben")
    expect(kept).to_contain_text("App: erledigt · Liste: offen")

    opened.get_by_role("button", name="Aus Liste übernehmen").click()
    expect(opened.get_by_role("status")).to_have_text("Übernommen: beworben")
    kept.get_by_role("button", name="App behalten").click()
    expect(kept).to_contain_text("App-Status bleibt: erledigt")

    page.goto(f"{app_url}/#/pool")
    page.get_by_role("button", name="Beworben", exact=True).click()
    expect(page.get_by_role("link", name=titles[f"{site}/static.html"], exact=True)
           ).to_be_visible()
    expect(page.get_by_role("link", name=titles[f"{site}/import-rejected.html"],
                            exact=True)).to_have_count(0)
    page.get_by_role("button", name="Erledigt", exact=True).click()
    expect(page.get_by_role("link", name=titles[f"{site}/import-rejected.html"],
                            exact=True)).to_be_visible()


def test_a_click_on_a_lower_rows_title_opens_it(page, app_url):
    page.goto(f"{app_url}/#/pool")
    page.reload()  # as a user opens it: default filter, the first unrated row expanded
    links = page.get_by_role("heading", level=3).get_by_role("link")
    expect(links).to_have_count(3)  # the open postings: two imported, the manual one
    title = links.last.inner_text()
    links.last.click()
    expect(page.get_by_role("heading", level=1, name=title)).to_be_visible(timeout=3_000)
