# Spotify Daily Charts — Tracker

Tracks the Spotify Daily charts for **Global, United States, Japan and South
Korea** (as published by [kworb.net](https://kworb.net/spotify/)) with a daily
GitHub Actions cron job, commits the results as JSON, and displays them on a
GitHub Pages site with one tab per region.

Every entry is clickable and plays the song on Spotify. New entries and the
highest climbers of the day are highlighted.

## How it works

```
GitHub Actions (cron)  --scrapes-->  docs/data/<region>.json  --served by-->  GitHub Pages
        |                                     |
        v                                     v
 scripts/fetch_charts.py       docs/data/history/<region>/YYYY-MM-DD.json
```

- **`scripts/fetch_charts.py`** scrapes the four kworb daily chart pages and
  writes one JSON snapshot per region, plus a dated archive copy:
  - [Global](https://kworb.net/spotify/country/global_daily.html)
  - [United States](https://kworb.net/spotify/country/us_daily.html)
  - [Japan](https://kworb.net/spotify/country/jp_daily.html)
  - [South Korea](https://kworb.net/spotify/country/kr_daily.html)
- **`.github/workflows/update-charts.yml`** runs the scraper on a schedule,
  then commits and pushes any changed files.
- **`docs/index.html`** is a static page with four tabs (Global / US / Japan /
  South Korea) that fetches the per-region JSON and renders the chart. GitHub
  Pages serves this folder directly — no build step.

kworb's chart table already includes rank movement (`NEW` / `RE` / `+n` /
`-n`), streams, peak and days on chart, and its track links are named after
the Spotify track ID — that's how every row gets a working
`open.spotify.com/track/…` play link.

## Setup

1. **Push to GitHub** (repo already initialized):
   ```bash
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```

2. **Enable GitHub Pages.**
   Repo → **Settings** → **Pages** → set **Source** to "Deploy from a branch,"
   pick branch `main` and folder `/docs`, then save.

3. **Enable Actions write permissions.**
   Repo → **Settings** → **Actions** → **General** → "Workflow permissions" →
   select **"Read and write permissions"** → save.

4. **Run the workflow once** (Actions tab → "Update Spotify chart data" →
   Run workflow) so the data files exist immediately. It also runs on every
   push to `main` and daily at 08:15 UTC.

## Local testing

```bash
pip install -r requirements.txt
python scripts/fetch_charts.py

cd docs && python -m http.server        # then open http://localhost:8000
```

(`fetch()` doesn't work over `file://`, hence the local server.)

## Notes on the data

This mirrors publicly visible chart positions from kworb.net, which itself
aggregates Spotify's public chart data, for personal/non-commercial tracking.
Be a considerate scraper: the workflow runs once a day, which matches the
chart's update cadence — don't lower the cron interval to something
aggressive.
