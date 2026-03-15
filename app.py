#!/usr/bin/env python3
"""
Web server entry point: form to submit Place ID, enqueue job, poll status, serve report.
Jobs are processed asynchronously by the RQ worker.
"""
import hashlib
import logging
import re
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from redis import Redis
from rq import Queue, Retry

from core.config import (
    OUTPUT_DIR,
    REDIS_URL,
    RQ_JOB_TIMEOUT,
    RQ_RETRY_INTERVALS,
    RQ_RETRY_MAX,
)
from core.db import create_job, get_job, init_db
from core.storage import LocalStorageService

app = Flask(__name__)
init_db()
_storage = LocalStorageService(OUTPUT_DIR)


def _safe_output_folder(place_id: str) -> str:
    """Return a filesystem-safe folder name for this place (ChIJ... or hash of URL/search)."""
    s = place_id.strip()
    if re.match(r"^ChIJ[\w-]+$", s):
        return s[:80]
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _get_queue():
    """Get the RQ default queue, connecting to Redis."""
    redis_conn = Redis.from_url(REDIS_URL)
    return Queue(connection=redis_conn)


@app.route("/")
def index():
    error = request.args.get("error")
    if error == "no_report":
        error = "No report yet. Run an analysis first."
    return render_template("index.html", error=error)


@app.route("/analyze", methods=["POST"])
def analyze():
    place_id = (request.form.get("place_id") or "").strip()
    if not place_id:
        return render_template("index.html", error="Please enter a Google Maps Place ID or URL.")

    place_folder = _safe_output_folder(place_id)
    job_id = create_job(place_id, place_folder)

    try:
        queue = _get_queue()
        queue.enqueue(
            "worker.process_job",
            str(job_id),
            place_id,
            timeout=RQ_JOB_TIMEOUT,
            retry=Retry(max=RQ_RETRY_MAX, interval=RQ_RETRY_INTERVALS),
        )
    except Exception as e:
        logging.exception("Failed to enqueue job")
        return render_template("index.html", error=f"Could not queue job: {e}")

    return redirect(url_for("status", job_id=job_id))


@app.route("/status/<int:job_id>")
def status(job_id):
    job = get_job(job_id)
    if not job:
        return render_template("status.html", job_id=job_id, job=None, error="Job not found"), 404
    return render_template("status.html", job_id=job_id, job=job)


@app.route("/api/status/<int:job_id>")
def api_status(job_id):
    """JSON endpoint for polling job status."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    data = {
        "job_id": job_id,
        "status": job["status"],
        "report_url": url_for("report", job_id=job_id) if job["status"] == "Completed" else None,
        "error_message": job["error_message"],
    }
    return jsonify(data)


@app.route("/report/<int:job_id>")
def report(job_id):
    report_path = _storage.get_report_path(job_id)
    if report_path is None:
        job = get_job(job_id)
        if job and job["status"] == "Failed":
            return redirect(url_for("index", error=job.get("error_message") or "Job failed."))
        return redirect(url_for("index", error="no_report"))
    return send_file(report_path, mimetype="text/html")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5001)
