"""Browser walkthrough of scoring: a pass that scores a rated posting without a score, a score from
a posting's page, a re-score from a pool row, the blocked button, the pool's score range at
desktop and phone width, and the pass button's variant menu (choosing starts nothing, the main
part rescores everything, a reload drops the choice, the split button fits a phone), and a pass
whose progress beside the pass button shows its counts until a cancel keeps the scores so far, and
the row of the pass button that keeps its layout in every running state.
Real app (`create_app` served by uvicorn) over a temporary data repository, the built frontend in
Chromium, fake models. The tests share one server and run in order, each building on the data of
the one before; run them as a set: `pytest -m e2e` after `npm --prefix frontend run build`."""

import threading
import time

import pytest
import uvicorn
from conftest import LABEL, ScriptedModel, ToolScriptModel, write_json
from playwright.sync_api import expect, sync_playwright
from test_triage_graph import POLICY_PACK, Harness, add_posting, judge_by_title

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.data.writer import read_scores
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
RATED = "Bewertete Stelle 8"  # the fake judge scores the first number of the title
FRESH = "Neue Stelle 6"
SALES = "Sales Manager 5"  # excluded by the policy pack's rule `no-sales`


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    """The temporary data repository: a posting the user rated before any score existed, a new
    one and an excluded one."""
    root = tmp_path_factory.mktemp("e2e-score") / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    add_posting(root, "rated", RATED)
    write_json(root / "labels/rated.json", LABEL)
    add_posting(root, "fresh", FRESH)
    add_posting(root, "sales", SALES)
    return root


@pytest.fixture(scope="module")
def harness(data_root, tmp_path_factory):
    """The triage harness the app runs on; a test swaps `harness.judge` to change the next score."""
    return Harness(tmp_path_factory.mktemp("e2e-score-state"), data_root)


@pytest.fixture(scope="module")
def app_url(data_root, harness):
    """Base URL of the real app on a free localhost port; fails with a build hint when
    `frontend/dist` is missing and stops the server afterwards."""
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")
    app = create_app(
        Runs(harness.graph, harness.context),
        Intake(data_root, ScriptedModel(lambda schema, prompt: {}), ContentGuard(None, {}),
               loop_model=ToolScriptModel(plan=[])),
        agent=lambda messages: pytest.fail("the walkthrough never chats"), frontend=FRONTEND)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the app did not start"
    yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    server.should_exit = True
    thread.join(10)


