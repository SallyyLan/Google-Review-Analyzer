# Customer Review Analysis — MVP Report

Single reference for users, problem, solution, user flow, technology map, design decisions within business constraints, and future scaling hooks.

---

## 1. Who are the users

- **Primary:** Small and medium businesses (SMBs)—single-location restaurants, local shops, salons, service providers—that care about their Google Maps reputation and want to act on customer feedback.
- **Secondary:** Operators or marketers who need a quick, shareable summary of review sentiment and themes without reading hundreds of reviews or hiring a data team.

---

## 2. Challenges they faced

- **No time or expertise:** Cannot manually read and summarize large volumes of reviews; no in-house data or analytics team.
- **Cost and efficiency:** Paying for APIs (e.g. review data, LLM) makes duplicate work (re-analyzing the same place repeatedly) expensive and slow.
- **Unreliable tooling:** External APIs (scraping, inference) can fail or hang; jobs that never finish or never retry hurt trust and usability.
- **Scaling later:** Today one app and one disk; tomorrow multiple servers or object storage—design should allow switching DB and storage without rewrites.

---

## 3. How this project solves them

- **One report per place:** User submits a Google Maps place (URL, Place ID, or search). The system fetches reviews, runs sentiment and theme extraction, and produces a single executive-style HTML report: sentiment mix, strength drivers, operational risks, LLM-derived themes with evidence, and recommended actions (high / medium / quick-win). No manual reading; insights in minutes.
- **Cost and speed:** A 24-hour cache by place means repeat requests for the same location reuse the last result—no extra scrape or LLM calls—reducing API cost and returning a result in milliseconds.
- **Reliability:** Jobs run with a timeout and a retry policy (e.g. 3 retries with exponential backoff). Transient API failures are retried; stuck jobs are failed so the worker can take the next one.
- **Scaling hooks:** Database is behind an ORM and a single connection string (switch to PostgreSQL in one line). Reports go through a storage interface (local today; S3/GCS later). Caching and retries are built in.

---

## 4. User flow

- **Web:** User opens the app → enters Google Maps Place ID or full URL → submits → job is created and enqueued → redirect to status page → page polls until status is Completed or Failed → user opens or downloads the report. If the same place was completed in the last 24 hours, the new job is served from cache (no new scrape or LLM).
- **CLI:** User runs `python run_pipeline.py "Place or URL"` (or `--csv path/to/reviews.csv`). Pipeline runs; report and artifacts are written under `output/` (or `--output-dir`). No Redis required; useful for automation or local runs.

---

## 5. Technologies and libraries — where used, why, and future expansion

| Technology / library | Part of system | Why used | Future expansion (hook) |
|----------------------|----------------|----------|-------------------------|
| **Flask** | Web app (`app.py`) | Routes: `/` (form), `/analyze` (create job, enqueue), `/status/<id>`, `/api/status/<id>` (polling), `/report/<id>`. Minimal surface; easy to run behind Gunicorn. | Add auth, rate limiting; optional REST API. |
| **SQLAlchemy** | Job persistence (`core/db.py`, `core/models.py`) | ORM + single `DATABASE_URL`. Same code for SQLite (default) and PostgreSQL. | **Hook:** Set `DATABASE_URL=postgresql://...` in `.env` for production; no code change. |
| **Redis** | Job queue | Broker for RQ; job payloads and state. | Connection pooling; multiple queues (e.g. priority). |
| **RQ** | Async workers | App enqueues `worker.process_job` with timeout and retry; workers run the pipeline. | **Hook:** Timeout and retries already configured; add dead-letter handling, monitoring. |
| **Outscraper** | Scraping (`modules/review_scraper.py`) | Google Maps review API → CSV (date, rating, review_text). Avoids custom scraping. | Throttle/concurrency; optional caching beyond 24h. |
| **VADER** (vaderSentiment) | Sentiment (`modules/sentiment_analyzer.py`) | Per-review positive/neutral/negative. Fast, no training; good for short informal text. | Optional: train or plug another model. |
| **Hugging Face** (Qwen, Inference API) | Themes & summary (`modules/theme_extractor.py`, `modules/llm_client.py`) | Structured themes, 4-sentence summary, high/medium/quick-win actions. Single API; no self-hosted model. | Model swap via config; fallback (e.g. rule-based) on outage. |
| **pandas** | Analytics | Aggregation, monthly trends, CSV handling. | — |
| **matplotlib / seaborn** | Charts | Sentiment bar, phrase bars, 6‑month trend. PNGs embedded in report. | Offload charting to separate worker if needed. |
| **StorageService** | Report read/write (`core/storage.py`) | Abstract interface: `save_report(job_id, html)`, `get_report_path(job_id)`. Local implementation writes to `output/<job_id>/report.html`. | **Hook:** Implement S3 or GCS backend so multiple web nodes serve reports without shared disk. |
| **24h cache by place_id** | Worker (`worker.py`) + `core/db.py` | Before running pipeline, check for a completed job for same place in last 24h; if found, reuse output and mark new job completed. | **Hook:** Configurable TTL; optional "cached" badge in UI; cache invalidation. |
| **python-dotenv** | Config (`core/config.py`) | Load `.env` from project root. Secrets and flags in one place. | — |
| **Docker Compose** | Deployment | Web, worker, Redis; volumes for output and DB. | Add PostgreSQL service; optional S3 volume or env. |
| **Gunicorn** | Production WSGI | Multi-worker process for Flask. | Tune workers; reverse proxy (Nginx/Caddy). |

---

## 6. Tech stack decisions and business constraints

Decisions were made to ship a working MVP quickly while keeping the door open for production scale. Rationale:

