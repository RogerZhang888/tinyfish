# RunWise

RunWise is a running shoe recommendation app with two connected workflows:

- User-facing recommendations are served from a Supabase `shoes` table.
- A periodic TinyFish-powered catalog sync refreshes that table with newly released running shoes from major brands.

This setup keeps recommendation requests fast while ensuring the underlying catalog stays fresh.

## Current Workflow

### Recommendation Flow

1. User fills in the Astro form with budget, shoe type, foot shape, running style, and optional notes.
2. Frontend sends `POST /recommend-shoes` to FastAPI.
3. Backend queries the Supabase `shoes` table using the user’s filters:
   - `price < budget`
   - `type = shoe_type`
   - `foot_shape = foot_shape`
   - optional `brand` when provided
4. Backend returns all matching shoes in the existing recommendation response shape.
5. Results page renders the matching shoes, including image, price, weight, and recommendation details.

### Catalog Refresh Flow

RunWise uses TinyFish outside the request path to keep the catalog current.

1. A scheduled sync job runs the brand catalog scraper in [backend/scripts/scrape_brand_catalog_to_supabase.py](/Users/rogerzhang/github/tinyfish/backend/scripts/scrape_brand_catalog_to_supabase.py).
2. The script crawls supported brand catalog sites with TinyFish:
   - adidas
   - nike
   - puma
   - asics
   - hoka
   - saucony
3. TinyFish extracts normalized shoe data such as:
   - name
   - price
   - brand
   - weight
   - type
   - description
   - image source
   - product URL
   - foot shape
4. The script normalizes the data and upserts it into Supabase, defaulting to the `shoes` table.
5. This job can be run periodically, for example once every month, so users always receive recommendations based on the latest running shoe releases available in the database.

This is the key product loop now:

- TinyFish keeps the catalog fresh.
- Supabase stores the current normalized shoe inventory.
- The backend recommendation API filters that inventory in real time for each user.

## Why This Architecture

- Recommendation requests stay fast because they query a database instead of scraping live websites.
- TinyFish scraping is still valuable, but it happens on a controlled schedule instead of in the user request path.
- Monthly or periodic ingestion helps RunWise surface newly launched shoes and updated catalog entries without slowing down the app.
- Users get better recommendations because the database can be refreshed continuously as brands release new models.

## Directory Structure

```text
runwise/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── ShoeForm.astro
│   │   ├── layouts/
│   │   │   └── BaseLayout.astro
│   │   ├── pages/
│   │   │   ├── index.astro
│   │   │   └── results.astro
│   │   └── styles/
│   │       └── global.css
│   ├── package.json
│   └── astro.config.mjs
├── backend/
│   ├── main.py
│   ├── models/
│   │   └── schemas.py
│   ├── routes/
│   │   └── recommendations.py
│   ├── services/
│   │   ├── recommendation_pipeline.py
│   │   └── shoe_repository.py
│   ├── scripts/
│   │   ├── run_backend.py
│   │   ├── scrape_brand_catalog_to_supabase.py
│   │   ├── test_external_apis.py
│   │   ├── test_openai_api.py
│   │   └── test_supabase_shoes.py
│   └── requirements.txt
└── README.md
```

## API Contract

### `POST /recommend-shoes`

Request payload:

```json
{
  "budget": 180,
  "shoe_type": "daily trainer",
  "foot_shape": "neutral",
  "running_style": "midfoot",
  "preferences": [],
  "height_cm": 175,
  "weight_kg": 70,
  "weekly_mileage_km": 45,
  "experience_level": "intermediate",
  "max_results": 5
}
```

`brand` is also supported as an optional backend filter if added by the frontend later.

Response payload:

```json
{
  "recommendations": [
    {
      "name": "Novablast 5",
      "brand": "ASICS",
      "score": 100,
      "price_sgd": 189,
      "weight_grams": 252,
      "key_features": ["Price: S$189", "Type: daily trainer", "Weight: 252g"],
      "reason": "Matched your selected filters for budget under S$180, shoe type daily trainer, and foot shape neutral.",
      "best_for": "daily trainer",
      "image_source": "https://...",
      "sources": []
    }
  ],
  "metadata": {
    "targets_planned": 1,
    "items_scraped": 4,
    "items_normalized": 4
  }
}
```

## Environment Variables

Backend `.env` commonly includes:

```bash
OPENAI_API_KEY=
OPENAI_MODEL=
TINYFISH_API_KEY=
TINYFISH_BASE_URL=
GEMINI_API_KEY=
GEMINI_MODEL=
GEMINI_API_BASE=
SUPABASE_URL=
SUPABASE_API_KEY=
SUPABASE_TIMEOUT_SECONDS=
```

For the current recommendation backend, the important variables are:

- `SUPABASE_URL`
- `SUPABASE_API_KEY`
- `SUPABASE_TIMEOUT_SECONDS`

For the catalog refresh workflow, the important variables are:

- `TINYFISH_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_API_KEY`

## Run Locally

Open two terminals from the repo root.

### 1. Start Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/scripts/run_backend.py
```

If you prefer raw `uvicorn`, run it from the repo root:

```bash
uvicorn backend.main:app --reload
```

### 2. Start Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:4321`.

## Useful Test Scripts

### Test Supabase Recommendation Query

```bash
python backend/scripts/test_supabase_shoes.py
```

Example:

```bash
python backend/scripts/test_supabase_shoes.py --budget 180 --shoe-type "daily trainer" --foot-shape neutral --brand nike
```

### Test TinyFish + Google AI Studio APIs

```bash
python backend/scripts/test_external_apis.py
```

### Test OpenAI API Separately

```bash
python backend/scripts/test_openai_api.py
```

## Periodic TinyFish Sync

The catalog sync script is:

- [backend/scripts/scrape_brand_catalog_to_supabase.py](/Users/rogerzhang/github/tinyfish/backend/scripts/scrape_brand_catalog_to_supabase.py)

It supports:

- selecting brands with `--brands`
- controlling concurrency with `--concurrency`
- setting TinyFish timeout with `--timeout`
- outputting normalized JSON to a file
- uploading to Supabase with `--upload-to-supabase`
- selecting the target table with `--supabase-table`

Example monthly refresh command:

```bash
python backend/scripts/scrape_brand_catalog_to_supabase.py \
  --brands adidas nike puma asics hoka saucony \
  --upload-to-supabase \
  --supabase-table shoes \
  --timeout 300
```

This job is a good candidate for:

- a monthly cron job
- GitHub Actions on a schedule
- a server-side scheduler

Running it monthly ensures the `shoes` table stays updated with new model launches and catalog changes, so users get the latest shoes and stronger recommendations without waiting on live scraping during the recommendation request.

## Notes

- The recommendation API currently filters from the Supabase `shoes` table and returns all matches, not only 5.
- The frontend still uses the “Top 5” wording in the button, but the backend now returns all matching rows.
- `websites.md` and the older scraping services are no longer part of the main recommendation path.