@pytest.fixture(scope="module")
def page(app_url):
    """One Chromium page for the whole walkthrough, in the Europe/Berlin time zone so the added
    date reads the same on every machine; default timeout 10 s."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(timezone_id="Europe/Berlin")
        page.set_default_timeout(10_000)
        yield page
        browser.close()


def stored_scores(root) -> dict[str, int]:
    """The score of each posting that has one, read from the data repository on disk."""
    scores, _ = read_scores(root)
    return {posting_id: score.score for posting_id, score in scores.items()}


def pool_row(page, title):
    """The pool row of the posting `title`."""
    return page.get_by_role("list", name="Anzeigen").get_by_role("listitem").filter(
        has=page.get_by_role("heading", name=title))


def test_a_pass_scores_a_rated_posting_without_a_score(page, app_url, data_root):
    page.goto(f"{app_url}/#/pool")
    expect(pool_row(page, RATED).get_by_text("noch kein Score")).to_be_visible()
    page.get_by_role("button", name="Anzeigen ohne Score scoren (2)").click()  # rated and fresh
    expect(pool_row(page, RATED).get_by_text("8", exact=True)).to_be_visible(timeout=60_000)
    assert stored_scores(data_root) == {"rated": 8, "fresh": 6}
    assert set(load(data_root).labels) == {"rated"}  # the pass kept the user's rating


def test_a_score_from_the_posting_page_lands_in_the_pool(page, app_url, data_root, harness):
    (data_root / "scores/fresh.json").unlink()  # the new posting has no score again
    harness.judge = ScriptedModel(lambda schema, prompt: {"score": 4, "reasoning": "Passt teils."})
    page.goto(f"{app_url}/#/anzeigen/fresh")
    score = page.get_by_role("region", name="Score")
    expect(score.get_by_text("Noch kein Score")).to_be_visible()
    score.get_by_role("button", name="Score berechnen").click()
    expect(score.get_by_text("Passt teils.")).to_be_visible()
    expect(score.get_by_role("button", name="Neu berechnen")).to_be_enabled()
    assert stored_scores(data_root)["fresh"] == 4
    page.goto(f"{app_url}/#/pool")
    expect(pool_row(page, FRESH).get_by_text("4", exact=True)).to_be_visible()


def test_a_re_score_from_a_pool_row_replaces_the_score(page, app_url, data_root, harness):
    harness.judge = ScriptedModel(lambda schema, prompt: {"score": 9, "reasoning": "Doch besser."})
    page.goto(f"{app_url}/#/pool")
    row = pool_row(page, FRESH)
    row.get_by_role("button", name="Neu berechnen").click()
    expect(row.get_by_text("9", exact=True)).to_be_visible()
    assert stored_scores(data_root)["fresh"] == 9


def test_the_added_date_shows_in_the_browsers_time_zone_in_the_pool_and_on_the_posting_page(
        page, app_url):
    """The fixture's `added_at` is 09:00 UTC; the page is in Europe/Berlin, so it reads 10:00."""
    added = "Hinzugefügt 05.01.2026, 10:00"
    page.goto(f"{app_url}/#/pool")
    expect(pool_row(page, RATED).get_by_text(added)).to_be_visible()
    page.goto(f"{app_url}/#/anzeigen/rated")
    expect(page.get_by_role("heading", level=1, name=RATED)).to_be_visible()
    # a role query skips the pool, which stays in the DOM but hidden
    expect(page.get_by_role("time").filter(has_text=added)).to_be_visible()


def test_an_excluded_posting_has_a_disabled_button_with_its_reason(page, app_url, data_root):
    page.goto(f"{app_url}/#/pool")
    row = pool_row(page, SALES)
    expect(row.get_by_role("button", name="Score berechnen")).to_be_disabled()
    row.get_by_role("button", name="Warum nicht verfügbar?").focus()
    expect(row.get_by_role("tooltip")).to_contain_text("Eine Ausschlussregel greift: no-sales")
    assert "sales" not in stored_scores(data_root)


def test_the_score_range_narrows_the_pool_and_resets_at_desktop_and_phone_width(
        page, app_url, data_root):
    """Without a score file `fresh` is unscored again: "ohne Score" lists only it, 0 to 0 lists
    nothing, "Filter zurücksetzen" lists the open postings; the controls fit a 390 px page."""
    (data_root / "scores/fresh.json").unlink()
    page.goto(f"{app_url}/#/pool")
    page.reload()
    von = page.get_by_role("combobox", name="von", exact=True)
    bis = page.get_by_role("combobox", name="bis", exact=True)
    expect(pool_row(page, RATED)).to_be_visible()
    try:
        bis.select_option(label="ohne Score")
        expect(pool_row(page, FRESH)).to_be_visible()
        expect(pool_row(page, RATED)).to_have_count(0)
        expect(pool_row(page, SALES)).to_have_count(0)  # excluded, not unscored
        von.select_option(label="0")
        bis.select_option(label="0")
        expect(page.get_by_text("Keine Anzeige passt zu diesem Filter")).to_be_visible()
        page.get_by_role("button", name="Filter zurücksetzen").click()
        for title in (RATED, FRESH, SALES):
            expect(pool_row(page, title)).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        bis.select_option(label="ohne Score")
        expect(pool_row(page, FRESH)).to_be_visible()
        expect(pool_row(page, RATED)).to_have_count(0)
        for control in (von, bis, page.get_by_role("combobox", name="Sortierung")):
            expect(control).to_be_in_viewport()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    finally:  # later tests share the page: desktop width and the full range again
        page.set_viewport_size({"width": 1280, "height": 720})
        von.select_option(label="ohne Score")
        bis.select_option(label="10")


