"""Browser walkthrough of adding a link: the real app in Chromium over a temporary data repository,
the built frontend, fake models. The company lookup is served by a fake, since it would ask
https://127.0.0.1/; run it with `pytest -m e2e` after `npm --prefix frontend run build`."""

import threading
import time
from functools import partial

import pytest
import uvicorn
from conftest import ScriptedModel, ToolScriptModel, write_json
from playwright.sync_api import expect, sync_playwright
from test_company_lookup import FakeWeb, NoWait, ok, organization
from test_triage_graph import POLICY_PACK, Harness

from jobadvaisor.api.app import create_app
from jobadvaisor.data.loader import load
from jobadvaisor.data.models import company_id
from jobadvaisor.intake import postings as postings_module
from jobadvaisor.intake.company_facts import Reply, look_up
from jobadvaisor.intake.postings import Intake
from jobadvaisor.settings import REPOSITORY_ROOT
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.triage.runs import Runs

pytestmark = pytest.mark.e2e

FRONTEND = REPOSITORY_ROOT / "frontend/dist"
HOME = "https://127.0.0.1/"
FIELDS = {"title": "Backend Engineer", "company": "Harbor Freight Analytics GmbH",
          "location_raw": "Bremen"}


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("e2e-facts") / "data"
    write_json(root / "profile.json", {"schema_version": "1", "summary": "Developer"})
    write_json(root / "policy-pack.json", POLICY_PACK)
    return root


@pytest.fixture(scope="module")
def app_url(data_root, tmp_path_factory):
    if not (FRONTEND / "index.html").is_file():
        pytest.fail("frontend/dist is missing: run `npm --prefix frontend run build` first")
    harness = Harness(tmp_path_factory.mktemp("e2e-facts-state"), data_root)
    app = create_app(
        Runs(harness.graph, harness.context),
        Intake(data_root, ScriptedModel(lambda schema, prompt: FIELDS), ContentGuard(None, {}),
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
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(10_000)
        yield page
        browser.close()


def add_link(page, app_url, link):
    page.goto(f"{app_url}/#/hinzufuegen")
    page.get_by_label("Link zur Anzeige").fill(link)
    page.get_by_role("button", name="Hinzufügen", exact=True).click()


def test_a_link_added_in_the_browser_is_stored_with_its_employers_facts(
        page, app_url, data_root, site, monkeypatch):
    web = FakeWeb(**{HOME: ok(HOME, organization(foundingDate="2005-04-01",
                                                 numberOfEmployees=40))})
    monkeypatch.setattr(postings_module, "look_up", partial(look_up, fetch=web, throttle=NoWait()))
    add_link(page, app_url, f"{site}/static.html")
    expect(page.get_by_role("heading", name="Anzeige hinzugefügt")).to_be_visible()
    record = load(data_root).companies[company_id(FIELDS["company"])]
    assert (record.size_class, record.founded, record.source) == ("11-50", 2005, "website")
    assert web.requests == [HOME]


def test_a_second_link_of_the_same_employer_asks_nobody_again(
        page, app_url, data_root, site, monkeypatch):
    web = FakeWeb()
    monkeypatch.setattr(postings_module, "look_up", partial(look_up, fetch=web, throttle=NoWait()))
    add_link(page, app_url, f"{site}/jsonld.html")
    expect(page.get_by_role("heading", name="Anzeige hinzugefügt")).to_be_visible()
    assert web.requests == [] and len(load(data_root).postings) == 2


def test_a_failing_lookup_does_not_fail_the_link_and_leaves_no_record(
        page, app_url, data_root, site, monkeypatch):
    """The employer's site answers 500: the link is still added, nothing is stored for the
    company. (Its first posting's host is the only candidate, so the page asked is HOME.)"""
    web = FakeWeb(**{HOME: Reply(500, HOME, "")})
    monkeypatch.setattr(postings_module, "look_up", partial(look_up, fetch=web, throttle=NoWait()))
    (data_root / "companies" / f"{company_id(FIELDS['company'])}.json").unlink()
    for posting_id in sorted(load(data_root).postings)[1:]:  # leave one posting of the employer
        (data_root / "postings" / f"{posting_id}.json").unlink()
    add_link(page, app_url, f"{site}/import-applied.html")
    expect(page.get_by_role("heading", name="Anzeige hinzugefügt")).to_be_visible()
    assert web.requests == [HOME]
    assert load(data_root).companies == {} and len(load(data_root).postings) == 2
