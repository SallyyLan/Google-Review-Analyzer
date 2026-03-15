"""
RQ worker entry point. Runs the pipeline for enqueued jobs.
Usage: rq worker (or: python -m rq.cli worker)
Ensure REDIS_URL is set and points to Redis.
"""
import shutil
from pathlib import Path

from run_pipeline import run_pipeline

from core.config import OUTPUT_DIR, REVIEWS_LIMIT
from core.db import get_recent_completed_job_for_place, update_job_status
from core.storage import LocalStorageService

CACHE_WITHIN_HOURS = 24
_storage = LocalStorageService(OUTPUT_DIR)


def process_job(job_id: str, place_id: str) -> None:
    """
    Run the pipeline for a job. Called by RQ worker.
    job_id: string (from queue)
    place_id: the Place ID or URL to analyze
    """
    job_id = int(job_id)
    output_dir = Path(OUTPUT_DIR) / str(job_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Idempotency: reuse result if same place was completed in the last 24h
        cached = get_recent_completed_job_for_place(place_id, within_hours=CACHE_WITHIN_HOURS)
        if cached and cached["id"] != job_id:
            cached_dir = Path(OUTPUT_DIR) / str(cached["id"])
            if cached_dir.exists() and (cached_dir / "report.html").exists():
                shutil.copytree(cached_dir, output_dir, dirs_exist_ok=True)
                report_html = (output_dir / "report.html").read_text(encoding="utf-8")
                _storage.save_report(job_id, report_html)
                report_path = _storage.get_report_path(job_id)
                update_job_status(job_id, "Completed", report_path=str(report_path) if report_path else None)
                return

        update_job_status(job_id, "Processing")
        success, report_path, error_message, report_html = run_pipeline(
            place_query=place_id,
            output_dir=output_dir,
            reviews_limit=REVIEWS_LIMIT,
        )
        if success and report_html:
            _storage.save_report(job_id, report_html)
            report_path = _storage.get_report_path(job_id)
            update_job_status(job_id, "Completed", report_path=str(report_path) if report_path else None)
        elif success and report_path:
            update_job_status(job_id, "Completed", report_path=str(report_path))
        else:
            update_job_status(job_id, "Failed", error_message=error_message or "Pipeline failed")
    except Exception as e:
        update_job_status(job_id, "Failed", error_message=str(e))
        raise
