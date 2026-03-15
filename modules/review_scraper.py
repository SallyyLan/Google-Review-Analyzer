"""
Fetch Google Maps reviews via Outscraper API. Accepts place URL, place ID, or search string.
Maps API response to CSV schema: date (YYYY-MM-DD), rating, review_text.
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Optional: only require outscraper when actually calling the API
try:
    from outscraper import OutscraperClient
except ImportError:
    OutscraperClient = None  # type: ignore[misc, assignment]

EMPTY_COLUMNS = ["date", "rating", "review_text"]


def _normalize_date(value: Any) -> str:
    """Convert review date to YYYY-MM-DD from datetime string or timestamp."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return datetime.utcnow().strftime("%Y-%m-%d")

    if isinstance(value, (int, float)):
        try:
            dt = datetime.utcfromtimestamp(int(value))
            return dt.strftime("%Y-%m-%d")
        except (OSError, ValueError):
            return datetime.utcnow().strftime("%Y-%m-%d")

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    s = str(value).strip()
    # Outscraper may return "01/31/2021 15:38:38" (MM/DD/YYYY HH:MM:SS)
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            if " " in fmt:
                dt = datetime.strptime(s[:19].strip(), fmt)
            else:
                dt = datetime.strptime(s[:10].strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # ISO-like
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return datetime.utcnow().strftime("%Y-%m-%d")


def _normalize_rating(value: Any) -> int | None:
    """Return 1–5 rating or None."""
    if value is None:
        return None
    try:
        n = int(float(value))
        return min(5, max(1, n)) if n else None
    except (TypeError, ValueError):
        return None


def _reviews_from_place(place: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten reviews_data from one place object into rows with date, rating, review_text."""
    rows = []
    reviews_data = place.get("reviews_data") or place.get("reviewsData") or []
    for r in reviews_data:
        if not isinstance(r, dict):
            continue
        text = r.get("review_text") or r.get("reviewText") or ""
        if not isinstance(text, str):
            text = str(text or "").strip()
        # Optional: skip empty review text if we want only reviews with text
        date_raw = r.get("review_datetime_utc") or r.get("review_timestamp") or r.get("reviewTimestamp")
        date_str = _normalize_date(date_raw)
        rating = _normalize_rating(r.get("review_rating") or r.get("reviewRating"))
        rows.append({
            "date": date_str,
            "rating": rating if rating is not None else "",
            "review_text": text,
        })
    return rows


def fetch_reviews(
    place_query: str,
    reviews_limit: int = 100,
    language: str = "en",
) -> pd.DataFrame:
    """
    Fetch Google Maps reviews via Outscraper API.

    Accepts place_query: Google Maps URL, place ID (ChIJ...), or search string
    (e.g. "Double Chicken Please, NY"). Returns a DataFrame with columns
    date (YYYY-MM-DD), rating, review_text.

    Raises ValueError if OUTSCRAPER_API_KEY is missing. On API/network errors
    or empty/malformed response, returns empty DataFrame with correct columns.
    """
    api_key = os.environ.get("OUTSCRAPER_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "OUTSCRAPER_API_KEY is not set. Set it in .env or environment. "
            "Get your key from https://app.outscraper.com/profile"
        )

    if OutscraperClient is None:
        raise ImportError("outscraper package is required. Install with: pip install outscraper")

    client = OutscraperClient(api_key=api_key)

    try:
        result = client.google_maps_reviews(
            place_query,
            reviews_limit=reviews_limit,
            limit=1,
            language=language,
        )
    except Exception as e:
        raise RuntimeError(f"Outscraper API request failed: {e}") from e

    # Result: list of place objects (single query -> one or zero items)
    if not result:
        return pd.DataFrame(columns=EMPTY_COLUMNS)

    places = result if isinstance(result, list) else [result]
    all_rows: list[dict[str, Any]] = []
    for place in places:
        if not isinstance(place, dict):
            continue
        all_rows.extend(_reviews_from_place(place))

    if not all_rows:
        return pd.DataFrame(columns=EMPTY_COLUMNS)

    df = pd.DataFrame(all_rows)
    # Ensure columns order and types for downstream (time_analyzer uses pd.to_datetime(df["date"]))
    df = df[EMPTY_COLUMNS]
    return df


def save_reviews_csv(df: pd.DataFrame, path: str | Path) -> Path:
    """Save reviews DataFrame to CSV (date, rating, review_text)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    return p
