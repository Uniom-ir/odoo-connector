#!/usr/bin/env python3
# Part of Uniom Messaging Gateway for Odoo. See LICENSE file for full
# copyright and licensing details.
"""Capture module screenshots with Playwright against a running Odoo.

Env: ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_PASSWORD, OUT_DIR
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("ODOO_URL", "http://localhost:8069")
DB = os.environ["ODOO_DB"]
LOGIN = os.environ.get("ODOO_LOGIN", "admin")
PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")
OUT = os.environ.get("OUT_DIR", "screenshots")

SHOTS = [
    # (name, menu path pieces, sleep before shot)
    ("screenshot_01_messages", ["Uniom", "Messages"], 1.5),
    ("screenshot_02_rules", ["Uniom", "Automation Rules"], 1.5),
    ("screenshot_03_connections", ["Uniom", "Connections"], 1.5),
    ("screenshot_04_templates", ["Uniom", "Templates"], 1.5),
]


def login(page):
    page.goto(f"{URL}/web/login", wait_until="networkidle")
    page.fill("input[name=db]", DB)
    page.fill("input[name=login]", LOGIN)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector(".o_main_navbar", timeout=90_000)


def open_app(page, breadcrumb):
    page.goto(f"{URL}/web#home", wait_until="networkidle")
    page.click(".o_navbar_apps_menu button")
    page.wait_for_selector(".o-apps", timeout=30_000)
    page.click(f".o-apps span:has-text('{breadcrumb[0]}')")
    page.wait_for_selector(".o_control_panel", timeout=30_000)
    if len(breadcrumb) > 1:
        page.click(f".o_menu_sections a:has-text('{breadcrumb[1]}')", timeout=15_000)


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        login(page)
        failures = []
        for name, path, delay in SHOTS:
            try:
                open_app(page, path)
                time.sleep(delay)
                page.screenshot(path=os.path.join(OUT, f"{name}.png"))
                print("captured", name)
            except Exception as error:  # noqa: BLE001
                failures.append((name, str(error)))
                print("FAILED", name, error, file=sys.stderr)
        browser.close()
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