def test_choosing_the_all_variant_starts_nothing_and_its_main_part_rescores_everything(
        page, app_url, data_root, harness):
    """Entry state: `rated` has the score 8, `fresh` has none, `sales` is excluded. Choosing "Alle
    Anzeigen neu scoren" only switches the main part; pressing it replaces both scores with the
    judge's fixed 7 and leaves the excluded one alone; the choice does not outlive a pass or a
    reload. Leaves `rated` at 7 and `fresh` without a score, also when an assertion fails;
    `harness.judge` stays fixed at 7 for any later test."""
    harness.judge = ScriptedModel(lambda schema, prompt: {"score": 7, "reasoning": "Fest."})
    pass_requests = []

    def note_pass_request(request):
        """Remember each `POST /pool/passes` the page sends."""
        if request.method == "POST" and "/pool/passes" in request.url:
            pass_requests.append(request)

    page.on("request", note_pass_request)
    try:
        page.goto(f"{app_url}/#/pool")
        before = page.get_by_role("button", name="Anzeigen ohne Score scoren (1)")
        expect(before).to_be_enabled()
        width = before.bounding_box()["width"]
        page.get_by_role("button", name="Andere Variante wählen").click()
        page.get_by_role("menuitemradio", name="Alle Anzeigen neu scoren (2)").click()
        main = page.get_by_role("button", name="Alle Anzeigen neu scoren (2)")
        expect(main).to_be_enabled()
        assert main.bounding_box()["width"] == width  # the label change keeps the button's size
        expect(page.get_by_role("menu")).to_have_count(0)
        assert pass_requests == [] and harness.judge.calls == []  # choosing started nothing
        assert stored_scores(data_root) == {"rated": 8}
        expect(page.get_by_text("Scoren läuft")).to_have_count(0)
        main.click()
        expect(pool_row(page, RATED).get_by_text("7", exact=True)).to_be_visible(timeout=60_000)
        expect(pool_row(page, FRESH).get_by_text("7", exact=True)).to_be_visible()
        assert stored_scores(data_root) == {"rated": 7, "fresh": 7}  # `sales` is excluded
        assert len(pass_requests) == 1
        # the pass ended: the choice is dropped and no posting lacks a score
        expect(page.get_by_role("button", name="Anzeigen ohne Score scoren (0)")).to_be_disabled()
        page.get_by_role("button", name="Andere Variante wählen").click()
        page.get_by_role("menuitemradio", name="Alle Anzeigen neu scoren (2)").click()
        expect(page.get_by_role("button", name="Alle Anzeigen neu scoren (2)")).to_be_enabled()
        page.reload()
        expect(page.get_by_role("button", name="Anzeigen ohne Score scoren (0)")).to_be_disabled()
        expect(page.get_by_role("button", name="Alle Anzeigen neu scoren (2)")).to_have_count(0)
        assert len(pass_requests) == 1  # the reload and the second choice started nothing
    finally:  # the phone test after this one expects `fresh` unscored
        page.remove_listener("request", note_pass_request)
        (data_root / "scores/fresh.json").unlink(missing_ok=True)


def test_the_split_button_and_its_menu_fit_a_phone(page, app_url):
    """At 390 px the main part, the trigger and the open menu stay in the viewport and the page
    does not scroll sideways, with the longest main part ("Alle Anzeigen neu scoren")."""
    fits = "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        page.goto(f"{app_url}/#/pool")
        page.reload()
        trigger = page.get_by_role("button", name="Andere Variante wählen")
        main = page.get_by_role("button", name="Anzeigen ohne Score scoren (1)")
        expect(main).to_be_in_viewport()
        expect(trigger).to_be_in_viewport()
        assert page.evaluate(fits)
        trigger.click()
        menu = page.get_by_role("menu", name="Variante")
        expect(menu).to_be_in_viewport(ratio=1)
        assert page.evaluate(fits)
        menu.get_by_role("menuitemradio", name="Alle Anzeigen neu scoren (2)").click()
        expect(page.get_by_role("button", name="Alle Anzeigen neu scoren (2)")).to_be_in_viewport(
            ratio=1)
        expect(trigger).to_be_in_viewport(ratio=1)
        assert page.evaluate(fits)
    finally:  # later tests share the page: desktop width again
        page.set_viewport_size({"width": 1280, "height": 720})


