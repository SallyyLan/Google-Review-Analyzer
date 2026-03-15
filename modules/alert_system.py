"""
Calculate average rating per month; if current month drops by 0.5+ stars from previous month,
print and save "ALERT: Negative spike detected".
"""
from pathlib import Path

import pandas as pd


def monthly_avg_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """Expects date and rating. Returns DataFrame with month, avg_rating."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "rating"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    by_month = df.groupby("month")["rating"].mean().round(2).reset_index()
    return by_month.sort_values("month")


def check_alerts(df: pd.DataFrame) -> list[str]:
    """
    Compare most recent month's avg rating to previous month. If drop >= 0.5, return alert messages.
    """
    by_month = monthly_avg_ratings(df)
    messages = []
    if len(by_month) < 2:
        return messages
    current = by_month.iloc[-1]
    previous = by_month.iloc[-2]
    drop = previous["rating"] - current["rating"]
    if drop >= 0.5:
        prev_month = pd.Timestamp(previous["month"]).strftime("%Y-%m")
        curr_month = pd.Timestamp(current["month"]).strftime("%Y-%m")
        msg = (
            f"ALERT: Negative spike detected. "
            f"Average rating dropped from {previous['rating']} ({prev_month}) "
            f"to {current['rating']} ({curr_month})."
        )
        messages.append(msg)
        print(msg)
    return messages


def run_on_csv(csv_path: str | Path, output_path: str | Path | None = None) -> list[str]:
    """Read CSV (date, rating), check alerts, append to output_path if given."""
    df = pd.read_csv(csv_path)
    alerts = check_alerts(df)
    if output_path and alerts:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(alerts) + "\n", encoding="utf-8")
    return alerts
