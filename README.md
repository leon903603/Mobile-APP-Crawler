# Mobile App Dev DB

ISLab project to gather info about mobile app developers, and reach out to them about the lab's cloud analysis service.

> [!IMPORTANT]
> Taking over this project? Read [HANDOVER.md](HANDOVER.md) first — architecture, known
> pitfalls, and the remaining TODO list are all there. This README is just the quick start.

Data sources: `google-play-scraper` for Google Play[^1], the old 2017 iTunes/Search API for the App Store[^2].
Developer emails are scraped from the developer's own website with Playwright.

## Pipeline

```
App Store / Google Play  ──►  Postgres (appcrawler)  ──►  email enrichment  ──►  outreach
   crawl apps + devs           developers / apps          Playwright visits       mail.py
                               / app_versions             dev sites for email
```

Crawlers pull work from a `crawl_tasks` queue in Postgres, so multiple containers run in
parallel without duplicating work. Each store × region pair gets its own container and its
own Tor proxy to spread out the request load.

Regions: `americas`, `europe`, `asia-pacific`, `africa-me`.

## Layout

| Path | What it is |
|---|---|
| [main.py](main.py) | Crawler container entrypoint — `CRAWLER_TYPE` picks the worker |
| [seed_tasks.py](seed_tasks.py) | Fills the `crawl_tasks` queue (country × category / keyword / language) |
| [crawlers/](crawlers/) | Store crawlers, email enrichment, search-term generation |
| [db/](db/) | Connection pool, schema, task queue, upserts |
| [mail.py](mail.py) | Gmail SMTP outreach — see the caveats in [HANDOVER.md](HANDOVER.md) §5 |

## Running it

Everything except `db` sits behind a Compose profile, so a bare `docker compose up -d`
only starts Postgres.

```shell
# database
docker compose up -d db

# crawlers (each profile brings up 4 crawlers + 4 Tor proxies)
docker compose --profile app_store up -d
docker compose --profile google_play up -d

# seed the task queue — only needed when the queue runs dry.
# tables must exist first, so run this after the crawlers have started once.
pip install -r requirements.txt
DB_HOST=localhost DB_PORT=5433 python3 seed_tasks.py

# email enrichment (one-shot batch, exits when no developers are left to enrich)
docker compose --profile enrich up -d
docker compose logs -f email-enrich
```

Local debug mode — runs both crawlers in-process against `localhost:5433`, no containers:

```shell
python3 main.py
```

## Checking on the DB

```shell
psql -h localhost -p 5433 -U crawler -d appcrawler    # password: crawlerpass
```

```sql
-- queue progress
SELECT source, region, status, COUNT(*) FROM crawl_tasks GROUP BY 1,2,3 ORDER BY 1,2,3;

-- how much we've collected
SELECT store, COUNT(*) FROM apps GROUP BY store;

-- email enrichment progress ('not_found' = site was scraped, no email on it)
SELECT
  COUNT(*) FILTER (WHERE email IS NULL)                              AS pending,
  COUNT(*) FILTER (WHERE email = 'not_found')                        AS not_found,
  COUNT(*) FILTER (WHERE email IS NOT NULL AND email <> 'not_found') AS mailable
FROM developers;
```

## Plotting

```shell
python3 visualize.py    # writes images/<store>.png
```

## Notes

- `config.json` (Gmail credentials) and `ads/` are gitignored — they don't come with a clone.
- Always attach `logging: *default-logging` to new Compose services. A crash-looping
  container once wrote a single 304GB log file on the lab machine.
- Don't `docker compose down -v` on the lab machine — that drops the `pgdata` volume
  and everything crawled so far with it.

## Todo

- ~~Flesh out the schema~~
- ~~Rewrite crawling logic~~
- ~~Dev as model?~~
- ~~Include app version in schema~~
- ~~Run continuously on Lab PC~~
- Deploy the on-prem app analysis platform, scan every app, mail the report excerpt to its
  developer — the main outstanding work, broken down in [HANDOVER.md](HANDOVER.md) §6
- google-play-scraper not pulling enough apps, need to change from `search` to `collection` for better results
- Cloud compatibility, maybe store apps on S3?
- Pull even more apps

[^1]: https://github.com/JoMingyu/google-play-scraper
[^2]: https://performance-partners.apple.com/search-api