def test_a_pass_shows_its_progress_and_a_cancel_keeps_the_scores_so_far(
        page, app_url, data_root, harness):
    """Entry state: `rated` has a score, `fresh` and three new postings have none, `sales` is
    excluded. The scripted judge waits for the test, so nothing races the 1 s poll: the progress
    shows scoring at 0 of 4, then 1 of 4. The cancel lands while the second posting is scored: the
    button reads "Wird beendet…", the notice reports 2 new scores, and only those two show a
    score in the ranking. Leaves the other two postings unscored."""
    # scores of 6 and more: the rating keys 1 to 5 sit in each row as text too
    titles = {"c1": "Weitere Stelle 8", "c2": "Weitere Stelle 9", "c3": "Weitere Stelle 10"}
    for posting_id, title in titles.items():
        add_posting(data_root, posting_id, title)
    titles["fresh"] = FRESH
    before = stored_scores(data_root)
    entered, permits = threading.Semaphore(0), threading.Semaphore(0)

    def judge(schema, prompt):
        """Announce each scoring call, then wait for one permit from the test."""
        entered.release()
        assert permits.acquire(timeout=10), "no permit for the judge"
        return judge_by_title(schema, prompt)

    harness.judge = ScriptedModel(judge)
    try:
        page.goto(f"{app_url}/#/pool")
        page.reload()
        page.get_by_role("button", name="Anzeigen ohne Score scoren (4)").click()
        progress = page.get_by_role("region", name="Stand des Scorens")
        assert entered.acquire(timeout=10)  # the first posting is being scored
        expect(progress.get_by_text("Scoren läuft: 0 von 4", exact=True)).to_be_visible()
        assert "Merkmale" not in progress.inner_text()  # a pass reads no features
        permits.release()
        assert entered.acquire(timeout=10)  # the second posting is being scored
        expect(progress.get_by_text("Scoren läuft: 1 von 4", exact=True)).to_be_visible()
        cancel = page.get_by_role("button", name="Scoren abbrechen")
        expect(cancel).not_to_have_attribute("aria-disabled", "true")  # the 1 s swap guard is over
        cancel.click()
        expect(progress.get_by_text("Wird nach der aktuellen Anzeige beendet.")).to_be_visible()
        stopping = page.get_by_role("button", name="Wird beendet…")
        expect(stopping).to_have_attribute("aria-disabled", "true")
        expect(stopping).to_be_focused()  # a second Enter must not fall through to the pool's keys
        permits.release()  # the second posting ends; the check before the third stops the pass
        expect(page.get_by_text(
            "Das Scoren wurde abgebrochen. 2 Anzeigen haben einen neuen Score.")).to_be_visible()
        expect(progress).to_have_count(0)
        assert len(harness.judge.calls) == 2  # the third posting was never judged
        new = {posting_id: score for posting_id, score in stored_scores(data_root).items()
               if posting_id not in before}
        assert len(new) == 2, new
        for posting_id, title in titles.items():
            row = pool_row(page, title)
            if posting_id in new:
                expect(row.get_by_text(str(new[posting_id]), exact=True)).to_be_visible()
            else:
                expect(row.get_by_text("noch kein Score")).to_be_visible()
        expect(page.get_by_role("button", name="Anzeigen ohne Score scoren (2)")).to_be_enabled()
    finally:  # a failed assertion must not leave the pass thread waiting
        permits.release(4)


