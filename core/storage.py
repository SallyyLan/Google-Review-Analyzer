"""
Stateless storage interface for reports. Local implementation writes to disk;
can be swapped for S3/GCS when running multiple web nodes.
"""
from pathlib import Path


class StorageService:
    """Abstract interface: save and retrieve report by job_id."""

    def save_report(self, job_id: int, report_html: str) -> str | Path:
        """Save report HTML for this job. Returns path or URL."""
        raise NotImplementedError

    def get_report_path(self, job_id: int) -> Path | None:
        """Return path to report file if it exists (for send_file); None otherwise."""
        raise NotImplementedError


class LocalStorageService(StorageService):
    """Writes reports to OUTPUT_DIR/job_id/report.html. Ready to swap for S3/GCS."""

    def __init__(self, output_dir: str | Path):
        self._root = Path(output_dir)

    def save_report(self, job_id: int, report_html: str) -> Path:
        """Write report to output_dir/job_id/report.html."""
        report_path = self._root / str(job_id) / "report.html"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_html, encoding="utf-8")
        return report_path

    def get_report_path(self, job_id: int) -> Path | None:
        """Return path if report exists."""
        p = self._root / str(job_id) / "report.html"
        return p if p.exists() else None
