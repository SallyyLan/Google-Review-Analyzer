# Step-by-Step: Development, Production, and Testing

Plain steps for running the app in development, deploying to production, and running tests.

---

## 1. Development (step-by-step)

Use this when you are coding on your machine and want to try the app locally.

### One-time setup

1. **Go to the project folder**
   ```bash
   cd /path/to/customer_review
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**
   - macOS/Linux: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\activate`

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Copy the example env file and add your keys**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set:
   - `OUTSCRAPER_API_KEY` (from [Outscraper](https://app.outscraper.com/profile))
   - `HF_TOKEN` (from [Hugging Face](https://huggingface.co/settings/tokens))

### Run the app (web flow)

6. **Start Redis** (in a separate terminal, leave it open)
   ```bash
   redis-server
   ```
   If Redis is not installed: install it (e.g. `brew install redis` on macOS) or use Docker: `docker run -d -p 6379:6379 redis:7-alpine`.

7. **Start the RQ worker** (in another terminal, leave it open)
   ```bash
   source .venv/bin/activate   # if not already activated
   rq worker
   ```

8. **Start the Flask app** (in a third terminal)
   ```bash
   source .venv/bin/activate
   python app.py
   ```

9. **Use the app**
   - Open a browser: http://localhost:5001
   - Enter a Place ID or Google Maps URL → click Analyze → wait on the status page → open the report when done.

### Run the app (CLI only, no Redis)

If you only want to run the pipeline from the command line (no web, no Redis):

```bash
source .venv/bin/activate
python run_pipeline.py "Place name or Google Maps URL"
```

Reports and artifacts go under `output/`.

---

## 2. Production (step-by-step)

Use this when you want to run the app for real users. Two options: **Docker** (simplest) or **manual** (e.g. on a VPS).

### Option A: Production with Docker (recommended)

1. **Install Docker and Docker Compose** on the server.

2. **Clone/copy the project** to the server (including `Dockerfile`, `docker-compose.yml`, `requirements.txt`, and app code). Do **not** commit `.env` with real keys; create it on the server.

3. **Create `.env` on the server** with production values:
   ```bash
   cp .env.example .env
   ```
   Set at least:
   - `OUTSCRAPER_API_KEY`
   - `HF_TOKEN`
   - Optionally `DATABASE_URL` for PostgreSQL, or keep SQLite (default).

4. **Set production env for the app** (e.g. in `docker-compose.yml` or a `.env` file):
   - `REDIS_URL=redis://redis:6379/0` (already set in docker-compose for the stack).

5. **Build and start everything**
   ```bash
   docker compose up -d --build
   ```
   This starts: Redis, the web app (Gunicorn on port 5001), and the RQ worker.

6. **Check that it runs**
   - Open http://YOUR_SERVER_IP:5001 (or your domain if you point it to port 5001).

7. **(Optional) Put Nginx in front** for HTTPS, static files, and a single port (80/443). Nginx proxies to `localhost:5001`. Configure SSL (e.g. Let’s Encrypt) and point your domain to the server.

### Option B: Production without Docker (manual)

1. **Prepare the server**: install Python 3.12, Redis, and (optional) PostgreSQL and Nginx.

2. **Clone the project** and create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Create `.env`** with production values (`OUTSCRAPER_API_KEY`, `HF_TOKEN`, `REDIS_URL`, and optionally `DATABASE_URL` for PostgreSQL).

4. **Run Redis** (e.g. as a system service): `redis-server` or `systemctl start redis`.

5. **Run the RQ worker** as a service (e.g. systemd unit or process manager like supervisord):
   ```bash
   rq worker --url $REDIS_URL
   ```

6. **Run the app with Gunicorn** (e.g. as a systemd service or behind Nginx):
   ```bash
   gunicorn -w 3 -b 0.0.0.0:5001 app:app
   ```

7. **(Optional) Put Nginx in front** to handle HTTPS and proxy to `127.0.0.1:5001`.

---

## 3. Testing (step-by-step)

The project can be tested with **pytest** and Flask’s **test client**. Tests live under `tests/`.

### One-time setup for testing

1. **Install test dependencies**
   ```bash
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```
   (This adds pytest and pytest-cov; Flask in `requirements.txt` provides the test client.)

2. **Optional:** use a separate `.env.test` or set env vars so tests don’t call real APIs or production DB. The sample test below uses the app’s test client and can mock the queue so Redis is not required during tests.

### Run tests

3. **Run all tests**
   ```bash
   pytest
   ```
   Or with coverage:
   ```bash
   pytest --cov=app --cov=core --cov-report=term-missing
   ```

4. **Run a single test file**
   ```bash
   pytest tests/test_app.py
   ```

5. **Run with verbose output**
   ```bash
   pytest -v
   ```

### What to test

- **Flask routes:** use `app.test_client()` to GET/POST and assert status codes and response content.
- **Core logic:** test `core.db`, `core.storage`, and helpers with real or in-memory DB/paths; mock external APIs (Outscraper, Hugging Face) so tests don’t hit them.
- **Pipeline:** run `run_pipeline` with a small CSV or mocked scraper to avoid real API calls in CI.

Adding more test files under `tests/` (names like `test_*.py`) will be discovered automatically by pytest.
