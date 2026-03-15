"""
Run VADER sentiment analysis on reviews and add sentiment_score column (negative/neutral/positive).
Exposes get_sentiment_label(text) for sentence- or phrase-level sentiment (e.g. in theme extraction).
"""
from pathlib import Path

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_ANALYZER = None


def _get_analyzer() -> SentimentIntensityAnalyzer:
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = SentimentIntensityAnalyzer()
    return _ANALYZER


def _label_from_compound(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def get_sentiment_label(text: str) -> str:
    """
    Return sentiment label for a piece of text (e.g. a sentence).
    Use this for phrase-level sentiment so phrases are tagged by the sentence
    they appear in, not the whole review. Returns "positive", "neutral", or "negative".
    """
    if not (text and str(text).strip()):
        return "neutral"
    compound = _get_analyzer().polarity_scores(str(text).strip())["compound"]
    return _label_from_compound(compound)


def analyze_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add sentiment_score column to a DataFrame that has review_text.
    sentiment_score is one of: negative, neutral, positive.
    """
    analyzer = _get_analyzer()
    scores = df["review_text"].fillna("").apply(
        lambda t: analyzer.polarity_scores(str(t))["compound"]
    )
    df = df.copy()
    df["sentiment_score"] = scores.apply(_label_from_compound)
    return df


def run_on_csv(csv_path: str | Path, output_path: str | Path | None = None) -> pd.DataFrame:
    """
    Read CSV with date, rating, review_text; run sentiment; add sentiment_score; save.
    If output_path is None, overwrites csv_path.
    """
    path = Path(csv_path)
    out = Path(output_path) if output_path else path
    df = pd.read_csv(path)
    df = analyze_sentiment(df)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df
