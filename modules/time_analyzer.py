"""
Group reviews by month, count positive/negative per month, create line chart of sentiment trend (last 6 months).
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set_style("whitegrid")


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def analyze_trends(df: pd.DataFrame, last_n_months: int = 6) -> pd.DataFrame:
    """
    Expects date (YYYY-MM-DD) and sentiment_score. Returns DataFrame with one row per month:
    month, positive, negative, neutral, total, pct_positive.
    """
    if df.empty:
        return pd.DataFrame(columns=["month", "positive", "negative", "neutral", "total", "pct_positive"])
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if df.empty:
        return pd.DataFrame(columns=["month", "positive", "negative", "neutral", "total", "pct_positive"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    by_month = df.groupby("month").agg(
        positive=("sentiment_score", lambda s: (s == "positive").sum()),
        negative=("sentiment_score", lambda s: (s == "negative").sum()),
        neutral=("sentiment_score", lambda s: (s == "neutral").sum()),
    ).reset_index()
    by_month["total"] = by_month["positive"] + by_month["negative"] + by_month["neutral"]
    total_safe = by_month["total"].replace(0, 1).astype(float)
    by_month["pct_positive"] = (100 * by_month["positive"].astype(float) / total_safe).round(1)
    by_month = by_month.sort_values("month")
    # last N months
    if len(by_month) > last_n_months:
        by_month = by_month.tail(last_n_months)
    return by_month


def create_trend_chart(by_month: pd.DataFrame, output_path: str | Path) -> None:
    """Line chart: x = month, y = % positive (and optionally negative)."""
    if by_month.empty:
        fig, ax = plt.subplots()
        ax.set_title("Sentiment trend (last 6 months)")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(by_month["month"].astype(str), by_month["pct_positive"], marker="o", label="% positive", color="#2ecc71")
    ax.plot(by_month["month"].astype(str), 100 - by_month["pct_positive"], marker="s", label="% non-positive", color="#e74c3c", alpha=0.7)
    ax.set_title("Sentiment trend over last 6 months")
    ax.set_ylabel("Percentage")
    ax.set_xlabel("Month")
    ax.legend()
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    p = Path(output_path)
    _ensure_dir(p)
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()


def run_on_csv(csv_path: str | Path, output_path: str | Path, last_n_months: int = 6) -> pd.DataFrame:
    """
    Read CSV, compute monthly trend, save line chart, and write a monthly
    aggregation CSV (for future time series analysis).
    """
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)
    by_month = analyze_trends(df, last_n_months=last_n_months)
    create_trend_chart(by_month, output_path)

    # Write a monthly aggregate CSV with year/year_month columns.
    if not by_month.empty:
        monthly = by_month.copy()
        monthly["year"] = monthly["month"].dt.year
        monthly["year_month"] = monthly["month"].dt.to_period("M").astype(str)
        monthly_path = csv_path.parent / "monthly_reviews.csv"
        monthly.to_csv(monthly_path, index=False)

    return by_month
