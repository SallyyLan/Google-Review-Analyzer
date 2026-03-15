#!/usr/bin/env python3
"""
Run the customer review pipeline: scrape Google Maps reviews (or use existing CSV),
then run sentiment, themes, charts, summary, trend, alerts, and HTML report.
"""
import argparse
import logging
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for worker threads / no-GUI envs

from dotenv import load_dotenv

from modules import alert_system, report_generator, sentiment_analyzer, summary_writer, theme_extractor, time_analyzer, visualizer
from modules.review_scraper import fetch_reviews, save_reviews_csv


def run_pipeline(
    place_query: str | None = None,
    output_dir: str | Path = "output",
    reviews_limit: int = 200,
    csv_path: str | Path | None = None,
    force_scrape: bool = False,
) -> tuple[bool, Path | None, str, str | None]:
    """
    Run the full analysis pipeline. Returns (success, report_path, error_message, report_html).
    report_html is the HTML string for storage layer; report_path is the on-disk path for CLI.
    """
    load_dotenv()

    try:
        if csv_path is not None:
            input_csv = Path(csv_path)
            if not input_csv.exists():
                return False, None, f"CSV file not found: {input_csv}", None
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            target_csv = out_dir / "reviews.csv"
            if input_csv.resolve() != target_csv.resolve():
                shutil.copy2(input_csv, target_csv)
            csv_path = target_csv
        else:
            if not (place_query and place_query.strip()):
                return False, None, "Provide place_query (URL, place ID, or search string) or use csv_path.", None
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            csv_path = out_dir / "reviews.csv"

            if csv_path.exists() and not force_scrape:
                pass  # use existing CSV
            else:
                query = place_query.strip()
                df = fetch_reviews(query, reviews_limit=reviews_limit)
                if df.empty:
                    return (
                        False,
                        None,
                        "No reviews returned for this place. Check the Place ID or URL (e.g. full Google Maps link) and try again.",
                        None,
                    )
                save_reviews_csv(df, csv_path)

        # Pipeline steps
        df = sentiment_analyzer.run_on_csv(csv_path)
        pos, neg = theme_extractor.run_on_csv(csv_path, print_to_terminal=False)
        charts_dir = out_dir / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)
        visualizer.create_all_charts(df, pos, neg, charts_dir)
        summary_writer.generate_llm_summary(df, out_dir / "llm_insights.json", out_dir / "summary.txt")
        time_analyzer.run_on_csv(csv_path, charts_dir / "sentiment_trend.png")
        alert_system.run_on_csv(csv_path, out_dir / "alerts.txt")
        report_path, report_html = report_generator.generate_html_report(out_dir)
        return True, report_path, "", report_html
    except Exception as e:
        logging.exception("Pipeline failed")
        return False, None, str(e), None


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Google Maps reviews and run analysis pipeline.")
    parser.add_argument("place_query", nargs="?", help="Google Maps place URL (recommended), place ID (ChIJ...), or search string. E.g. 'https://maps.app.goo.gl/xxx' or 'Double Chicken Please, NY'. Omit if using --csv or when reviews.csv already exists.")
    parser.add_argument("--reviews-limit", type=int, default=200, help="Max number of reviews to fetch when scraping (default 200).")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory. Default: output/")
    parser.add_argument("--csv", type=str, default=None, help="Use existing reviews CSV instead of scraping (run pipeline only).")
    parser.add_argument("--scrape", action="store_true", help="Force re-scrape even if reviews.csv already exists in output dir.")
    args = parser.parse_args()

    csv_path_arg = Path(args.csv) if args.csv else None
    output_dir = Path(args.output_dir) if args.output_dir else Path("output")
    if args.csv and not args.output_dir:
        output_dir = Path(args.csv).parent

    success, report_path, error, _ = run_pipeline(
        place_query=args.place_query or None,
        output_dir=output_dir,
        reviews_limit=args.reviews_limit,
        csv_path=csv_path_arg,
        force_scrape=args.scrape,
    )
    if success and report_path:
        print(f"Report: {report_path}")
        sys.exit(0)
    else:
        print(error or "Pipeline failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
