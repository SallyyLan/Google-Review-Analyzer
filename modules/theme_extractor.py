"""
Use a Hugging Face LLM (Mistral) to extract structured themes and business insights
from restaurant reviews, replacing the old YAKE/spaCy-based keyphrase pipeline.

The model returns strict JSON, which we save to llm_insights.json and also convert
into simple positive/negative theme-count dicts for downstream charts and summaries.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

import pandas as pd

from modules.llm_client import generate_text


INSIGHTS_FILENAME = "llm_insights.json"


@dataclass
class Theme:
    name: str
    polarity: str
    mention_count: int
    example_quotes: list[str]
    source_reviews: list[dict[str, Any]]
    # Optional enrichment fields coming from the LLM.
    impact: str | None = None
    risk_level: str | None = None
    cause_hypothesis: str | None = None


def _build_prompt(df: pd.DataFrame, max_reviews: int = 150) -> str:
    """
    Build the analysis prompt based on the user's prompt-design rules.

    We pass a sample of reviews (id, date, rating, sentiment_score, text) and ask
    the model to return JSON with positive/negative themes and a four-sentence
    business summary. Limited to 150 reviews so prompt + response fit HF API
    limit (inputs + max_new_tokens <= 32769).
    """
    if df.empty:
        return "You are a restaurant review analyst. There are no reviews. Return an empty JSON object."

    # Ensure required columns exist
    df = df.copy()
    if "id" not in df.columns:
        df["id"] = df.index.astype(int)

    # Sample up to max_reviews to keep prompt size manageable while preserving variety.
    if len(df) > max_reviews:
        df_sample = df.sample(max_reviews, random_state=42)
    else:
        df_sample = df

    # Build a reviews block for the prompt.
    review_lines: list[str] = []
    for _, row in df_sample.iterrows():
        rid = int(row.get("id", 0))
        date = str(row.get("date", "") or "")
        rating = row.get("rating", "")
        sentiment = row.get("sentiment_score", "")
        text = str(row.get("review_text", "") or "").replace("\n", " ").strip()
        if not text:
            continue
        review_lines.append(
            f"- id: {rid}; date: {date}; rating: {rating}; sentiment: {sentiment}; text: \"{text}\""
        )

    reviews_block = "\n".join(review_lines)

    prompt = dedent(
        f"""
        You are a restaurant review analyst analyzing Google reviews for a single restaurant.
        You must return structured JSON only.

        ANALYSIS RULES:
        1. Ignore restaurant names and their variations (e.g. "Piccola Cucina", "Piccola Cucina Uptown").
        2. Ignore location words such as "New York", "NYC", "uptown" except when needed purely as context.
        3. Dish names alone (e.g. "cheese wheel", "cacio e pepe", "lobster pasta") are NOT themes unless a clear opinion is attached.
        4. Analyze sentiment at the SENTENCE level, not just the overall review.
           - The same review can contribute both positive and negative themes (e.g. great food BUT terrible service).
           - Do not label all phrases based on star rating alone.
        5. Always return AT LEAST 2–3 negative themes, even if the reviews are mostly positive.
           - If strong negatives are rare, look for mild complaints or "could be better" style feedback.
        6. Theme names must be SPECIFIC and restaurant-contextual:
           - REJECT generic names like "good food", "bad service", "great place".
           - USE names like "inconsistent cacio e pepe portion size", "inattentive staff on weekend evenings", "dishes arriving at different times".
        7. Keep the output compact and short:
           - Limit the total number of themes to AT MOST 6 items combined (positive + negative).
           - Each theme's example_quotes list must contain AT MOST 1 short quote (a single sentence or short excerpt).
           - Each theme's source_reviews list must contain AT MOST 3 review objects.
        8. Every theme must include verifiable evidence:
           - mention_count = number of reviews that clearly support the theme.
           - example_quotes = up to 1 verbatim quote from reviews, copied word-for-word.
           - source_reviews = list of objects with at least review id, date, and rating.
        9. Impact and risk annotations:
           - For POSITIVE themes, set impact to either "Signature" (core, frequently mentioned brand driver) or "Experience Enhancer" (secondary but notable).
           - For NEGATIVE themes, set impact to null.
           - For NEGATIVE themes, always set risk_level to "High", "Medium", or "Low" based on how severe and frequent the issue is for guests.
           - For NEGATIVE themes, always set cause_hypothesis to ONE short, operational sentence describing the most likely root cause (e.g. "Batch prep of sauces leading to inconsistent cacio e pepe texture").

        SUMMARY PARAGRAPH RULES (4 sentences, fixed structure):
        - sentence_1: strongest positive theme with a specific example.
        - sentence_2: second positive theme or notable praise.
        - sentence_3: main negative theme(s) — MUST be included if any exist.
        - sentence_4: pattern observation or actionable recommendation for the restaurant.

        JSON SCHEMA (return EXACTLY this shape):
        {{
          "themes": [
            {{
              "name": "string, specific theme name",
              "polarity": "positive" | "negative",
              "mention_count": integer,
              "impact": "Signature" | "Experience Enhancer" | null,
              "example_quotes": ["exact quote 1", "exact quote 2"],
              "source_reviews": [
                {{"id": integer, "date": "YYYY-MM-DD or similar", "rating": number}}
              ],
              "risk_level": "High" | "Medium" | "Low" | null,
              "cause_hypothesis": "string, one short operational sentence or null"
            }}
          ],
          "summary": {{
            "sentence_1": "string",
            "sentence_2": "string",
            "sentence_3": "string",
            "sentence_4": "string"
          }}
        }}

        REVIEWS TO ANALYZE:
        {reviews_block}

        Follow ALL rules above.
        Return valid JSON only. No text before or after. If unsure, return low confidence rather than guessing.
        """
    ).strip()

    return prompt


def _parse_insights_json(raw: str) -> dict[str, Any]:
    """
    Parse the JSON returned by the model. Try to be resilient to stray text
    by trimming to the first '{{' and last '}}'.
    """
    raw = (raw or "").strip()
    # Strip common Markdown fences like ```json ... ``` that some models add.
    if raw.startswith("```"):
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    if not raw:
        # Graceful fallback: empty insights structure.
        return {"themes": [], "summary": {}}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to salvage JSON substring.
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        # Final fallback: return empty insights to avoid crashing the pipeline.
        print("Warning: could not parse LLM JSON response; proceeding with empty insights.")
        return {"themes": [], "summary": {}}


def _parse_actions_json(raw: str) -> dict[str, Any]:
    """
    Parse a secondary JSON blob that should contain an "actions" object.

    Reuses the same robustness as _parse_insights_json but expects a much
    smaller schema. Returns {} on failure.
    """
    payload = _parse_insights_json(raw)
    if not isinstance(payload, dict):
        return {}
    actions = payload.get("actions")
    if isinstance(actions, dict):
        return {"actions": actions}
    return {}


def _themes_from_payload(payload: dict[str, Any] | None) -> list[Theme]:
    out: list[Theme] = []
    if payload is None:
        return []
    for item in payload.get("themes", []) or []:
        try:
            name = str(item.get("name", "")).strip()
            polarity = str(item.get("polarity", "")).strip().lower()
            mention_count = int(item.get("mention_count", 0))
            example_quotes = [str(q) for q in item.get("example_quotes", []) or []]
            source_reviews = item.get("source_reviews", []) or []
            impact_raw = item.get("impact")
            impact = str(impact_raw).strip() or None if impact_raw is not None else None
            risk_raw = item.get("risk_level")
            risk_level = str(risk_raw).strip() or None if risk_raw is not None else None
            cause_raw = item.get("cause_hypothesis")
            cause_hypothesis = str(cause_raw).strip() or None if cause_raw is not None else None
            if not name or polarity not in {"positive", "negative"} or mention_count < 0:
                continue
            out.append(
                Theme(
                    name=name,
                    polarity=polarity,
                    mention_count=mention_count,
                    example_quotes=example_quotes,
                    source_reviews=source_reviews,
                    impact=impact,
                    risk_level=risk_level,
                    cause_hypothesis=cause_hypothesis,
                )
            )
        except Exception:
            # Skip malformed theme entries
            continue
    return out


def _counts_from_themes(themes: list[Theme]) -> tuple[dict[str, int], dict[str, int]]:
    pos_counts: dict[str, int] = {}
    neg_counts: dict[str, int] = {}
    for t in themes:
        if t.polarity == "positive":
            pos_counts[t.name] = pos_counts.get(t.name, 0) + int(t.mention_count)
        elif t.polarity == "negative":
            neg_counts[t.name] = neg_counts.get(t.name, 0) + int(t.mention_count)
    return pos_counts, neg_counts


def _build_actions_prompt(payload: dict[str, Any]) -> str:
    """
    Build a compact prompt that asks the LLM to propose recommended actions
    grouped into high_impact / medium_impact / quick_wins based on the
    already-extracted themes and summary.
    """
    themes = payload.get("themes") or []
    summary = payload.get("summary") or {}

    theme_lines: list[str] = []
    for t in themes:
        try:
            name = str(t.get("name", "")).strip()
            polarity = str(t.get("polarity", "")).strip().lower()
            mention_count = int(t.get("mention_count", 0))
            impact = str(t.get("impact", "") or "").strip()
            risk_level = str(t.get("risk_level", "") or "").strip()
            if not name:
                continue
            theme_lines.append(
                f'- name: "{name}"; polarity: {polarity}; mentions: {mention_count}; '
                f'impact: "{impact or "null"}"; risk_level: "{risk_level or "null"}"'
            )
        except Exception:
            continue

    summary_sentence_4 = str(summary.get("sentence_4", "") or "").strip()

    lines_block = "\n".join(theme_lines) or "(no themes available)"

    prompt = dedent(
        f"""
        You are a restaurant operations strategist.

        You will receive a small list of already-extracted THEMES plus one
        recommendation-style SUMMARY sentence. Based on these, propose
        concrete recommended actions for the next 30 days.

        THEMES:
        {lines_block}

        SUMMARY_SENTENCE_4 (pattern / recommendation from the first pass):
        "{summary_sentence_4}"

        ACTION DESIGN RULES:
        - Use only the themes and signals provided above; do not invent new issues.
        - Group actions into three buckets: high_impact, medium_impact, quick_wins.
        - Each action MUST be:
          - a single short, operational sentence in the "label" field.
          - clearly address one or more of the existing themes.
        - For each action, fill the "themes" array with the EXACT theme.name strings it addresses.
        - Prefer 1–3 actions per bucket; omit a bucket or return an empty array if you truly have no actions for it.

        JSON SCHEMA (return EXACTLY this shape):
        {{
          "actions": {{
            "high_impact": [
              {{"label": "string, one short sentence", "themes": ["existing theme name", "..."]}}
            ],
            "medium_impact": [
              {{"label": "string, one short sentence", "themes": ["existing theme name", "..."]}}
            ],
            "quick_wins": [
              {{"label": "string, one short sentence", "themes": ["existing theme name", "..."]}}
            ]
          }}
        }}

        Return valid JSON only. No text before or after.
        """
    ).strip()

    return prompt


def enrich_actions_from_insights(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Second-pass enrichment: call the LLM with the existing themes and
    summary to generate a structured "actions" object grouped by impact.

    On any failure (LLM error or JSON parse issue) this function returns
    the original payload unchanged.
    """
    try:
        prompt = _build_actions_prompt(payload)
        raw = generate_text(prompt)
        actions_payload = _parse_actions_json(raw)
        actions = actions_payload.get("actions")
        if isinstance(actions, dict):
            payload = dict(payload)
            payload["actions"] = actions
    except Exception:
        # Do not break the main pipeline if the enrichment step fails.
        return payload
    return payload


