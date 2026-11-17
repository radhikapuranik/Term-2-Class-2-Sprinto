"""Click-through checks of Outreach Desk in a real (headless) browser, on seeded data with mocks. No network, no real sends."""
import socket
import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from outreach import api, db  # noqa: E402
from tests.ui_seed import seed  # noqa: E402

PAGES = ["/", "/companies", "/companies/ledgerly.test", "/review", "/quality", "/icp", "/runs", "/about", "/missing"]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("TEST_RECIPIENT", "me@example.com")
    path = tmp_path_factory.mktemp("ui") / "ui.db"
    seed(db.connect(path))
    api.app.state.db_path = path
    sent = []
    mp.setattr("outreach.send.send", lambda to, subject, text, html, headers=None: sent.append((to, subject)) or "re_test")

    def fake_qualify(d, icp, con, llm, fetcher, refresh=False):
        for page in ("home", "careers"):
            db.log(con, d, f"fetched {page} https://{d}/{page} via http: ok ")
            time.sleep(0.05)
        db.save_company(con, d, d.split(".")[0].title(), {}, "NO-GO", ["Company type: rejects"], 0.2, "auto-reject")
        return db.cached_company(con, d) | {"cached": False}
    mp.setattr(api, "qualify_company", fake_qualify)
    mp.setattr("outreach.llm.Gemini.__init__", lambda self, con, model=None: setattr(self, "model", "fake"))

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield {"url": f"http://127.0.0.1:{port}", "sent": sent, "db": path}
    srv.should_exit = True
    del api.app.state.db_path
    mp.undo()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # browser binaries not installed
            pytest.skip(f"Chromium not available: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script("window.__UNDO_MS = 900; try { localStorage.setItem('od-dry','0') } catch (e) {}")
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    yield pg
    ctx.close()
    assert not errors, errors


def test_test_mode_banner_on_every_page(server, page):
    for path in PAGES:
        page.goto(server["url"] + path)
        page.wait_for_selector("#view > *:not([aria-busy])")
        assert page.locator(".ribbon").is_visible() and "test mode" in page.locator(".ribbon").inner_text().lower()
    assert page.locator("h1").inner_text().replace("\n", " ").startswith("Off the")


def test_run_agent_streams_three_domains(server, page):
    page.goto(server["url"] + "/")
    page.fill("#domains", "alpha.test\nbeta.test\ngamma.test")
    page.check("input[name=qualify_only]")
    page.click("[data-run-btn]")
    page.wait_for_selector("[data-run-status]:has-text('Done. 3 companies')", timeout=15000)
    stream = page.locator("[data-stream]").inner_text()
    assert "careers" in stream and "gamma.test: NO-GO" in stream


def test_company_page_shows_highlighted_evidence(server, page):
    page.goto(server["url"] + "/companies")
    page.click("tr[data-href='/companies/ledgerly.test']")
    page.wait_for_selector("text=ICP scorecard")
    assert page.url.endswith("/companies/ledgerly.test")
    assert page.locator(".hl", has_text="Senior Compliance Engineer").count() == 1
    assert page.locator("a.source[href='https://ledgerly.test/careers']").count() == 1
    assert page.locator(".tl").count() >= 2


def test_review_edit_undo_approve_reject_and_keyboard(server, page):
    page.goto(server["url"] + "/review")
    page.wait_for_selector("[data-mail]")
    assert page.locator(".queue-item").count() == 2
    page.keyboard.press("j")
    assert "Second" in page.locator(".queue-item[aria-current='true']").inner_text()
    page.keyboard.press("k")

    # Edit: the edit % meter moves as the reviewer types.
    page.keyboard.press("e")
    assert page.locator("[data-pct]").inner_text() == "0%"
    page.locator("[data-body]").press("End")
    page.locator("[data-body]").type(" Totally rewritten with many new words added here.")
    page.wait_for_function("document.querySelector('[data-pct]').textContent !== '0%'")
    page.keyboard.press("Escape")

    # Approve then undo: nothing is sent.
    page.click("[data-approve]")
    page.wait_for_selector(".toast:has-text('Sending Ledgerly')")
    page.keyboard.press("u")
    page.wait_for_selector(".toast:has-text('Nothing was sent')")
    assert page.locator(".queue-item").count() == 2 and server["sent"] == []

    # Dry run approve: no send, draft stays.
    page.check("[data-dry]")
    page.click("[data-approve]")
    page.wait_for_selector(".toast:has-text('nothing was sent')", timeout=5000)
    assert server["sent"] == []
    page.uncheck("[data-dry]")
    page.locator("h1").click()  # shortcuts pause while a form field has focus

    # Reject one with a reason.
    page.keyboard.press("j")
    page.keyboard.press("x")
    page.fill("[data-reason]", "wrong person")
    page.keyboard.press("Enter")
    page.wait_for_selector(".toast:has-text('Rejected the Second draft')")

    # Real approve (mocked Resend): goes only to TEST_RECIPIENT after the undo window.
    page.wait_for_selector(".queue-item >> nth=0")
    page.click("[data-approve]")
    page.wait_for_selector(".toast:has-text('Sent to your test inbox')", timeout=5000)
    assert server["sent"] == [("me@example.com", "Your compliance engineer hire")]
    page.wait_for_selector("text=Inbox zero.")


def test_reduced_motion_is_static_and_readable(server, browser):
    ctx = browser.new_context(reduced_motion="reduce")
    pg = ctx.new_page()
    pg.goto(server["url"] + "/quality")
    pg.wait_for_selector(".gauge-value b")
    pg.wait_for_timeout(500)
    assert "motion" not in (pg.locator("html").get_attribute("class") or "")
    assert pg.locator(".gauge-value b").inner_text().endswith("%")
    assert pg.evaluate("[...document.querySelectorAll('[data-reveal]')].every(e => getComputedStyle(e).opacity === '1')")
    ctx.close()


def test_keyboard_only_navigation(server, page):
    page.goto(server["url"] + "/")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip"
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")  # "Companies" in the rail
    page.wait_for_url("**/companies")
    assert page.locator("[data-nav='/companies'][aria-current='page']").count() == 1
