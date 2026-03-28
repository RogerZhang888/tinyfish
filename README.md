# RunWise MVP

RunWise is an intelligent running shoe recommendation platform that combines:

- Profile-aware user input
- TinyFish-driven web scraping
- Data normalization and aggregation
- LLM-assisted planning and recommendation ranking

## Architecture (MVP)

### End-to-End Flow

1. User fills the Astro form with budget, biomechanics, and preferences.
2. Frontend sends `POST /recommend-shoes` to FastAPI.
3. Backend pipeline executes in order: Planner reads allowed targets from `websites.md`; TinyFish Agent executes scraping for each target (mock implementation now); Aggregator deduplicates shoes and normalizes noisy fields; Ranker scores candidates against user profile and optionally asks OpenAI to refine explanations.
4. API returns top recommendations plus pipeline metadata.
5. Results page renders top 5 shoes with reasons, features, and source links.

### Directory Structure

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
│   │   ├── planner.py
│   │   ├── tinyfish_agent.py
│   │   ├── aggregator.py
│   │   ├── ranker.py
│   │   ├── openai_client.py
│   │   └── recommendation_pipeline.py
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
  "preferences": ["high cushioning", "lightweight"],
  "height_cm": 175,
  "weight_kg": 70,
  "weekly_mileage_km": 45,
  "experience_level": "intermediate",
  "max_results": 5
}
```

Response payload:

```json
{
  "recommendations": [
    {
      "name": "Novablast 5",
      "brand": "ASICS",
      "score": 91,
      "key_features": ["Cushioning: high", "Weight: 252g"],
      "reason": "...",
      "best_for": "...",
      "sources": ["https://..."]
    }
  ],
  "metadata": {
    "targets_planned": 3,
    "items_scraped": 18,
    "items_normalized": 6
  }
}
```

## Run Locally

Open two terminals from the `runwise` directory.

### 1. Start Backend (FastAPI)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

Optional for OpenAI enhancement:

```bash
cp backend/.env.example backend/.env
# set OPENAI_API_KEY in backend/.env
```

Optional for TinyFish enhancement:

```bash
# set TINYFISH_API_KEY in backend/.env
```

### 2. Start Frontend (Astro)

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:4321`.

## Notes For Future Integration

- Keep all allowed scrape domains in `websites.md`. The planner only uses websites listed there.
- Replace `TinyFishScraperAgent.scrape()` with a real TinyFish browser session and extraction prompts.
- Keep `QueryPlanner` and `ShoeRanker` contracts stable so LLM prompts can evolve independently.
- Extend `ScrapedShoeData` with durability, drop, stack height, and terrain metadata.