def run_on_csv(
    csv_path: str | Path,
    top_n: int = 20,
    print_to_terminal: bool = True,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Read CSV with review_text and sentiment_score; call the LLM to extract
    structured themes and insights; save the full JSON; and return simple
    positive/negative theme counts for charts and summaries.
    """
    path = Path(csv_path)
    df = pd.read_csv(path)

    prompt = _build_prompt(df)
    raw = generate_text(prompt)

    # Optional debug: save raw LLM output for inspection.
    output_dir = path.parent
    raw_path = output_dir / "llm_raw.txt"
    try:
        raw_path.write_text(raw or "", encoding="utf-8")
    except Exception:
        pass

    payload = _parse_insights_json(raw)

    # Second-pass enrichment: derive structured actions from the base payload.
    payload = enrich_actions_from_insights(payload)

    # Save full payload for downstream consumers (summary writer, report).
    insights_path = output_dir / INSIGHTS_FILENAME
    insights_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    themes = _themes_from_payload(payload)
    pos_counts, neg_counts = _counts_from_themes(themes)

    # Limit to top_n by count, descending.
    pos_counts = dict(sorted(pos_counts.items(), key=lambda x: -x[1])[:top_n])
    neg_counts = dict(sorted(neg_counts.items(), key=lambda x: -x[1])[:top_n])

    if print_to_terminal:
        print("Positive themes (from LLM):")
        for name, count in pos_counts.items():
            print(f"  {name!r}: {count} reviews")
        print("\nNegative themes (from LLM):")
        for name, count in neg_counts.items():
            print(f"  {name!r}: {count} reviews")

    return pos_counts, neg_counts

