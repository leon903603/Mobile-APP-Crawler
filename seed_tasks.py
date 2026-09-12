import json

print("[SEED] started", flush=True)

from db.crawl_tasks import add_tasks_bulk
from crawlers.search_terms import generate_search_terms, ALL_LANGS, VERTICALS


# ──────────────────────────────────────────────────────────────────────────────
# REGION MAP
# Keys must exactly match the REGION env var set in docker-compose.yml
# ──────────────────────────────────────────────────────────────────────────────

REGION_FILES = {
    "americas":     "listings/countries-americas.json",
    "europe":       "listings/countries-europe.json",
    "asia-pacific": "listings/countries-asia_pacific.json",
    "africa-me":    "listings/countries-africa_middle_east.json",
}

# ──────────────────────────────────────────────────────────────────────────────
# LOAD CATEGORY LISTS
# ──────────────────────────────────────────────────────────────────────────────

with open("listings/apple-appstore-categories.json") as f:
    APPLE_CATEGORIES = json.load(f)

with open("listings/google-play-apps-categories.json") as f:
    GP_CATEGORIES = json.load(f)

# ──────────────────────────────────────────────────────────────────────────────
# BUILD AND INSERT TASKS PER REGION
# ──────────────────────────────────────────────────────────────────────────────

total_as_inserted = 0
total_as_skipped = 0
total_gp_inserted = 0
total_gp_skipped = 0

for region, filepath in REGION_FILES.items():
    with open(filepath) as f:
        countries = json.load(f)

    print(f"[SEED] region={region}  countries={len(countries)}", flush=True)

    # ── App Store tasks ───────────────────────────────────────────────────────
    app_tasks: list[tuple] = []

    for country in countries:
        for cat in APPLE_CATEGORIES:
            app_tasks.append((
                "app_store", country, "category", cat["category"], region,
            ))

        for term in generate_search_terms(country):
            app_tasks.append((
                "app_store", country, "keyword", term, region,
            ))

    inserted, skipped = add_tasks_bulk(app_tasks)
    total_as_inserted += inserted
    total_as_skipped += skipped
    print(f"[SEED] app_store  region={region}  queued={len(app_tasks)}  inserted={inserted}  skipped_existing={skipped}", flush=True)

    # ── Google Play tasks ─────────────────────────────────────────────────────
    gp_tasks: list[tuple] = []

    for country in countries:
        for cat in GP_CATEGORIES:
            gp_tasks.append((
                "google_play", country, "category", cat["category"], region,
            ))

        for term in generate_search_terms(country):
            gp_tasks.append((
                "google_play", country, "keyword", term, region,
            ))

        for lang in ALL_LANGS:
            for term in VERTICALS:
                gp_tasks.append((
                    "google_play", country, "language", f"{lang}::{term}", region,
                ))

    inserted, skipped = add_tasks_bulk(gp_tasks)
    total_gp_inserted += inserted
    total_gp_skipped += skipped
    print(f"[SEED] google_play  region={region}  queued={len(gp_tasks)}  inserted={inserted}  skipped_existing={skipped}", flush=True)


print(
    f"[SEED] done  App Store: (inserted={total_as_inserted}, skipped_existing={total_as_skipped})  "
    f"Google Play: (inserted={total_gp_inserted}, skipped_existing={total_gp_skipped})",
    flush=True
)