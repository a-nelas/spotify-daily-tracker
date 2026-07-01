#!/usr/bin/env python3
"""
Scrapes kworb.net's Spotify Daily charts for Global, US, Japan and South
Korea and writes one JSON snapshot per region for the static site to render.

kworb's track links are named after the Spotify track ID, so every entry
still gets a working open.spotify.com play link. The chart table also
carries rank movement (NEW / RE / +n / -n) directly, so no history
comparison is needed.

Output:
  docs/data/<region>.json                     -> latest snapshot per region
  docs/data/history/<region>/YYYY-MM-DD.json  -> archived copy of every run
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; spotify-chart-tracker/1.0; "
    "+https://github.com/)"
}

REGIONS = {
    "global": {
        "label": "Global",
        "url": "https://kworb.net/spotify/country/global_daily.html",
    },
    "us": {
        "label": "United States",
        "url": "https://kworb.net/spotify/country/us_daily.html",
    },
    "jp": {
        "label": "Japan",
        "url": "https://kworb.net/spotify/country/jp_daily.html",
    },
    "kr": {
        "label": "South Korea",
        "url": "https://kworb.net/spotify/country/kr_daily.html",
    },
}

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
HISTORY_DIR = DATA_DIR / "history"


def to_int(text):
    """Turn '4,206,904' / '+56,958' / '' into an int or None."""
    text = (text or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_change(text, rank):
    """kworb's movement column: '=', '+7', '-3', 'NEW', 'RE'."""
    text = (text or "").strip()
    if text == "=":
        return {"status": "same", "delta": 0}, rank
    if text == "NEW":
        return {"status": "new", "delta": None}, None
    if text == "RE":
        return {"status": "re-entry", "delta": None}, None
    m = re.match(r"^([+-])(\d+)$", text)
    if m:
        delta = int(m.group(2)) * (1 if m.group(1) == "+" else -1)
        status = "up" if delta > 0 else "down"
        return {"status": status, "delta": delta}, rank + delta
    return {"status": "unknown", "delta": None}, None


def spotify_id_from_href(href):
    """kworb hrefs look like '../track/0kosUz0jePvjiz4ctmR6wL.html'."""
    m = re.search(r"/([0-9A-Za-z]+)\.html$", href or "")
    return m.group(1) if m else None


def extract_chart_date(html):
    """Page title reads e.g. 'Spotify Daily Chart - Global - 2026/06/30'."""
    m = re.search(r"Spotify Daily Chart - .*? - (\d{4}/\d{2}/\d{2})", html)
    if m:
        return m.group(1).replace("/", "-")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_region(session, region):
    resp = session.get(region["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    # kworb serves UTF-8 but omits the charset header, so requests would
    # otherwise fall back to ISO-8859-1 and garble Japanese/Korean titles
    resp.encoding = "utf-8"
    html = resp.text
    chart_date = extract_chart_date(html)

    table = BeautifulSoup(html, "lxml").find("table")
    if table is None:
        raise RuntimeError("Could not find chart table on page")

    entries = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 11:
            continue  # header row or malformed row

        rank = to_int(cells[0].get_text())
        if rank is None:
            continue
        change, prev_rank = parse_change(cells[1].get_text(), rank)

        # Artist/title cell: first <a> = artist, second = track title
        links = cells[2].find_all("a")
        artist = links[0].get_text(strip=True) if len(links) > 0 else None
        title = links[1].get_text(strip=True) if len(links) > 1 else None
        track_id = spotify_id_from_href(links[1]["href"]) if len(links) > 1 else None
        featured = [a.get_text(strip=True) for a in links[2:]]

        entries.append({
            "rank": rank,
            "prev_rank": prev_rank,
            "change": change,
            "title": title,
            "artists": [a for a in [artist, *featured] if a],
            "track_id": track_id,
            "track_url": (
                f"https://open.spotify.com/track/{track_id}" if track_id else None
            ),
            "peak_rank": to_int(cells[4].get_text()),
            "days_on_chart": to_int(cells[3].get_text()),
            "streams": to_int(cells[6].get_text()),
        })

    if not entries:
        raise RuntimeError("Chart table had no parseable rows")
    entries.sort(key=lambda e: e["rank"])
    return entries, chart_date


def build_snapshot(region_key, region, entries, chart_date):
    new_entries = [e for e in entries if e["change"]["status"] == "new"]
    # ten biggest climbs, listed by the rank they reached
    climbers = sorted(
        sorted(
            (e for e in entries if e["change"]["status"] == "up"),
            key=lambda e: e["change"]["delta"],
            reverse=True,
        )[:10],
        key=lambda e: e["rank"],
    )
    return {
        "region": region_key,
        "label": region["label"],
        "chart_date": chart_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": "kworb.net daily chart",
        "source_url": region["url"],
        "entry_count": len(entries),
        "entries": entries,
        "new_entries": new_entries,
        "top_climbers": climbers,
    }


def main():
    session = requests.Session()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0

    for key, region in REGIONS.items():
        try:
            entries, chart_date = fetch_region(session, region)
            snapshot = build_snapshot(key, region, entries, chart_date)

            latest = DATA_DIR / f"{key}.json"
            latest.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False),
                              encoding="utf-8")
            archive = HISTORY_DIR / key / f"{chart_date}.json"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False),
                               encoding="utf-8")
            print(f"[{key}] {len(entries)} entries for {chart_date}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[{key}] FAILED: {exc}", file=sys.stderr)

    if failures == len(REGIONS):
        sys.exit(1)


if __name__ == "__main__":
    main()
