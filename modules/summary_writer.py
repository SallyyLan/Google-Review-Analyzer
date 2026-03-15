"""
Write text summaries from sentiment/theme data.

- Baseline: simple counts-based summary (existing behavior).
- Enhanced: use LLM-generated insights JSON for a richer business summary.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def generate_text_summary(
    df: pd.DataFrame,
    pos_word_counts: dict[str, int],
    neg_word_counts: dict[str, int],
    output_path: str | Path,
) -> None:
    """
    Baseline summary: Count positive/negative/neutral, compute %, take top 3
    positive/negative themes, and write a short plain-English summary.
    """
    total = len(df)
    if total == 0:
        summary = "No reviews to summarize."
    else:
        pos_count = (df["sentiment_score"] == "positive").sum()
        neg_count = (df["sentiment_score"] == "negative").sum()
        neutral_count = (df["sentiment_score"] == "neutral").sum()
        pct_positive = round(100 * pos_count / total)
        praise = ", ".join(list(pos_word_counts.keys())[:3]) if pos_word_counts else "—"
        complaints = ", ".join(list(neg_word_counts.keys())[:3]) if neg_word_counts else "—"
        summary = (
            f"Based on {total} reviews, {pct_positive}% positive "
            f"({pos_count} positive, {neg_count} negative, {neutral_count} neutral).\n"
            f"Customers love: {praise}.\n"
            f"Main complaints: {complaints}."
        )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary, encoding="utf-8")


def generate_llm_summary(
    df: pd.DataFrame,
    insights_json_path: str | Path,
    output_path: str | Path,
) -> None:
    """
    Enhanced summary: read structured insights from llm_insights.json and
    write a concise, business-focused summary for the owner.

    Falls back to generate_text_summary() if the JSON is missing or invalid.
    """
    insights_path = Path(insights_json_path)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not insights_path.exists():
        # Fallback to baseline summary if insights file is missing.
        generate_text_summary(df, {}, {}, out_path)
        return

    try:
        payload = json.loads(insights_path.read_text(encoding="utf-8"))
    except Exception:
        generate_text_summary(df, {}, {}, out_path)
        return

    summary_block = payload.get("summary") or {}
    s1 = str(summary_block.get("sentence_1", "")).strip()
    s2 = str(summary_block.get("sentence_2", "")).strip()
    s3 = str(summary_block.get("sentence_3", "")).strip()
    s4 = str(summary_block.get("sentence_4", "")).strip()

    # Stats from sentiment_analyzer output as context.
    total = len(df)
    if total > 0:
        pos_count = (df["sentiment_score"] == "positive").sum()
        neg_count = (df["sentiment_score"] == "negative").sum()
        neutral_count = (df["sentiment_score"] == "neutral").sum()
        pct_positive = round(100 * pos_count / total)
        stats_line = (
            f"Based on {total} reviews, {pct_positive}% are positive "
            f"({pos_count} positive, {neg_count} negative, {neutral_count} neutral)."
        )
    else:
        stats_line = "No reviews to summarize."

    sentences = [s for s in (s1, s2, s3, s4) if s]
    llm_paragraph = " ".join(sentences) if sentences else ""

    if not llm_paragraph:
        # If LLM summary is empty, revert to baseline.
        generate_text_summary(df, {}, {}, out_path)
        return

    final_summary = f"{stats_line}\n\n{llm_paragraph}"
    out_path.write_text(final_summary, encoding="utf-8")

