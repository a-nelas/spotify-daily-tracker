# Spotify Daily Charts — Tracker

Tracks Spotify's official daily charts for **Global, United States, Japan and
South Korea** with a daily GitHub Actions cron job, commits the results as
JSON, and displays them on a GitHub Pages site with one tab per region.

Every entry is clickable and plays the song on Spotify. New entries and the
highest climbers of the day are highlighted.

## How it works

```
GitHub Actions (cron)  --fetches-->  docs/data/<region>.json  --served by-->  GitHub Pages
        |                                     |
        v                                     v
 scripts/fetch_charts.py       docs/data/history/<region>/YYYY-MM-DD.json
```

- **`scripts/fetch_charts.py`** fetches the daily chart for each region and
  writes one JSON snapshot per region, plus a dated archive copy.
- **`.github/workflows/update-charts.yml`** runs the fetcher on a schedule,
  then commits and pushes any changed files.
- **`docs/index.html`** is a static page with four tabs (Global / US / Japan /
  South Korea) that fetches the per-region JSON and renders the chart. GitHub
  Pages serves this folder directly — no build step.

## Data source: two modes

The tracker targets the charts you see at
[charts.spotify.com](https://charts.spotify.com/charts/view/regional-global-daily/latest)
(also [US](https://charts.spotify.com/charts/view/regional-us-daily/latest),
[Japan](https://charts.spotify.com/charts/view/regional-jp-daily/latest),
[South Korea](https://charts.spotify.com/charts/view/regional-kr-daily/latest)).

Spotify gates the CSV download on that site behind a login, so the fetcher
supports two modes:

1. **Official CSV (top 200)** — used when the `SP_DC` secret is configured
   (see below). Downloads the same CSV as the site's "download" button, which
   includes previous rank, peak rank, days on chart, and stream counts.
2. **Anonymous fallback (top 50)** — used otherwise. Fetches Spotify's
   official "Top 50" daily chart playlists (the same charts data) through the
   public embed pages, no credentials needed. Rank movement is computed by
   comparing against the previous day's archived snapshot, so movement badges
   appear from the second run onward.

### Enabling official CSV mode (optional)

1. Log in to [open.spotify.com](https://open.spotify.com) in your browser.
2. Open DevTools → Application/Storage → Cookies → `https://open.spotify.com`
   and copy the value of the **`sp_dc`** cookie.
3. In your GitHub repo: **Settings → Secrets and variables → Actions →
   New repository secret**, name it `SP_DC`, paste the value.

The cookie is long-lived (~1 year) but does expire; when it does, the fetcher
logs a warning and automatically falls back to anonymous mode, so the site
keeps updating either way.

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
python scripts/fetch_charts.py          # anonymous mode
# or, for official CSV mode:
SP_DC=<your cookie> python scripts/fetch_charts.py

cd docs && python -m http.server        # then open http://localhost:8000
```

(`fetch()` doesn't work over `file://`, hence the local server.)

## Notes on the data

This mirrors Spotify's own published daily charts for personal,
non-commercial tracking. The workflow runs once per day, matching the chart's
update cadence — don't lower the cron interval to something aggressive.
