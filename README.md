# Spotify Global Daily — Chart Tracker

Scrapes [kworb.net's Spotify Global Daily chart](https://kworb.net/spotify/country/global_daily.html)
once a day with a GitHub Actions cron job, commits the results as JSON, and
displays them on a GitHub Pages site.

## How it works

```
GitHub Actions (cron)  --scrapes-->  docs/data.json  --served by-->  GitHub Pages
       |                                    |
       v                                    v
  scripts/scrape.py            docs/data/history/YYYY-MM-DD.json
```

- **`scripts/scrape.py`** fetches the page, parses the chart table, and writes
  `docs/data.json` (latest snapshot) plus a dated copy in `docs/data/history/`.
- **`.github/workflows/update-chart.yml`** runs the scraper on a schedule,
  then commits and pushes any changed files.
- **`docs/index.html`** is a static page that fetches `data.json` and renders
  the chart, new entries, and biggest climbers/fallers. GitHub Pages serves
  this folder directly — no build step.

## Setup

1. **Create the repo.** On GitHub, click "New repository," give it a name
   (e.g. `spotify-chart-tracker`), and create it — public or private both
   work for Pages (private repos need GitHub Pro/Team/Enterprise for Pages).

2. **Push these files.**
   ```bash
   cd spotify-chart-tracker
   git init
   git add .
   git commit -m "Initial commit: scraper, workflow, site"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```

3. **Enable GitHub Pages.**
   Repo → **Settings** → **Pages** → under "Build and deployment," set
   **Source** to "Deploy from a branch," pick branch `main` and folder `/docs`,
   then save. Your site will appear at
   `https://<your-username>.github.io/<repo-name>/` within a minute or two.

4. **Enable Actions write permissions.**
   Repo → **Settings** → **Actions** → **General** → scroll to "Workflow
   permissions" → select **"Read and write permissions"** → save. This lets
   the workflow commit the scraped data back to the repo.

5. **Run the scraper once manually** so `data.json` exists immediately
   instead of waiting for the next scheduled run:
   Repo → **Actions** tab → select **"Update Spotify chart data"** →
   **Run workflow** → **Run workflow**. After it finishes (~30 seconds),
   refresh your Pages URL.

That's it — from then on it updates automatically every day at the time set
in the workflow's cron schedule (default: 08:15 UTC).

## Customizing

- **Change the schedule:** edit the `cron` line in
  `.github/workflows/update-chart.yml`. Cron is in UTC.
  [crontab.guru](https://crontab.guru) helps if you want a different time.
- **Track a different country chart:** kworb has per-country URLs like
  `https://kworb.net/spotify/country/us_daily.html`. Change the `URL`
  constant at the top of `scripts/scrape.py` (and update the regex in
  `extract_chart_date` if the country name in the header text differs).
- **Change how much history you keep:** every run adds one file to
  `docs/data/history/`. If you don't want the repo to grow indefinitely, add
  a cleanup step to the workflow, or just let it accumulate — JSON files are
  small.
- **Local testing:** `pip install -r requirements.txt` then
  `python scripts/scrape.py` will write `docs/data.json` locally so you can
  open `docs/index.html` in a browser (use a local server, e.g.
  `python -m http.server`, from inside `docs/` — `fetch()` won't work with
  `file://` URLs).

## Notes on the data

This mirrors publicly visible chart positions from kworb.net, which itself
aggregates Spotify's public chart data, for personal/non-commercial tracking.
Be a considerate scraper: the workflow runs once a day, which is a
reasonable interval for a daily chart — don't lower the cron interval to
something aggressive.
