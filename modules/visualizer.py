"""
Create 3 charts: bar (sentiment distribution), bar (top positive phrases), bar (top negative phrases). Save as PNG.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (8, 5)


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def create_sentiment_bar_chart(df: pd.DataFrame, output_path: str | Path) -> None:
    """Bar chart: count of positive / neutral / negative. Save to output_path."""
    if df.empty or "sentiment_score" not in df.columns:
        counts = pd.Series({"positive": 0, "neutral": 0, "negative": 0})
    else:
        counts = df["sentiment_score"].value_counts()
    counts = counts.reindex(["positive", "neutral", "negative"], fill_value=0).fillna(0)
    colors = ["#2ecc71", "#95a5a6", "#e74c3c"]
    fig, ax = plt.subplots(figsize=(8, 5))
    if counts.astype(float).sum() <= 0:
        ax.text(0.5, 0.5, "No sentiment data", ha="center", va="center", fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
    else:
        x = counts.index.tolist()
        y = counts.values
        bars = ax.bar(x, y, color=colors)
        ax.set_ylabel("Count")
        ax.set_xlabel("Sentiment")
        ax.set_title("Sentiment distribution")
        for bar, val in zip(bars, y):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5, str(int(val)), ha="center", va="bottom", fontsize=11)
    p = Path(output_path)
    _ensure_dir(p)
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()


def create_phrase_bar_chart(phrase_counts: dict[str, int], title: str, output_path: str | Path, color: str = "steelblue") -> None:
    """Bar chart of phrase (2–3 word) counts. phrase_counts: phrase -> count."""
    if not phrase_counts:
        fig, ax = plt.subplots()
        ax.set_title(title)
        ax.set_ylabel("Count")
        p = Path(output_path)
        _ensure_dir(p)
        fig.savefig(p, dpi=150, bbox_inches="tight")
        plt.close()
        return
    phrases = list(phrase_counts.keys())[::-1]  # top at top
    counts = [phrase_counts[p] for p in phrases]
    fig, ax = plt.subplots(figsize=(8, max(5, len(phrases) * 0.35)))
    ax.barh(phrases, counts, color=color)
    ax.set_title(title)
    ax.set_xlabel("Count")
    plt.tight_layout()
    p = Path(output_path)
    _ensure_dir(p)
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close()


def create_all_charts(
    df: pd.DataFrame,
    pos_phrase_counts: dict[str, int],
    neg_phrase_counts: dict[str, int],
    output_dir: str | Path,
) -> None:
    """
    Create sentiment bar chart and two phrase bar charts; save as PNG in output_dir.
    """
    out = Path(output_dir)
    create_sentiment_bar_chart(df, out / "sentiment_pie.png")
    create_phrase_bar_chart(pos_phrase_counts, "Most common positive phrases (2–3 words)", out / "positive_words_bar.png", color="#2ecc71")
    create_phrase_bar_chart(neg_phrase_counts, "Most common negative phrases (2–3 words)", out / "negative_words_bar.png", color="#e74c3c")
