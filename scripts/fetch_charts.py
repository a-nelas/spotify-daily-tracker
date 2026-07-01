#!/usr/bin/env python3
"""
Fetches Spotify's official daily charts for Global, US, Japan and South Korea
and writes one JSON snapshot per region for the static site to render.

Two data modes, tried in order:

1. Official charts CSV (top 200) from charts.spotify.com.
   Requires a logged-in Spotify session: set the SP_DC environment variable
   to the value of your `sp_dc` cookie (see README). The CSV already carries
   previous_rank / peak_rank / days_on_chart / streams.

2. Anonymous fallback: the official "Top 50" daily chart playlists via the
   public open.spotify.com embed pages. No credentials needed. Rank movement
   is computed against the previous snapshot stored in docs/data/history/.

Output:
  docs/data/<region>.json                     -> latest snapshot per region
  docs/data/history/<region>/YYYY-MM-DD.json  -> archived copy of every run
"""

import csv
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

REGIONS = {
    "global": {
        "label": "Global",
        "chart": "regional-global-daily",
        "playlist": "37i9dQZEVXbMDoHDwVN2tF",  # Top 50 - Global
    },
    "us": {
        "label": "United States",
        "chart": "regional-us-daily",
        "playlist": "37i9dQZEVXbLRQDuF5jeBp",  # Top 50 - USA
    },
    "jp": {
        "label": "Japan",
        "chart": "regional-jp-daily",
        "playlist": "37i9dQZEVXbKXQ4mDTEBXq",  # Top 50 - Japan
    },
    "kr": {
        "label": "South Korea",
        "chart": "regional-kr-daily",
        "playlist": "37i9dQZEVXbNxXF4SkHj9F",  # Top 50 - South Korea
    },
}

CHARTS_PAGE = "https://charts.spotify.com/charts/view/{chart}/latest"
CSV_URL = (
    "https://charts-spotify-com-service.spotify.com"
    "/auth/v0/charts/{chart}/latest/download"
)
TOKEN_URL = "https://charts.spotify.com/api/token"
EMBED_URL = "https://open.spotify.com/embed/playlist/{playlist}"

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
HISTORY_DIR = DATA_DIR / "history"


