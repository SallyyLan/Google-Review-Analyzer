"""
Generate a horizontal, executive-style HTML report that combines summary text,
LLM themes (with impact/risk), structured actions, and visual analytics.
"""
import base64
import csv
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _img_data_uri(p: Path) -> str:
    """Read image file and return a data URI for embedding in HTML."""
    if not p.exists():
        return ""
    raw = p.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _load_llm_insights(output_dir: Path) -> dict[str, Any]:
    """
    Load LLM insights (if present) and return the raw payload.

    Expected top-level keys:
    - themes: list of theme objects
    - summary: dict with sentence_1..sentence_4
    - actions: optional dict with high_impact/medium_impact/quick_wins
    """
    insights_path = output_dir / "llm_insights.json"
    if not insights_path.exists():
        return {"themes": [], "summary": {}, "actions": {}}

    try:
        raw = insights_path.read_text(encoding="utf-8")
        payload: dict[str, Any] = json.loads(raw)
    except Exception:
        return {"themes": [], "summary": {}, "actions": {}}

    if not isinstance(payload.get("themes", []), list):
        payload["themes"] = []
    if not isinstance(payload.get("summary", {}), dict):
        payload["summary"] = {}
    if not isinstance(payload.get("actions", {}), dict):
        payload["actions"] = {}
    return payload


def _compute_review_stats(output_dir: Path) -> dict[str, Any]:
    """
    Compute total reviews and sentiment buckets (positive/neutral/negative)
    from reviews.csv. Falls back gracefully if the file or columns are missing.
    """
    reviews_path = output_dir / "reviews.csv"
    total = 0
    sentiment_counts: Counter[str] = Counter()

    if reviews_path.exists():
        try:
            with reviews_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total += 1
                    raw_sent = (row.get("sentiment_score") or "").strip().lower()
                    if raw_sent.startswith("pos"):
                        bucket = "positive"
                    elif raw_sent.startswith("neg"):
                        bucket = "negative"
                    elif raw_sent:
                        bucket = "neutral"
                    else:
                        try:
                            rating = float(row.get("rating", "") or 0)
                        except ValueError:
                            rating = 0.0
                        if rating >= 4:
                            bucket = "positive"
                        elif rating <= 2:
                            bucket = "negative"
                        else:
                            bucket = "neutral"
                    sentiment_counts[bucket] += 1
        except Exception:
            # Leave stats at zero and surface a missing-data note in the UI.
            pass

    def _pct(count: int) -> float:
        return round((count / total) * 100, 1) if total > 0 else 0.0

    pos = sentiment_counts.get("positive", 0)
    neu = sentiment_counts.get("neutral", 0)
    neg = sentiment_counts.get("negative", 0)

    return {
        "total_reviews": total,
        "sentiment_counts": {"positive": pos, "neutral": neu, "negative": neg},
        "sentiment_percentages": {
            "positive": _pct(pos),
            "neutral": _pct(neu),
            "negative": _pct(neg),
        },
    }


