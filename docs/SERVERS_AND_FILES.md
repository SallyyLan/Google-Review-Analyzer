# Servers and Files — Simple Guide

Plain-English answers and a map of which files do what in this project.

---

## 1. Do Django/Flask already contain the application server and web server, controlled by Gunicorn?

**Short answer:** Not quite. Here’s the simple version.

- **Django and Flask** are **frameworks**. They are like a big box of tools that help you write your app: pages, forms, database code, etc. They do **not** by themselves “listen” on the internet for visitors. So the framework is your **application** (your logic), not the server.

- **Gunicorn** is a separate program. It is the **application server**. Its job is to **run** your Django or Flask app and to **talk to the internet**: receive requests and send back responses. So:
  - **Flask/Django** = your app (the code you write).
  - **Gunicorn** = the thing that runs your app and handles HTTP. So the “application server” is Gunicorn, not inside the framework.

- **Web server** (in the strict sense) often means something like **Nginx** or **Apache**. They serve static files (images, CSS) and can send other requests to Gunicorn. In this project we don’t use Nginx; Gunicorn does both: it runs the app and serves the HTTP traffic. So here, “web server” and “application server” are the same program: Gunicorn (or Flask’s built-in dev server when you run `python app.py`).

**Corrected summary:** The framework (Flask/Django) is your **application**. Gunicorn is the **application server** that runs that application. The framework does not “contain” the server; Gunicorn is a separate program that runs the framework.

---

## 2. Without a framework, do we have to design application and web server? With a framework, do we not separate them?

- **If you do NOT use a framework:** You have to build more yourself: how to read requests, how to decide which code runs for which URL, how to send responses. You could still use Gunicorn to run your code (if you speak WSGI), but you’d be writing a lot of “plumbing” that Django/Flask give you for free. So yes: without a framework you have to design both your application logic and how it’s served (or use something like Gunicorn to do the serving).

- **If you DO use a framework:** The framework gives you the **application** (routes, logic, templates). You don’t build a full HTTP server from scratch; you use an application server like **Gunicorn** to run your app and handle HTTP. So you don’t “separate” them in the sense of building two different programs yourself — the framework is the app, Gunicorn is the server that runs it. But the **application** (your Flask code) and the **application server** (Gunicorn) are still two different things: one is your code, one is the program that runs your code.

**Summary:** With a framework you don’t have to design a web server from scratch; you use Gunicorn (or similar) to run your app. The “application” and “application server” are still separate ideas, but you don’t build the server part yourself.

---

## 3. Map: Which file is which part of the system?

| Part of the system        | What it does in simple words                    | File(s) in this project |
|---------------------------|--------------------------------------------------|--------------------------|
| **Application**           | Your app logic: pages, forms, when to run jobs  | `app.py` (Flask app: routes, enqueue, status, report) |
| **Application server**    | Runs the app and talks to the internet (HTTP)   | **Not a file.** Gunicorn when you run `gunicorn ... app:app`, or Flask’s dev server when you run `python app.py`. |
| **Worker**                | Picks up jobs from the queue and runs the heavy work (scrape, analyze, report) | `worker.py` (run by `rq worker`) |
| **Database layer**        | Saves and loads jobs (place, status, report path) | `core/db.py`, `core/models.py` |
| **Config**                | Where we keep settings (Redis URL, paths, timeouts) | `core/config.py` |
| **Storage**               | Saves and loads the report HTML files           | `core/storage.py` |
| **Pipeline**              | The full analysis: scrape → sentiment → themes → report | `run_pipeline.py` + everything in `modules/` |
| **Queue (Redis)**         | Holds jobs until the worker is ready             | **Not a file.** Redis is a separate program (or Docker service). |
| **Templates**             | HTML for the form and status page               | `templates/index.html`, `templates/status.html` |

So in this project:

- **`app.py`** = the **application** (the Flask app: form, enqueue, status, report). When we run it with Gunicorn or `python app.py`, that **process** is what acts as the application server (and in this project, the only HTTP server).
- **`worker.py`** = the **worker** (background jobs).
- **`core/db.py`** and **`core/models.py`** = **database**.
- **`core/config.py`** = **config**.
- **`core/storage.py`** = **storage** for reports.
- **`run_pipeline.py`** + **`modules/`** = the **pipeline** (the actual analysis).

No single file “is” the application server; the application server is the **program** (Gunicorn or Flask’s dev server) that runs `app.py`.

---

## 4. Production, web server vs application server, and when to separate

### In production: web server necessary? Application server necessary?

- **Application server (e.g. Gunicorn) is necessary.** Something must run your app and handle HTTP. In production that is usually Gunicorn (or uWSGI, etc.).
- **A separate web server (e.g. Nginx) is not strictly necessary.** You can run only Gunicorn; it will accept HTTP and serve your app. So: **web server optional, application server required.**

### Gunicorn alone vs Nginx + Gunicorn

- **Gunicorn can do both:** accept HTTP and run your app. So one process can be enough.
- **It is fine — and often better — to separate:** put **Nginx** in front as the web server and **Gunicorn** as the application server. Nginx receives requests first, can serve static files and handle SSL, then forwards to Gunicorn for your app.

### Chain, not hierarchy

- These pieces form a **chain**: the request passes from one to the next. User → (optional Nginx) → Gunicorn → your app → your app may call DB, Redis, etc. So it is not a hierarchy of layers; it is a **chain** that passes the request (and response) from one component to another.

### When and why separate web server and application server?

**When to separate (add Nginx in front of Gunicorn):**

- **Traffic / many connections:** Nginx is built to handle many simultaneous connections and to proxy to one or more Gunicorn workers.
- **Static files:** Nginx is very good at serving images, CSS, JS from disk; you don't want Gunicorn doing that for thousands of files.
- **SSL/HTTPS:** Often SSL is terminated at Nginx (it talks HTTPS to the user, HTTP to Gunicorn), which is simpler and offloads work from the app server.
- **Security:** Nginx can hide Gunicorn (only Nginx is exposed); you can add rate limiting, blocking, etc. in one place.
- **One entry point for many apps:** One Nginx can route to several apps (different Gunicorn processes or other backends).

**When Gunicorn alone might be enough:**

- Small or internal apps, low traffic, no need for Nginx's strengths yet. You can add Nginx later when you need it.

**Summary:** You decide based on **traffic, static files, SSL, security, and scaling**. You separate so that **Nginx** does what it's best at (connections, static files, SSL, proxy) and **Gunicorn** does what it's best at (running your Python app). Each program has a clear job; together they form a chain.