ROW_WIDTHS = (360, 390, 640, 768, 1024, 1280)
# Run in the page with the progress block as `el`: the elements whose text overflows their own box.
OVERFLOWING = """(el, where) => [...el.querySelectorAll('*')]
    .filter((node) => node.scrollWidth > node.clientWidth + 1
        || node.scrollHeight > node.clientHeight + 1)
    .map((node) => `${where}: ${node.tagName} ${node.textContent.slice(0, 40)}`)"""


def running_pass(phase, score=None, cancel_requested=False):
    """The body of `GET /pool/passes/<id>` for a pass that computes, with `score` as a
    `(done, total)` pair."""
    return {"pass_id": "ps-row", "status": "running", "started_at": None, "error": None,
            "progress": {"phase": phase, "score": score and {"done": score[0], "total": score[1]}},
            "cancel_requested": cancel_requested, "scored": 0, "unscreened": []}


def test_the_row_of_the_pass_button_keeps_its_layout_in_every_running_state(page, app_url):
    """The pass endpoint is stubbed, one answer per state: checking, scoring with the longest
    realistic counts, after a cancel request and storing. Each state is waited for by its text, then
    the row of the pass button is measured at 360 to 1280 px wide. A width must give one row height
    and one x position and width for the progress block and the correction counter in all four
    states, and the cancel button must be as wide as the split button measured while idle (spec:
    Same size in every phase)."""
    states = {
        "checking": (running_pass("checking"), "Scoren läuft: Anzeigen prüfen…"),
        "scoring": (running_pass("scoring", (120, 179)), "Scoren läuft: 120 von 179"),
        "cancel requested": (running_pass("scoring", (120, 179), True),
                             "Wird nach der aktuellen Anzeige beendet."),
        "storing": (running_pass("storing", (179, 179)), "Scores werden gespeichert"),
    }
    current = {}
    page.route("**/pool/passes/ps-row", lambda route: route.fulfill(json=current["body"]))
    split = page.locator("[role=group][aria-label=Scoren]")
    cancel = page.locator("button[aria-describedby=cancel-why]")
    counter = page.get_by_text("Korrekturen seit dem letzten Neu-Scoren")
    idle_split: dict[int, float] = {}
    layout: dict[int, dict[str, tuple]] = {width: {} for width in ROW_WIDTHS}
    overflowing: list[str] = []
    try:
        page.goto(f"{app_url}/#/pool")
        page.reload()
        expect(split).to_be_visible()
        for width in ROW_WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            idle_split[width] = split.bounding_box()["width"]
        page.evaluate("sessionStorage.setItem('jobadvaisor.pool-pass', 'ps-row')")
        current["body"] = states["checking"][0]
        page.reload()
        progress = page.get_by_role("region", name="Stand des Scorens")
        row = progress.locator("xpath=..")
        for state, (body, text) in states.items():
            current["body"] = body
            expect(progress.get_by_text(text, exact=True)).to_be_visible(timeout=15_000)
            for width in ROW_WIDTHS:
                page.set_viewport_size({"width": width, "height": 900})
                block, count = progress.bounding_box(), counter.bounding_box()
                layout[width][state] = (
                    row.bounding_box()["height"], block["x"], block["width"], count["x"],
                    cancel.bounding_box()["width"])
                overflowing += progress.evaluate(OVERFLOWING, f"{width} px, {state}")
    finally:  # later tests share the page: desktop width, no stored pass
        page.unroute("**/pool/passes/ps-row")
        page.evaluate("sessionStorage.removeItem('jobadvaisor.pool-pass')")
        page.set_viewport_size({"width": 1280, "height": 720})
    table = "\n".join(
        f"{width} px (split {idle_split[width]}): {by_state}" for width, by_state in layout.items())
    print("\n" + table)  # (row height, block x, block width, counter x, cancel width) per state
    for width, by_state in layout.items():
        measured = list(by_state.values())
        assert len({values[:4] for values in measured}) == 1, table
        assert {values[4] for values in measured} == {idle_split[width]}, table
    assert overflowing == [], overflowing  # a fixed box that clips or spills its text is no fix