| Decision | Constraint / goal | Judgment |
|----------|-------------------|----------|
| **SQLite by default** | Zero-ops setup, no DB server to run; single developer or small team. | Use SQLAlchemy + single `DATABASE_URL` so production can switch to PostgreSQL via env only—no code change. |
| **Flask over Django** | Minimal surface: a few routes, form, status, report. No need for admin, ORM migrations, or built-in auth. | Flask keeps the app small and easy to reason about; Gunicorn handles production concurrency. |
| **RQ over Celery** | Need a simple job queue with timeout and retries; Redis already acceptable as a dependency. | RQ is lighter and sufficient for one queue and one worker type; Celery can be introduced later if we need multiple queues or more complex routing. |
| **VADER for sentiment** | No labeled data, no ML training; must work out of the box on short, informal review text. | Rule-based and fast; good enough for SMB dashboards. A custom or fine-tuned model can be plugged in later if accuracy becomes a product requirement. |
| **Hugging Face Inference API for themes** | Need themes and actionable summary without hosting or fine-tuning an LLM. | Single API, pay-per-use; model can be swapped via config or replaced with a fallback if the API is down. |
| **StorageService abstraction** | Today: one server, local disk. Later: multiple web nodes or serverless. | Interface with a local implementation; add S3/GCS backend when moving to multi-node or cloud storage. |
| **Polling for status** | Need to show job progress without adding WebSockets or SSE infrastructure. | Polling is simple and works with any deployment; real-time updates can be added when UX or scale justifies the extra complexity. |
| **Single-tenant, no auth in MVP** | Validate the product and flow first; multi-tenant and auth add scope and security surface. | Ship fast; add auth and per-user quotas when moving to a paid or multi-tenant offering. |

---

## 7. Project layout (after reorganization)

```
├── app.py                 # Flask entry point
├── worker.py              # RQ job entry point (process_job)
├── run_pipeline.py        # CLI pipeline entry point
├── core/
│   ├── config.py          # OUTPUT_DIR, DATABASE_URL, REDIS_URL, RQ timeout/retry, REVIEWS_LIMIT
│   ├── db.py              # Job CRUD, get_recent_completed_job_for_place
│   ├── models.py          # SQLAlchemy Job model
│   └── storage.py         # StorageService, LocalStorageService
├── modules/
│   ├── review_scraper.py  # Outscraper → CSV
│   ├── sentiment_analyzer.py
│   ├── theme_extractor.py # LLM themes, summary, actions
│   ├── llm_client.py      # Hugging Face InferenceClient
│   ├── summary_writer.py
│   ├── time_analyzer.py   # Trend chart, monthly_reviews.csv
│   ├── alert_system.py    # Rating-drop alerts
│   ├── visualizer.py      # Bar charts
│   └── report_generator.py # Executive HTML report
├── templates/             # index.html, status.html
├── tests/                 # test_app.py (Flask routes, status, report)
├── docs/                  # This report, REQUEST_FLOW.md, SERVERS_AND_FILES.md
├── output/                # Per-job reports and artifacts (gitignored)
├── data/                  # SQLite DB (gitignored)
├── .env.example
└── requirements.txt
```

---

## 8. Future scaling hooks

The MVP is scoped to prove value and flow; the following are deliberate extension points for when requirements grow:

| Area | Current scope (MVP) | Scaling hook |
|------|---------------------|--------------|
| **Identity & access** | Single-tenant; no login. | Add auth (e.g. OAuth or session-based); per-user quotas and rate limits. |
| **Rate limiting** | No app-level throttling; cost tied to traffic and API limits. | Add rate limiting (per IP or per user) and optional queue prioritization. |
| **Status updates** | Polling only. | Add WebSockets or SSE for live status when UX or scale justifies it. |
| **Retention & cleanup** | No automatic purge of old jobs or reports. | Add retention policy and cron (or worker task) to delete or archive old data. |
| **Observability** | Errors surfaced as generic messages. | Add structured logging, correlation IDs, and alerting (e.g. failed job count, API errors). |

The architecture (ORM, storage interface, config-driven URLs, timeout/retry) is already aligned with these hooks so that scaling does not require rewrites.

---

## 9. Quick start (summary)

1. **Install:** `python -m venv .venv`, activate, `pip install -r requirements.txt`
2. **Configure:** Copy `.env.example` to `.env`; set `OUTSCRAPER_API_KEY`, `HF_TOKEN`. Optional: `REDIS_URL`, `DATABASE_URL`, `RQ_JOB_TIMEOUT`, `RQ_RETRY_MAX`, `RQ_RETRY_INTERVALS`
3. **CLI:** `python run_pipeline.py "Place or URL"` → report under `output/`
4. **Web:** Start Redis → `rq worker` → `python app.py` (or `gunicorn -w 3 -b 0.0.0.0:5001 app:app`) → open http://localhost:5001

---

## 10. Key deliverables (portfolio)

- **End-to-end product:** Web and CLI entry points; one report per place with sentiment, themes, and recommended actions.
- **Async job pipeline:** Queue (RQ + Redis), timeout, retries, and 24h cache to control cost and improve reliability.
- **Abstraction for scale:** Database behind ORM and `DATABASE_URL`; report storage behind `StorageService`; config-driven timeouts and retry intervals.
- **Documentation:** This report (users, solution, tech map, design rationale, scaling hooks), plus request flow and server/file map in `docs/`.
- **Tests:** Flask app tests (e.g. `tests/test_app.py`) for critical web paths.

This document is the single place for who the product is for, what problem it solves, how users interact with it, which technologies are used where and why, how choices were made within business constraints, and how the current design supports future expansion (DB, storage, cache, retries, auth, observability).