def _split_and_sort_themes(themes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split themes into positive/negative lists sorted by mention_count desc."""
    pos = [t for t in themes if str(t.get("polarity", "")).lower() == "positive"]
    neg = [t for t in themes if str(t.get("polarity", "")).lower() == "negative"]

    def _sorted(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(items, key=lambda x: -int(x.get("mention_count", 0)))

    return _sorted(pos), _sorted(neg)


def _markdown_bold_to_html(text: str) -> str:
    """Escape HTML and convert **phrase** to <strong>phrase</strong>."""
    if not text:
        return ""
    escaped = html.escape(text)
    parts = escaped.split("**")
    out_parts: List[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out_parts.append(f"<strong>{part}</strong>")
        else:
            out_parts.append(part)
    return "".join(out_parts)


def _summary_narrative_html(
    summary_block: Dict[str, Any],
    summary_text: str,
    total_reviews: int,
    sent_pcts: Dict[str, float],
) -> str:
    """
    Build the Summary narrative section as a short stats line + bullet list
    so content is scannable and not a wall of prose.
    Prefers LLM summary sentences when available; otherwise parses summary.txt.
    """
    bullets: List[str] = []

    # Prefer structured LLM summary (sentence_1, sentence_2, ...).
    for key in ("sentence_1", "sentence_2", "sentence_3", "sentence_4"):
        raw = str(summary_block.get(key, "") or "").strip()
        if not raw:
            continue
        bullets.append(_markdown_bold_to_html(raw))

    if bullets:
        stats_line = ""
        if total_reviews and sent_pcts:
            pct = sent_pcts.get("positive", 0)
            stats_line = (
                f'<p class="summary-stats-line">Based on {total_reviews} reviews, '
                f"{pct:.0f}% positive.</p>"
            )
        items = "".join(f"<li>{b}</li>" for b in bullets)
        return (
            f'{stats_line}<ul class="summary-bullets">{items}</ul>'
        )

    # Fallback: parse summary.txt into bullets (split by sentence).
    if not summary_text or not summary_text.strip():
        return '<p class="muted">No summary narrative available.</p>'

    normalized = summary_text.replace("\n", " ").strip()
    segments = [s.strip() for s in normalized.split(". ") if s.strip()]

    # First segment often looks like "Based on N reviews, X% positive..."
    intro_line = ""
    rest = segments
    if segments and segments[0].lower().startswith("based on"):
        intro_line = f'<p class="summary-stats-line">{_markdown_bold_to_html(segments[0])}.</p>'
        rest = segments[1:]

    if not rest:
        return intro_line or '<p class="muted">No summary narrative available.</p>'

    items = "".join(f"<li>{_markdown_bold_to_html(s)}.</li>" for s in rest)
    return f'{intro_line}<ul class="summary-bullets">{items}</ul>'


def _impact_label_for_theme(theme: Dict[str, Any], max_count: int) -> str:
    """
    Choose the impact label for a positive theme.

    Prefer the explicit LLM-provided "impact" field, fall back to a simple
    mention_count-based heuristic if it is missing.
    """
    impact_raw = (theme.get("impact") or "").strip()
    if impact_raw:
        return str(impact_raw)
    mention_count = int(theme.get("mention_count", 0))
    if max_count <= 0:
        return "Experience Enhancer"
    if mention_count >= max_count * 0.7:
        return "Signature"
    return "Experience Enhancer"


def _avg_rating_from_theme(theme: Dict[str, Any]) -> float | None:
    reviews = theme.get("source_reviews") or []
    ratings: List[float] = []
    for r in reviews:
        try:
            ratings.append(float(r.get("rating", 0)))
        except Exception:
            continue
    if not ratings:
        return None
    return sum(ratings) / len(ratings)


def _risk_tag_for_theme(theme: Dict[str, Any]) -> str:
    """
    Choose a risk tag for a negative theme, preferring the explicit
    LLM-provided risk_level and falling back to a heuristic where needed.
    """
    risk_raw = (theme.get("risk_level") or "").strip()
    if risk_raw:
        return str(risk_raw)

    mention_count = int(theme.get("mention_count", 0))
    avg_rating = _avg_rating_from_theme(theme)
    if mention_count >= 10 or (avg_rating is not None and avg_rating <= 3.0):
        return "High"
    if mention_count >= 5 or (avg_rating is not None and avg_rating <= 3.7):
        return "Medium"
    return "Low"


def _classify_priority_buckets(neg_themes: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Group negative themes into coarse operational buckets for the top-right
    priority badge area: kitchen consistency, service pacing, seating comfort.
    """
    kitchen: List[str] = []
    service: List[str] = []
    seating: List[str] = []

    for t in neg_themes:
        name = str(t.get("name", "")).strip()
        lname = name.lower()
        if any(k in lname for k in ("cacio e pepe", "salty", "overly salty", "dish", "pasta", "food", "kitchen")):
            kitchen.append(name)
        if any(k in lname for k in ("service", "staff", "server", "wait", "rush", "peak hour", "booking")):
            service.append(name)
        if any(k in lname for k in ("seating", "seat", "chair", "cramped", "space", "tables close", "crowded")):
            seating.append(name)

    return {"kitchen": kitchen, "service": service, "seating": seating}


def generate_html_report(
    output_dir: str | Path,
    summary_path: str | Path | None = None,
    charts_dir: str | Path | None = None,
    report_filename: str = "report.html",
) -> tuple[Path, str]:
    """
    Write report.html into output_dir with a horizontal executive layout:
    - Top strip: total reviews, sentiment mix, and 2–3 key insight statements.
    - Middle band: strength drivers, operational risks, and recommended actions.
    - Bottom band: theme evidence tabs and compact visual analytics.
    """
    out = Path(output_dir)
    summary_path = Path(summary_path or out / "summary.txt")
    charts_dir = Path(charts_dir or out / "charts")

    # Legacy freeform summary (if any) for narrative context.
    summary_text = ""
    if summary_path.exists():
        summary_text = summary_path.read_text(encoding="utf-8").strip()

    # LLM-derived insights.
    insights = _load_llm_insights(out)
    themes: List[Dict[str, Any]] = insights.get("themes", [])  # type: ignore[assignment]
    summary_block: Dict[str, Any] = insights.get("summary", {})  # type: ignore[assignment]
    actions_block: Dict[str, Any] = insights.get("actions", {})  # type: ignore[assignment]

    pos_themes, neg_themes = _split_and_sort_themes(themes)
    # Review-level stats.
    stats = _compute_review_stats(out)
    total_reviews = stats["total_reviews"]
    sent_pcts = stats["sentiment_percentages"]

    # Priority buckets for badges and heuristic fallback for actions.
    priority_buckets = _classify_priority_buckets(neg_themes)

    # Impact label support for positive themes.
    max_pos_count = max((int(t.get("mention_count", 0)) for t in pos_themes), default=0)

    # Theme tabs + panels for bottom interaction area.
    theme_tabs_html: List[str] = []
    theme_panels_html: List[str] = []
    if themes:
        for idx, t in enumerate(themes):
            name = str(t.get("name", "")).strip()
            polarity = str(t.get("polarity", "")).lower()
            mention_count = int(t.get("mention_count", 0))
            quotes = [str(q) for q in (t.get("example_quotes") or [])][:3]
            tab_class = "theme-tab theme-tab-positive" if polarity == "positive" else "theme-tab theme-tab-negative"
            theme_tabs_html.append(
                f'<button class="{tab_class}" data-theme-id="{idx}">{name}</button>'
            )
            if quotes:
                quotes_items = "".join(f"<li>&ldquo;{q}&rdquo;</li>" for q in quotes)
                panel_body = f"<ul>{quotes_items}</ul>"
            else:
                panel_body = '<p class="muted">No example quotes available for this theme.</p>'
            theme_panels_html.append(
                f'<div class="theme-panel" data-theme-id="{idx}">'
                f"<h4>{name}</h4>"
                f'<p class="theme-meta">{polarity.capitalize()} &bull; {mention_count} mentions</p>'
                f"{panel_body}"
                "</div>"
            )
    else:
        theme_tabs_html.append('<span class="muted">No LLM themes available.</span>')
        theme_panels_html.append(
            '<div class="theme-panel" data-theme-id="0">'
            '<p class="muted">LLM insights were not generated for this run, so no theme-level quotes can be shown.</p>'
            "</div>"
        )

    # Inline horizontal bar chart for theme frequencies (top 7 themes).
    all_themes_sorted = sorted(
        themes,
        key=lambda t: -int(t.get("mention_count", 0)),
    )
    top_for_bars = all_themes_sorted[:7]
    max_bar_count = max((int(t.get("mention_count", 0)) for t in top_for_bars), default=0)
    bar_rows_html: List[str] = []
    if top_for_bars and max_bar_count > 0:
        for t in top_for_bars:
            name = str(t.get("name", "")).strip()
            count = int(t.get("mention_count", 0))
            width_pct = max(5, int((count / max_bar_count) * 100))
            polarity = str(t.get("polarity", "")).lower()
            bar_class = "bar-positive" if polarity == "positive" else "bar-negative"
            bar_rows_html.append(
                '<div class="bar-row">'
                f'<div class="bar-label">{name}</div>'
                '<div class="bar-track">'
                f'<div class="bar-fill {bar_class}" style="width:{width_pct}%"></div>'
                "</div>"
                f'<div class="bar-value">{count}</div>'
                "</div>"
            )
    else:
        bar_rows_html.append('<p class="muted">No theme frequency data available for this run.</p>')

    # Existing sentiment pie chart as donut visual if available.
    sentiment_pie_path = charts_dir / "sentiment_pie.png"
    if sentiment_pie_path.exists():
        sentiment_chart_html = f'<img src="{_img_data_uri(sentiment_pie_path)}" alt="Sentiment distribution" class="chart-img">'
    else:
        sentiment_chart_html = '<p class="muted">Sentiment donut chart image was not generated.</p>'

    # Alerts block, if present.
    alerts_path = out / "alerts.txt"
    alerts_html = ""
    if alerts_path.exists():
        alerts_html = (
            '<div class="alerts-block">'
            "<h3>Alerts</h3>"
            f"<pre>{alerts_path.read_text(encoding='utf-8').strip()}</pre>"
            "</div>"
        )

    # Actions panel content: prefer structured 'actions' from LLM, fallback to heuristics.
    use_structured_actions = isinstance(actions_block, dict) and any(
        isinstance(actions_block.get(key), list) and actions_block.get(key)
        for key in ("high_impact", "medium_impact", "quick_wins")
    )

    if use_structured_actions:
        def _render_action_group(bucket_key: str, default_label: str) -> str:
            items = actions_block.get(bucket_key) or []
            if not isinstance(items, list) or not items:
                return (
                    f"<li class='action-item'>"
                    f"<div class='item-main'>{default_label}</div>"
                    "<div class='item-secondary muted'>No LLM actions returned for this bucket.</div>"
                    "</li>"
                )
            rendered_items: List[str] = []
            for action in items:
                label = str(action.get("label", "") or "").strip()
                themes_for_action = [str(n) for n in (action.get("themes") or []) if n]
                themes_str = ", ".join(themes_for_action)
                meta_html = f"<span class='muted'>Themes: {themes_str}</span>" if themes_str else ""
                rendered_items.append(
                    "<li class='action-item'>"
                    f"<div class='item-main'>{label or default_label}</div>"
                    f"<div class='item-secondary'>{meta_html}</div>"
                    "</li>"
                )
            return "".join(rendered_items)

        actions_html = (
            _render_action_group("high_impact", "High impact")
            + _render_action_group("medium_impact", "Medium impact")
            + _render_action_group("quick_wins", "Quick wins")
        )
        actions_note = (
            "<div class='missing-note'>Actions are provided directly by the LLM enrichment step.</div>"
        )
    else:
        # Heuristic fallback if no structured actions are available.
        actions_html = """
          <li class="action-item">
            <div class="item-main">High impact</div>
            <div class="item-secondary">
              {high}
            </div>
          </li>
          <li class="action-item">
            <div class="item-main">Medium impact</div>
            <div class="item-secondary">
              {medium}
            </div>
          </li>
          <li class="action-item">
            <div class="item-main">Quick wins</div>
            <div class="item-secondary">
              {quick}
            </div>
          </li>
        """.format(
            high="; ".join(priority_buckets["kitchen"])
            if priority_buckets.get("kitchen")
            else "Stabilise kitchen execution on core dishes (e.g. cacio e pepe, seasoning levels).",
            medium="; ".join(priority_buckets["service"])
            if priority_buckets.get("service")
            else "Tighten service pacing and table coverage during weekend and peak hours.",
            quick="; ".join(priority_buckets["seating"])
            if priority_buckets.get("seating")
            else "Address seating comfort (chair support, table spacing) and small front-of-house touches.",
        )
        actions_note = (
            "<div class='missing-note'>Structured actions were not present in llm_insights.json; "
            "this panel uses heuristic groupings based on the negative themes.</div>"
        )

    summary_narrative_html = _summary_narrative_html(
        summary_block, summary_text, total_reviews, sent_pcts
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Customer Review Analysis Report</title>
  <style>
    :root {{
      --bg-page: #0b1020;
      --bg-panel: #13172a;
      --bg-panel-soft: #181d32;
      --bg-chip: #1f2540;
      --accent: #f5b041;
      --accent-soft: #f9e79f;
      --text-main: #f7f9ff;
      --text-muted: #a4a8c3;
      --border-subtle: #252a40;
      --positive: #5ad1a7;
      --negative: #ff6b6b;
      --neutral: #f4d03f;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      padding: 24px 32px 48px;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
      background: radial-gradient(circle at top left, #1a2240 0, #050815 55%, #030410 100%);
      color: var(--text-main);
    }}

    .page {{
      max-width: 1280px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}

    h1 {{
      font-size: 24px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--text-muted);
      margin: 0 0 4px;
    }}

    .page-subtitle {{
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 8px;
    }}

    .executive-strip {{
      display: flex;
      flex-direction: row;
      justify-content: space-between;
      align-items: stretch;
      gap: 16px;
      background: linear-gradient(135deg, #151c34 0, #101528 50%, #151c34 100%);
      border-radius: 16px;
      padding: 16px 20px;
      border: 1px solid rgba(255, 255, 255, 0.04);
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.55);
    }}

    .exec-col {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 8px;
      flex: 1;
      min-width: 0;
    }}

    h2.kpi-label,
    h2.exec-right-title,
    h2.panel-title {{
      margin: 0;
    }}

    h3.summary-heading {{
      margin: 0 0 4px;
    }}

    h3.chart-card-title {{
      margin: 0 0 6px;
    }}

    .exec-left .kpi-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-muted);
    }}

    .kpi-value-main {{
      font-size: 28px;
      font-weight: 600;
      letter-spacing: 0.03em;
    }}

    .kpi-row {{
      display: flex;
      gap: 10px;
      margin-top: 6px;
      flex-wrap: wrap;
    }}

    .kpi-chip {{
      background: rgba(255, 255, 255, 0.04);
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 11px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}

    .kpi-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }}

    .kpi-dot.positive {{ background: var(--positive); }}
    .kpi-dot.neutral {{ background: var(--neutral); }}
    .kpi-dot.negative {{ background: var(--negative); }}

    .exec-right-title {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      text-align: right;
      color: var(--text-muted);
    }}

    .priority-badges {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
      margin-top: 6px;
    }}

    .priority-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 9px;
      border-radius: 999px;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid rgba(255, 255, 255, 0.04);
      font-size: 11px;
    }}

    .priority-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }}

    .priority-dot.high {{ background: #ff4d4d; }}
    .priority-dot.medium {{ background: #ffb347; }}
    .priority-dot.low {{ background: #f4d03f; }}

    .priority-label {{
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 10px;
    }}

    .priority-desc {{
      color: var(--text-muted);
      font-size: 11px;
    }}

    .middle-band {{
      display: grid;
      grid-template-columns: 1.15fr 1.1fr 1.1fr;
      gap: 16px;
    }}

    .panel {{
      background: var(--bg-panel);
      border-radius: 16px;
      padding: 14px 14px 16px;
      border: 1px solid var(--border-subtle);
      box-shadow: 0 10px 26px rgba(0, 0, 0, 0.5);
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-height: 0;
    }}

    .panel-title {{
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent-soft);
    }}

    .panel-subtitle {{
      font-size: 11px;
      color: var(--text-muted);
    }}

    .strength-list,
    .risk-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 4px 0 0;
      padding: 0;
      list-style: none;
    }}

    .actions-list {{
      margin: 4px 0 0;
      padding-left: 18px;
      font-size: 12px;
      line-height: 1.5;
      text-align: left;
      list-style-type: disc;
    }}

    .actions-list .action-item {{
      margin-bottom: 6px;
      overflow-wrap: break-word;
    }}

    .action-item {{
      display: flex;
      flex-direction: column;
      gap: 2px;
      text-align: left;
      font-size: 12px;
    }}

    .action-item .item-main,
    .action-item .item-secondary {{
      text-align: left;
    }}

    .strength-item,
    .risk-item {{
      display: grid;
      grid-template-columns: minmax(0, 1.8fr) auto;
      column-gap: 6px;
      row-gap: 2px;
      align-items: baseline;
      font-size: 12px;
    }}

    .item-main {{
      font-weight: 500;
      min-width: 0;
      overflow-wrap: break-word;
    }}

    .item-meta-right {{
      font-size: 11px;
      color: var(--text-muted);
      text-align: right;
    }}

    .item-secondary {{
      grid-column: 1 / -1;
      font-size: 11px;
      color: var(--text-muted);
      min-width: 0;
      overflow-wrap: break-word;
    }}

    .impact-pill {{
      display: inline-flex;
      padding: 3px 7px;
      border-radius: 999px;
      font-size: 10px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}

    .impact-pill.signature {{
      border-color: var(--positive);
      color: var(--positive);
    }}

    .impact-pill.experience {{
      border-color: var(--accent-soft);
      color: var(--accent-soft);
    }}

    .risk-tag {{
      display: inline-flex;
      padding: 3px 7px;
      border-radius: 999px;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border: 1px solid rgba(255, 255, 255, 0.18);
    }}

    .risk-tag.high {{
      border-color: #ff4d4d;
      color: #ff9595;
    }}

    .risk-tag.medium {{
      border-color: #ffb347;
      color: #ffd18a;
    }}

    .risk-tag.low {{
      border-color: #f4d03f;
      color: #f7eaa5;
    }}

    .alerts-block pre {{
      margin: 6px 0 0;
      font-size: 11px;
      white-space: pre-wrap;
      background: #111525;
      border-radius: 10px;
      padding: 8px 10px;
      border: 1px solid #252a40;
      color: var(--text-muted);
    }}

    .bottom-band {{
      display: grid;
      grid-template-columns: 1.1fr 1.1fr;
      gap: 16px;
    }}

    .theme-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 10px;
    }}

    .theme-tab {{
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      padding: 5px 9px;
      background: #161b32;
      color: var(--text-main);
      font-size: 11px;
      cursor: pointer;
      max-width: 100%;
      text-overflow: ellipsis;
      white-space: nowrap;
      overflow: hidden;
    }}

    .theme-tab-positive {{
      border-color: var(--positive);
    }}

    .theme-tab-negative {{
      border-color: var(--negative);
    }}

    .theme-tab.active {{
      background: #f5b041;
      color: #05070f;
      border-color: #f5b041;
    }}

    .theme-panel {{
      display: none;
      background: var(--bg-panel-soft);
      border-radius: 12px;
      padding: 10px 12px 12px;
      border: 1px solid var(--border-subtle);
      font-size: 12px;
      overflow-wrap: break-word;
    }}

    .theme-panel h4 {{
      margin: 0 0 4px;
      font-size: 13px;
    }}

    .theme-meta {{
      margin: 0 0 6px;
      font-size: 11px;
      color: var(--text-muted);
    }}

    .theme-panel ul {{
      margin: 0;
      padding-left: 18px;
    }}

    .theme-panel li {{
      margin-bottom: 4px;
      overflow-wrap: break-word;
    }}

    .muted {{
      color: var(--text-muted);
      font-size: 11px;
    }}

    .charts-container {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}

    .chart-card {{
      background: var(--bg-panel-soft);
      border-radius: 12px;
      padding: 10px 12px 12px;
      border: 1px solid var(--border-subtle);
    }}

    .chart-card-title {{
      font-size: 12px;
      font-weight: 500;
      margin: 0 0 6px;
    }}

    .chart-img {{
      max-width: 100%;
      display: block;
      border-radius: 8px;
      border: 1px solid rgba(255, 255, 255, 0.12);
      background: #05070f;
    }}

    .sentiment-legend {{
      display: flex;
      gap: 10px;
      margin-top: 6px;
      font-size: 11px;
      color: var(--text-muted);
      flex-wrap: wrap;
    }}

    .sentiment-legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}

    .bar-row {{
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) 1fr auto;
      align-items: center;
      gap: 6px;
      margin-bottom: 5px;
    }}

    .bar-label {{
      font-size: 11px;
      color: var(--text-main);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .bar-track {{
      background: #1a2038;
      border-radius: 999px;
      height: 7px;
      overflow: hidden;
    }}

    .bar-fill {{
      height: 100%;
      border-radius: 999px;
    }}

    .bar-fill.bar-positive {{
      background: linear-gradient(90deg, #3fd4a1, #7af2c2);
    }}

    .bar-fill.bar-negative {{
      background: linear-gradient(90deg, #ff6b6b, #ffa8a8);
    }}

    .bar-value {{
      font-size: 11px;
      color: var(--text-muted);
      text-align: right;
    }}

    .summary-block {{
      font-size: 11px;
      color: var(--text-muted);
      line-height: 1.5;
      overflow-wrap: break-word;
    }}

    .summary-block p {{
      margin: 0 0 4px;
      overflow-wrap: break-word;
    }}

    .summary-heading {{
      font-size: 12px;
      font-weight: 600;
      margin: 0 0 4px;
      color: var(--text-main);
    }}

    .summary-stats-line {{
      margin: 0 0 6px;
      font-size: 11px;
      color: var(--text-muted);
    }}

    .summary-bullets {{
      margin: 0;
      padding-left: 18px;
      font-size: 11px;
      color: var(--text-muted);
      line-height: 1.5;
    }}

    .summary-bullets li {{
      margin-bottom: 6px;
      overflow-wrap: break-word;
    }}

    .missing-note {{
      margin-top: 6px;
      font-size: 10px;
      color: var(--text-muted);
      overflow-wrap: break-word;
    }}

    @media (max-width: 960px) {{
      .executive-strip {{
        flex-direction: column;
      }}
      .exec-col {{
        align-items: flex-start;
      }}
      .exec-right-title,
      .priority-badges {{
        align-items: flex-start;
        text-align: left;
      }}
      .middle-band {{
        grid-template-columns: 1fr;
      }}
      .bottom-band {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <nav style="margin-bottom: 1rem;">
      <a href="/" style="color: var(--accent); text-decoration: none;">&larr; Back to search</a>
    </nav>
    <header>
      <h1>Customer Review Analysis</h1>
      <div class="page-subtitle">Horizontal executive view &middot; Drivers, risks, and evidence</div>
    </header>

    <section class="executive-strip">
      <div class="exec-col exec-left">
        <h2 class="kpi-label">Total reviews</h2>
        <div class="kpi-value-main">{total_reviews if total_reviews else "N/A"}</div>
        <div class="kpi-row">
          <span class="kpi-chip">
            <span class="kpi-dot positive"></span>
            <span>Positive {sent_pcts["positive"]}%</span>
          </span>
          <span class="kpi-chip">
            <span class="kpi-dot neutral"></span>
            <span>Neutral {sent_pcts["neutral"]}%</span>
          </span>
          <span class="kpi-chip">
            <span class="kpi-dot negative"></span>
            <span>Negative {sent_pcts["negative"]}%</span>
          </span>
        </div>
        {"<div class='missing-note'>Sentiment mix unavailable &mdash; reviews.csv not found.</div>" if total_reviews == 0 else ""}
      </div>

      <div class="exec-col exec-right">
        <h2 class="exec-right-title">Priority focus (next 30 days)</h2>
        <div class="priority-badges">
          <div class="priority-badge">
            <span class="priority-dot high"></span>
            <span class="priority-label">High</span>
            <span class="priority-desc">Kitchen consistency</span>
          </div>
          <div class="priority-badge">
            <span class="priority-dot medium"></span>
            <span class="priority-label">Medium</span>
            <span class="priority-desc">Service pacing</span>
          </div>
          <div class="priority-badge">
            <span class="priority-dot low"></span>
            <span class="priority-label">Low</span>
            <span class="priority-desc">Seating comfort</span>
          </div>
        </div>
      </div>
    </section>

    <section class="middle-band">
      <article class="panel">
        <h2 class="panel-title">Brand strength drivers</h2>
        <div class="panel-subtitle">Ranked positive themes by mention count.</div>
        <ul class="strength-list">
          {"".join(
            f"<li class='strength-item'>"
            f"<div class='item-main'>{str(t.get('name', '')).strip()}</div>"
            f"<div class='item-meta-right'>{int(t.get('mention_count', 0))} mentions</div>"
            f"<div class='item-secondary'>"
            f"<span class='impact-pill {'signature' if _impact_label_for_theme(t, max_pos_count) == 'Signature' else 'experience'}'>"
            f"{_impact_label_for_theme(t, max_pos_count)}</span>"
            f"</div>"
            f"</li>"
            for t in pos_themes
          ) if pos_themes else "<li class='strength-item'><span class='muted'>No positive themes returned by LLM.</span></li>"}
        </ul>
        <div class="summary-block">
          <h3 class="summary-heading">Summary narrative</h3>
          {summary_narrative_html}
        </div>
      </article>

      <article class="panel">
        <h2 class="panel-title">Operational risks</h2>
        <div class="panel-subtitle">Ranked by frequency and impact on ratings.</div>
        <ul class="risk-list">
          {"".join(
            (
              lambda name, count, tag, cause: (
                "<li class='risk-item'>"
                f"<div class='item-main'>{name}</div>"
                f"<div class='item-meta-right'>"
                f"{count} mentions &middot; "
                f"<span class='risk-tag {tag.lower()}'>{tag}</span>"
                "</div>"
                f"<div class='item-secondary'>"
                f"{cause}"
                "</div>"
                "</li>"
              )
            )(
              str(t.get("name", "")).strip(),
              int(t.get("mention_count", 0)),
              _risk_tag_for_theme(t),
              str(t.get("cause_hypothesis") or f"Possible cause: operational patterns leading to {str(t.get('name', '')).strip().lower()}."),
            )
            for t in neg_themes
          ) if neg_themes else "<li class='risk-item'><span class='muted'>No negative themes returned by LLM, so no explicit operational risks are listed.</span></li>"}
        </ul>
        <div class="missing-note">
          Risk tags and cause hypotheses prefer the LLM-provided fields in <code>llm_insights.json</code>; heuristics are only used when those fields are missing.
        </div>
      </article>

      <article class="panel">
        <h2 class="panel-title">Recommended actions (next 30 days)</h2>
        <div class="panel-subtitle">Grouped into high impact, medium impact, and quick wins.</div>
        <ul class="actions-list">
          {actions_html}
        </ul>
        {actions_note}
      </article>
    </section>

    <section class="bottom-band">
      <article class="panel">
        <h2 class="panel-title">Theme evidence</h2>
        <div class="panel-subtitle">Switch between themes to see supporting quotes.</div>
        <div class="theme-tabs">
          {"".join(theme_tabs_html)}
        </div>
        <div class="theme-panels">
          {"".join(theme_panels_html)}
        </div>
      </article>

      <article class="panel">
        <h2 class="panel-title">Visual analytics</h2>
        <div class="panel-subtitle">Sentiment mix and theme frequency at a glance.</div>
        <div class="charts-container">
          <div class="chart-card">
            <h3 class="chart-card-title">Sentiment donut</h3>
            {sentiment_chart_html}
            <div class="sentiment-legend">
              <span class="sentiment-legend-item">
                <span class="kpi-dot positive"></span>
                <span>Positive {sent_pcts["positive"]}%</span>
              </span>
              <span class="sentiment-legend-item">
                <span class="kpi-dot neutral"></span>
                <span>Neutral {sent_pcts["neutral"]}%</span>
              </span>
              <span class="sentiment-legend-item">
                <span class="kpi-dot negative"></span>
                <span>Negative {sent_pcts["negative"]}%</span>
              </span>
            </div>
          </div>
          <div class="chart-card">
            <h3 class="chart-card-title">Theme frequency (top {len(top_for_bars)})</h3>
            {"".join(bar_rows_html)}
          </div>
          {alerts_html}
        </div>
      </article>
    </section>
  </div>

  <script>
    (function() {{
      var tabs = document.querySelectorAll('.theme-tab');
      var panels = document.querySelectorAll('.theme-panel');
      if (!tabs.length || !panels.length) return;

      function activate(id) {{
        tabs.forEach(function(btn) {{
          btn.classList.toggle('active', btn.getAttribute('data-theme-id') === id);
        }});
        panels.forEach(function(panel) {{
          panel.style.display = panel.getAttribute('data-theme-id') === id ? 'block' : 'none';
        }});
      }}

      tabs.forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          activate(btn.getAttribute('data-theme-id'));
        }});
      }});

      activate(tabs[0].getAttribute('data-theme-id'));
    }})();
  </script>
</body>
</html>
"""
    report_path = out / report_filename
    report_path.write_text(html, encoding="utf-8")
    return report_path, html