def get_charts_token(session: requests.Session, sp_dc: str) -> str:
    """Exchange the sp_dc login cookie for a charts API bearer token."""
    resp = session.get(
        TOKEN_URL,
        cookies={"sp_dc": sp_dc},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    token = payload.get("accessToken") or payload.get("access_token")
    if not token:
        raise RuntimeError(f"No access token in response: {list(payload)}")
    return token


def change_from_ranks(rank, prev_rank):
    """Normalize rank movement into {status, delta}."""
    if prev_rank is None:
        return {"status": "new", "delta": None}
    delta = prev_rank - rank
    if delta > 0:
        return {"status": "up", "delta": delta}
    if delta < 0:
        return {"status": "down", "delta": delta}
    return {"status": "same", "delta": 0}


def fetch_region_csv(session: requests.Session, token: str, region: dict):
    """Official top-200 daily chart CSV from charts.spotify.com."""
    resp = session.get(
        CSV_URL.format(chart=region["chart"]),
        headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()

    # Chart date is in the download filename, e.g. regional-us-daily-2026-06-30.csv
    disposition = resp.headers.get("Content-Disposition", "")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", disposition)
    chart_date = m.group(1) if m else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entries = []
    for row in csv.DictReader(io.StringIO(resp.text)):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
        rank = int(row["rank"])
        prev = int(row.get("previous_rank") or -1)
        days = int(row.get("days_on_chart") or 0)
        track_id = row.get("uri", "").split(":")[-1]
        artists = [a.strip() for a in row.get("artist_names", "").split(",") if a.strip()]

        if prev <= 0:
            change = {"status": "re-entry" if days > 1 else "new", "delta": None}
        else:
            change = change_from_ranks(rank, prev)

        entries.append({
            "rank": rank,
            "prev_rank": prev if prev > 0 else None,
            "change": change,
            "title": row.get("track_name"),
            "artists": artists,
            "track_id": track_id,
            "track_url": f"https://open.spotify.com/track/{track_id}",
            "peak_rank": int(row["peak_rank"]) if row.get("peak_rank") else None,
            "days_on_chart": days or None,
            "streams": int(row["streams"]) if row.get("streams") else None,
        })

    entries.sort(key=lambda e: e["rank"])
    return entries, chart_date, "charts.spotify.com CSV (top 200)"


def previous_ranks(region_key: str, before_date: str):
    """Latest archived snapshot strictly older than before_date, as {track_id: rank}."""
    region_history = HISTORY_DIR / region_key
    if not region_history.is_dir():
        return None
    files = sorted(
        f for f in region_history.glob("*.json") if f.stem < before_date
    )
    if not files:
        return None
    snapshot = json.loads(files[-1].read_text(encoding="utf-8"))
    return {e["track_id"]: e["rank"] for e in snapshot["entries"]}


def fetch_region_playlist(session: requests.Session, region_key: str, region: dict):
    """Anonymous fallback: official Top 50 chart playlist via the embed page."""
    resp = session.get(
        EMBED_URL.format(playlist=region["playlist"]),
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()

    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        re.S,
    )
    if not m:
        raise RuntimeError("No __NEXT_DATA__ payload in embed page")
    entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    track_list = entity.get("trackList") or []
    if not track_list:
        raise RuntimeError(f"Empty track list for playlist {region['playlist']}")

    chart_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prev = previous_ranks(region_key, chart_date)

    entries = []
    for i, track in enumerate(track_list, start=1):
        track_id = track["uri"].split(":")[-1]
        # subtitle is the artist list, e.g. "Shakira,\xa0Burna Boy"
        artists = [
            a.strip() for a in (track.get("subtitle") or "").replace("\xa0", " ").split(",")
            if a.strip()
        ]
        if prev is None:
            change = {"status": "unknown", "delta": None}  # first run: no baseline
            prev_rank = None
        else:
            prev_rank = prev.get(track_id)
            change = change_from_ranks(i, prev_rank)

        entries.append({
            "rank": i,
            "prev_rank": prev_rank,
            "change": change,
            "title": track.get("title"),
            "artists": artists,
            "track_id": track_id,
            "track_url": f"https://open.spotify.com/track/{track_id}",
            "peak_rank": None,
            "days_on_chart": None,
            "streams": None,
        })

    return entries, chart_date, "Top 50 chart playlist (anonymous)"


def build_snapshot(region_key: str, region: dict, entries, chart_date, source_mode):
    new_entries = [e for e in entries if e["change"]["status"] in ("new", "re-entry")]
    climbers = sorted(
        (e for e in entries if e["change"]["status"] == "up"),
        key=lambda e: e["change"]["delta"],
        reverse=True,
    )
    return {
        "region": region_key,
        "label": region["label"],
        "chart_date": chart_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mode": source_mode,
        "source_url": CHARTS_PAGE.format(chart=region["chart"]),
        "entry_count": len(entries),
        "entries": entries,
        "new_entries": new_entries,
        "top_climbers": climbers[:10],
    }


def main():
    session = requests.Session()
    sp_dc = os.environ.get("SP_DC", "").strip()

    token = None
    if sp_dc:
        try:
            token = get_charts_token(session, sp_dc)
            print("Using official charts.spotify.com CSV (SP_DC token OK)")
        except Exception as exc:  # noqa: BLE001
            print(f"SP_DC token exchange failed ({exc}); "
                  "falling back to anonymous Top 50 playlists", file=sys.stderr)
    else:
        print("SP_DC not set; using anonymous Top 50 playlists")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0

    for key, region in REGIONS.items():
        try:
            if token:
                try:
                    entries, chart_date, mode = fetch_region_csv(session, token, region)
                except Exception as exc:  # noqa: BLE001
                    print(f"[{key}] CSV fetch failed ({exc}); trying playlist fallback",
                          file=sys.stderr)
                    entries, chart_date, mode = fetch_region_playlist(session, key, region)
            else:
                entries, chart_date, mode = fetch_region_playlist(session, key, region)

            snapshot = build_snapshot(key, region, entries, chart_date, mode)

            latest = DATA_DIR / f"{key}.json"
            latest.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False),
                              encoding="utf-8")
            archive = HISTORY_DIR / key / f"{chart_date}.json"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False),
                               encoding="utf-8")
            print(f"[{key}] {len(entries)} entries for {chart_date} via {mode}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[{key}] FAILED: {exc}", file=sys.stderr)

    if failures == len(REGIONS):
        sys.exit(1)


if __name__ == "__main__":
    main()
