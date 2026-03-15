# Customer Review Analysis — MVP

Analyze Google Maps reviews for a place: fetch reviews (Outscraper), run sentiment and theme analysis (VADER + Hugging Face), and generate an executive-style HTML report with charts, themes, and recommended actions.

**Full product and technical report:** [docs/MVP_REPORT.md](docs/MVP_REPORT.md) — users, challenges, how the project solves them, user flow, and a technology table with where each library is used and future expansion hooks.

---

## Quick start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Set in `.env`:

- **OUTSCRAPER_API_KEY** — [Outscraper profile](https://app.outscraper.com/profile)
- **HF_TOKEN** — [Hugging Face token](https://huggingface.co/settings/tokens)

Optional: `REDIS_URL`, `OUTPUT_DIR`, `REVIEWS_LIMIT`, `DATABASE_URL` (default SQLite), `RQ_JOB_TIMEOUT`, `RQ_RETRY_MAX`, `RQ_RETRY_INTERVALS`.

### 3a. CLI (no Redis)

```bash
python run_pipeline.py "Place name or Google Maps URL"
```

Report and artifacts under `output/`. Use `--csv path/to/reviews.csv` to skip scraping; `--scrape` to force re-scrape.

### 3b. Web (Flask + Redis + RQ worker)

1. Start Redis: `redis-server`
2. Start worker: `rq worker` (jobs use timeout and retries; keep terminal open)
3. Start app: `python app.py` (or `gunicorn -w 3 -b 0.0.0.0:5001 app:app`)
4. Open http://localhost:5001 → enter Place ID or URL → Analyze → status page → open report when done.

---

## Project layout

```
├── app.py              # Flask: form, enqueue, status, report
├── worker.py           # RQ job: run_pipeline per job
├── run_pipeline.py     # CLI pipeline
├── core/               # Config, DB, models, storage
├── modules/            # Scraper, sentiment, themes, LLM, charts, report
├── templates/          # index.html, status.html
├── docs/MVP_REPORT.md  # Full report (users, challenges, solution, tech table)
├── .env.example
└── requirements.txt
```

---

## License

Use as a portfolio/demo project. Outscraper and Hugging Face have their own terms and rate limits.
