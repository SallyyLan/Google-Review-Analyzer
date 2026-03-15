# How a User Request Flows Through the System

This document answers: (1) what we can tell from config, (2) Redis as message queue, (3) database choice, and (4) step-by-step which file is called when, from user click to report.

---

## 1. Can we know the web system structure from config?

**Partly.** From `core/config.py` you can see:

- **What the system uses:** database (SQLite or PostgreSQL via `DATABASE_URL`), Redis (`REDIS_URL`), a place to save reports (`OUTPUT_DIR`), and job rules (timeout, retries, review limit).
- **What you cannot see from config alone:** which URLs exist (e.g. `/`, `/analyze`, `/status/<id>`, `/report/<id>`), the order of steps, or which code talks to which service. For that you need to look at `app.py`, `worker.py`, and the rest of the code.

So: **config = “what” (addresses and numbers). The “how” (structure and flow) is in the application code.**

---

## 2. Are we using Redis for a message queue?

**Yes.** We use **Redis** as the broker and **RQ (Redis Queue)** as the library that implements the queue.

- When the user clicks “Analyze,” the web app does **not** run the long pipeline. It puts a **job** (e.g. “run analysis for job_id 5, place_id ChIJ…”) into Redis via RQ.
- A separate process, the **worker** (`rq worker`), listens to that queue, takes the job, and runs `worker.process_job()` (which runs the pipeline).
- So: **Redis = place where jobs wait. RQ = the “message queue” logic that puts jobs in and takes them out.**

---

## 3. Are we only using SQLite, not MySQL/PostgreSQL?

**By default, yes — we use SQLite only.** The app uses a single file database: `data/app.db` (path from `core/config.py`).

You **can** switch to PostgreSQL without changing application code: set `DATABASE_URL=postgresql://user:pass@host:5432/dbname` in `.env`. Then `core/db.py` (SQLAlchemy) uses that URL and talks to PostgreSQL instead. So: **right now = SQLite; optional = PostgreSQL via one env variable.**

---

## 4. How does a request go from the user to the result? (Which file is called first, then next?)

Below is the path for: **User submits a place → job is created and queued → worker runs the pipeline → user sees status and then the report.**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  USER BROWSER                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  1. User opens http://localhost:5001/
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  app.py  →  index()                                                             │
│  Uses: (none from DB/Redis here)                                                │
│  Returns: render_template("index.html")   ←  templates/index.html               │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  2. User enters Place ID/URL and clicks "Analyze"
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  app.py  →  analyze()                                                            │
│     │                                                                            │
│     ├─► core.db.create_job(place_id, place_folder)                              │
│     │      └─► core/db.py  uses  core/config.py  DATABASE_URL                    │
│     │          → SQLite (data/app.db): INSERT new row, get job_id                │
│     │                                                                            │
│     ├─► _get_queue()  uses  core/config.py  REDIS_URL                            │
│     │      → Redis connection                                                    │
│     │                                                                            │
│     └─► queue.enqueue("worker.process_job", job_id, place_id, timeout=..., retry)│
│            → Job is put in Redis (RQ default queue)                              │
│     Returns: redirect to /status/<job_id>                                        │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  3. Browser loads /status/<job_id>
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  app.py  →  status(job_id)                                                       │
│     └─► core.db.get_job(job_id)  →  SQLite: SELECT job  →  e.g. status="Pending"│
│     Returns: render_template("status.html", job=job)   ←  templates/status.html  │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  4. status.html runs JavaScript: every few seconds calls GET /api/status/<id>
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  app.py  →  api_status(job_id)                                                   │
│     └─► core.db.get_job(job_id)  →  SQLite: SELECT  →  { status, report_url }   │
│     Returns: JSON for the page (so it can show "Processing" or "Completed")      │
└─────────────────────────────────────────────────────────────────────────────────┘

    ═══════════════════════════════════════════════════════════════════════════════
    MEANWHILE: A separate process (the worker) is running. It watches Redis.
    ═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────────┐
│  RQ Worker process  (started by: rq worker)                                      │
│  Uses: core/config.py  REDIS_URL, OUTPUT_DIR, REVIEWS_LIMIT                      │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  5. Worker sees new job in Redis and calls the function enqueued by the app
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  worker.py  →  process_job(job_id, place_id)                                     │
│     │                                                                            │
│     ├─► core.db.get_recent_completed_job_for_place(place_id)  →  SQLite: SELECT │
│     │   (If same place was done in last 24h: copy that output, update job, done) │
│     │                                                                            │
│     ├─► core.db.update_job_status(job_id, "Processing")  →  SQLite: UPDATE      │
│     │                                                                            │
│     ├─► run_pipeline(place_query=place_id, output_dir=..., reviews_limit=...)    │
│     │      │                                                                     │
│     │      ├─► modules/review_scraper.py  fetch_reviews()  →  Outscraper API     │
│     │      ├─► modules/sentiment_analyzer.py  run_on_csv()  →  VADER             │
│     │      ├─► modules/theme_extractor.py  run_on_csv()    →  Hugging Face API   │
│     │      ├─► modules/visualizer.py  create_all_charts()  →  matplotlib        │
│     │      ├─► modules/summary_writer.py  generate_llm_summary()                 │
│     │      ├─► modules/time_analyzer.py  run_on_csv()                            │
│     │      ├─► modules/alert_system.py  run_on_csv()                              │
│     │      └─► modules/report_generator.py  generate_html_report()  →  HTML     │
│     │                                                                            │
│     ├─► core.storage.LocalStorageService.save_report(job_id, report_html)       │
│     │      → Writes output/<job_id>/report.html  (uses core/config OUTPUT_DIR)   │
│     │                                                                            │
│     └─► core.db.update_job_status(job_id, "Completed", report_path=...)         │
│            → SQLite: UPDATE job set status='Completed', report_path=...         │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  Next time the browser polls /api/status/<id>, get_job() returns "Completed"
    │  and report_url is set, so the page can show "View report".
    │
    │  6. User clicks "View report" (or the link from the status page)
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  app.py  →  report(job_id)                                                       │
│     ├─► core.storage.LocalStorageService.get_report_path(job_id)                │
│     │      → Path to output/<job_id>/report.html  (from config OUTPUT_DIR)       │
│     └─► send_file(report_path)  →  browser displays the HTML report             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary table: who uses what

| File / component      | Reads config          | Uses DB (SQLite)     | Uses Redis   | Uses storage (files)   |
|----------------------|----------------------|----------------------|-------------|------------------------|
| app.py               | REDIS_URL, OUTPUT_DIR, RQ_* | create_job, get_job  | enqueue job | get_report_path        |
| worker.py            | OUTPUT_DIR, REVIEWS_LIMIT   | get_job, update_job_status, get_recent_* | (dequeues job) | save_report, output dir |
| core/db.py           | DATABASE_URL, DATABASE_PATH | ✓ (all job CRUD)     | —           | —                      |
| core/storage.py      | (receives OUTPUT_DIR from caller) | —                    | —           | ✓ (report.html)        |
| run_pipeline.py      | (receives paths/limits from worker) | —                    | —           | writes CSVs, charts, report (then worker passes HTML to storage) |

So: **config** tells everyone *where* the database, Redis, and output folder are; **app.py** and **worker.py** are the ones that actually connect and call **core/db.py** and **core/storage.py** (and **run_pipeline** → **modules/**) in the order above.
