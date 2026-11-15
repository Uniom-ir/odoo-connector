#!/usr/bin/env python3
# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""UI approval pass: load every Uniom surface, fail on JS/page errors.

Captures a screenshot per surface into OUT_DIR and prints all pageerrors
plus console errors. Exits 1 when any surface shows an error dialog or a
page-level JS error.

Env: ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_PASSWORD, OUT_DIR
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("ODOO_URL", "http://localhost:8092")
DB = os.environ["ODOO_DB"]
LOGIN = os.environ.get("ODOO_LOGIN", "admin")
PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")
OUT = os.environ.get("OUT_DIR", "/tmp/ui_approve")

SURFACES = [
    ("10_dashboard", 272),
    ("20_messages", 273),
    ("30_connections", 278),
    ("40_rules", 276),
    ("50_templates", 277),
]


def login(page):
    page.goto(f"{URL}/web/login?db={DB}", wait_until="domcontentloaded")
    page.fill("input[name=login]", LOGIN)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector(".o_main_navbar", timeout=90_000)


def open_surface(page, menu_id):
    page.goto(f"{URL}/web?db={DB}#menu_id={menu_id}")
    page.wait_for_selector(".o_main_navbar", timeout=60_000)
    page.wait_for_selector(".o_action, .o_uniom_chat", timeout=60_000)
    time.sleep(3)


def main():
    os.makedirs(OUT, exist_ok=True)
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        problems = []

        def on_pageerror(error):
            problems.append(f"PAGEERROR: {error}")

        def on_console(message):
            if message.type == "error":
                problems.append(f"CONSOLE: {message.text[:300]}")

        page.on("pageerror", on_pageerror)
        page.on("console", on_console)
        login(page)
        for name, path in SURFACES:
            problems.clear()
            try:
                open_surface(page, path)
                if page.locator(".o_error_dialog, .o_dialog_error").count():
                    text = page.locator(".o_error_dialog, .o_dialog_error").first.inner_text()
                    failures.append((name, f"error dialog: {text[:300]}"))
                page.screenshot(path=os.path.join(OUT, f"{name}.png"))
                print("captured", name)
            except Exception as error:  # noqa: BLE001
                failures.append((name, str(error)[:300]))
                print("FAILED", name, error, file=sys.stderr)
            for problem in problems:
                print(f"  [{name}] {problem}")
                if problem.startswith("PAGEERROR"):
                    failures.append((name, problem[:300]))
        # dashboard manage view (kanban): click through from Conversations
        problems.clear()
        try:
            open_surface(page, 272)
            page.click(".o_uniom_manage", timeout=15_000)
            time.sleep(2)
            if page.locator(".o_error_dialog, .o_dialog_error").count():
                text = page.locator(".o_error_dialog, .o_dialog_error").first.inner_text()
                failures.append(("15_manage_kanban", f"error dialog: {text[:300]}"))
            page.screenshot(path=os.path.join(OUT, "15_manage_kanban.png"))
            print("captured 15_manage_kanban")
        except Exception as error:  # noqa: BLE001
            failures.append(("15_manage_kanban", str(error)[:300]))
            print("FAILED 15_manage_kanban", error, file=sys.stderr)
        for problem in problems:
            print(f"  [15_manage_kanban] {problem}")
            if problem.startswith("PAGEERROR"):
                failures.append(("15_manage_kanban", problem[:300]))
        browser.close()
    if failures:
        print("FAILURES:", failures, file=sys.stderr)
        sys.exit(1)
    print("UI-APPROVAL-OK")


if __name__ == "__main__":
    main()
