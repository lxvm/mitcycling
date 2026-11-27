#!/usr/bin/env python3
"""
Fetch MIT Cycling race results from the BikeReg and crossresults.com team pages.
Both sites run on the same AthleteReg backend and render identical markup, so
one parser handles both.
Requires: playwright (pip install playwright && playwright install chromium)

Writes: data/race_results_live.json
Run:    python3 scripts/fetch_results.py
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Team IDs are per-site: crossresults' /team/40588 is a different team.
SOURCES = [
    ("BikeReg", "https://results.bikereg.com/team/40588"),
    ("crossresults", "https://www.crossresults.com/team/72"),
]
OUTPUT = Path(__file__).parent.parent / "data" / "race_results_live.json"


def fetch_all() -> dict:
    """Return {source name: html} for every source that loaded; warn on the rest."""
    pages = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = ctx.new_page()
        for name, url in SOURCES:
            print(f"Fetching {name} team results page…", file=sys.stderr)
            try:
                page.goto(url, timeout=45_000)
                try:
                    page.wait_for_selector("table.datatable1", timeout=45_000)
                except PlaywrightTimeoutError:
                    pass  # fall through to the content check below for a clearer error
                page.wait_for_timeout(5_000)
                html = page.content()
            except Exception as e:  # one site being down shouldn't block the other
                print(f"WARNING: {name} fetch failed: {e}", file=sys.stderr)
                continue
            if "datatable1" not in html:
                print(f"WARNING: {name} did not return expected content — Cloudflare may have blocked the request",
                      file=sys.stderr)
                continue
            pages[name] = html
        browser.close()
    if not pages:
        raise RuntimeError("No results source could be fetched")
    return pages


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def parse_results(html: str, team_url: str) -> list:
    # The results table is the 4th datatable1 on the page (index 3)
    tables = re.findall(
        r'<table[^>]*class="datatable1"[^>]*>(.*?)</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if len(tables) < 4:
        raise RuntimeError(f"Expected at least 4 datatable1 tables, found {len(tables)}")

    results_table = tables[3]
    rows = re.findall(r'(<tr[^>]*>.*?</tr>)', results_table, re.DOTALL | re.IGNORECASE)

    results = []
    current_race = ""
    current_date = ""
    current_date_iso = ""

    for row_html in rows:
        if 'class="headerrow"' in row_html:
            # Race header: <h2>Race Name (Mon DD YYYY)</h2>
            h2 = re.search(r'<h2[^>]*>(.*?)</h2>', row_html, re.DOTALL | re.IGNORECASE)
            if not h2:
                continue
            text = strip_tags(h2.group(1))
            # Split "Race Name (Jun 9 2026)" into name and date
            m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', text)
            if m:
                current_race = m.group(1).strip()
                current_date = m.group(2).strip()
                try:
                    dt = datetime.strptime(current_date, "%b %d %Y")
                    current_date_iso = dt.strftime("%Y-%m-%d")
                except ValueError:
                    current_date_iso = ""
            else:
                current_race = text
                current_date = ""
                current_date_iso = ""

        elif 'class="datarow' in row_html:
            # Result row: first name | last name | category | place / field
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.IGNORECASE)
            if len(cells) < 4:
                continue

            first = strip_tags(cells[0])
            last = strip_tags(cells[1])
            category = strip_tags(cells[2])
            place_text = strip_tags(cells[3])  # e.g. "27 / 48"

            place = 0
            field = 0
            pm = re.match(r'(\d+)\s*/\s*(\d+)', place_text)
            if pm:
                place = int(pm.group(1))
                field = int(pm.group(2))

            if place == 999:
                continue

            results.append({
                "date": current_date,
                "date_iso": current_date_iso,
                "race": current_race,
                "race_url": team_url,
                "rider": f"{first} {last}".strip(),
                "place": place,
                "category": category,
                "finish": f"{place} of {field}" if field else "",
            })

    return results


def result_key(r: dict) -> tuple:
    return (r["date_iso"], r["race"], r["rider"], r["category"])


def main():
    existing = []
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text())

    seen = {result_key(r) for r in existing}

    pages = fetch_all()
    urls = dict(SOURCES)
    new_results = []
    for name, html in pages.items():
        print(f"Parsing {name} results…", file=sys.stderr)
        added = 0
        # A race can appear on both sites; the first source listed wins.
        for r in parse_results(html, urls[name]):
            if result_key(r) not in seen:
                seen.add(result_key(r))
                new_results.append(r)
                added += 1
        print(f"  {added} new from {name}", file=sys.stderr)

    if not new_results:
        print("No new results.", file=sys.stderr)
        return

    # The templates show results in file order (the homepage takes the first
    # few), so keep the file newest-first. Stable sort keeps same-day order.
    merged = sorted(new_results + existing, key=lambda r: r["date_iso"], reverse=True)
    OUTPUT.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    print(f"Added {len(new_results)} new results ({len(merged)} total) to {OUTPUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
