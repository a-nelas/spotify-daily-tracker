#!/usr/bin/env python3
"""
Scrapes kworb.net's Spotify Global Daily chart and writes structured JSON.

Output:
  docs/data.json                -> latest snapshot (what the site reads)
  docs/data/history/YYYY-MM-DD.json -> archived copy of every run
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://kworb.net/spotify/country/global_daily.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; spotify-chart-tracker/1.0; "
    "+https://github.com/)"
}

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
HISTORY_DIR = DOCS / "data" / "history"


def to_int(text: str):
    """Turn '4,127,032' / '+84,637' / '-359,994' / '' into an int or None."""
    if text is None:
        return None
    text = text.strip().replace(",", "")
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_change(text: str):
    """Position-change column: '=', '+7', '-3', 'NEW', 'RE' -> normalized dict."""
    text = (text or "").strip()
    if text == "=":
        return {"raw": text, "delta": 0, "status": "same"}
    if text == "NEW":
        return {"raw": text, "delta": None, "status": "new"}
    if text == "RE":
        return {"raw": text, "delta": None, "status": "re-entry"}
    m = re.match(r"^([+-]\d+)$", text)
    if m:
        return {"raw": text, "delta": int(m.group(1)), "status": "moved"}
    return {"raw": text, "delta": None, "status": "unknown"}


def parse_page(html: str, chart_date: str):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        raise RuntimeError("Could not find chart table on page")

    rows = table.find_all("tr")
    entries = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 11:
            continue  # header row or malformed row

        pos = to_int(cells[0].get_text())
        change = parse_change(cells[1].get_text())

        # Artist/title cell contains one or more <a> tags:
        # first = main artist, second = track title, rest = features
        links = cells[2].find_all("a")
        artist = links[0].get_text(strip=True) if len(links) > 0 else None
        artist_url = links[0]["href"] if len(links) > 0 else None
        title = links[1].get_text(strip=True) if len(links) > 1 else None
        track_url = links[1]["href"] if len(links) > 1 else None
        featured = [a.get_text(strip=True) for a in links[2:]]

        entry = {
            "pos": pos,
            "change": change,
            "artist": artist,
            "artist_url": (
                f"https://kworb.net/spotify/{artist_url.lstrip('./')}"
                if artist_url else None
            ),
            "title": title,
            "track_url": (
                f"https://kworb.net/spotify/{track_url.lstrip('./')}"
                if track_url else None
            ),
            "featured": featured,
            "days_on_chart": to_int(cells[3].get_text()),
            "peak": to_int(cells[4].get_text()),
            "streams": to_int(cells[6].get_text()),
            "streams_change": to_int(cells[7].get_text()),
            "seven_day": to_int(cells[8].get_text()),
            "seven_day_change": to_int(cells[9].get_text()),
            "total_streams": to_int(cells[10].get_text()),
        }
        entries.append(entry)

    new_entries = [e for e in entries if e["change"]["status"] == "new"]
    re_entries = [e for e in entries if e["change"]["status"] == "re-entry"]
    climbers = sorted(
        (e for e in entries if e["change"]["status"] == "moved" and e["change"]["delta"] > 0),
        key=lambda e: e["change"]["delta"],
        reverse=True,
    )[:15]
    fallers = sorted(
        (e for e in entries if e["change"]["status"] == "moved" and e["change"]["delta"] < 0),
        key=lambda e: e["change"]["delta"],
    )[:15]

    return {
        "source": URL,
        "chart_date": chart_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entries),
        "entries": entries,
        "new_entries": new_entries,
        "re_entries": re_entries,
        "top_climbers": climbers,
        "top_fallers": fallers,
    }


def extract_chart_date(html: str) -> str:
    """The page header reads e.g. 'Spotify Daily Chart - Global - 2026/06/18'."""
    m = re.search(r"Global\s*-\s*(\d{4}/\d{2}/\d{2})", html)
    if m:
        return m.group(1).replace("/", "-")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main():
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text

    chart_date = extract_chart_date(html)
    data = parse_page(html, chart_date)

    DOCS.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    latest_path = DOCS / "data.json"
    latest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    history_path = HISTORY_DIR / f"{chart_date}.json"
    history_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print(f"Wrote {len(data['entries'])} entries for {chart_date}")
    print(f"  -> {latest_path}")
    print(f"  -> {history_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Scrape failed: {exc}", file=sys.stderr)
        sys.exit(1)
