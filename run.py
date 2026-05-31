"""apple-health-wrapped entry point."""

import argparse
import os

import pandas as pd

from parse_health import parse_workouts
from compute_stats import compute_all_stats, format_pace
from visualize import generate_all_charts
from generate_card import generate_card
from ai_summary import generate_summary


def print_stats(stats, year, fh=None):
    def p(line=""):
        print(line)
        if fh:
            fh.write(line + "\n")

    h = int(stats["total_time_hours"])
    m = int(round((stats["total_time_hours"] - h) * 60))
    bpd = stats["best_pace_date"].strftime("%b %-d")
    lrd = stats["longest_run_date"].strftime("%b %-d")

    p()
    p("═══════════════════════════════════")
    p(f"  {year} Running Stats")
    p("═══════════════════════════════════")
    p(f"  Total runs:       {stats['total_runs']}")
    p(f"  Total miles:      {stats['total_miles']:.1f} mi")
    p(f"  Total time:       {h}h {m:02d}m")
    p(f"  Avg pace:         {format_pace(stats['avg_pace'])}")
    p(f"  Best pace:        {format_pace(stats['best_pace'])}  ({bpd})")
    p(f"  Longest run:      {stats['longest_run_miles']:.1f} mi   ({lrd})")
    if stats["avg_hr"] == stats["avg_hr"]:  # not NaN
        p(f"  Avg heart rate:   {stats['avg_hr']:.0f} bpm")
    else:
        p(f"  Avg heart rate:   n/a (no HR data)")
    p(f"  Best month:       {stats['best_month']} — {stats['best_month_miles']:.1f} mi")
    p()
    if abs(stats["pace_improvement"]) >= 1:
        arrow = "↓" if stats["pace_improvement"] > 0 else "↑"
        p(f"  Pace trend:       {format_pace(stats['first_month_pace']).replace(' /mi','')}"
          f" → {format_pace(stats['last_month_pace']).replace(' /mi','')}"
          f"  ({arrow} {abs(stats['pace_improvement']):.0f}s/mi)")
        p()
    z = stats["hr_zones"]
    if sum(z.values()) > 0:
        p("  HR Zones:")
        p(f"    Z1 easy         {z['Z1']:.0f}%")
        p(f"    Z2 aerobic      {z['Z2']:.0f}%")
        p(f"    Z3 tempo        {z['Z3']:.0f}%")
        p(f"    Z4 hard         {z['Z4']:.0f}%")
    p("═══════════════════════════════════")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default="apple_health_export.zip")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--stats-only", action="store_true")
    parser.add_argument("--ai-summary", action="store_true")
    parser.add_argument("--name", default="Your Name", help="Name shown on card")
    parser.add_argument("--age", type=int, default=None,
                        help="Used for HR-zone max-HR (220-age). Default max 185.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Force re-parse instead of using cached workouts.")
    args = parser.parse_args()

    os.makedirs("output", exist_ok=True)

    cache = f"output/.workouts_{args.year}.pkl"
    if os.path.exists(cache) and not args.no_cache:
        print(f"Loading cached workouts from {cache} (use --no-cache to re-parse)...")
        df = pd.read_pickle(cache)
    else:
        print(f"Parsing {args.zip}...")
        df = parse_workouts(args.zip, year=args.year)
        df.to_pickle(cache)
    print(f"Found {len(df)} running workouts in {args.year}")

    if len(df) == 0:
        print("No runs found. Check that the zip contains Apple Health export data.")
        return

    max_hr = (220 - args.age) if args.age else 185.0
    stats = compute_all_stats(df, max_hr=max_hr)

    with open("output/stats.txt", "w") as fh:
        print_stats(stats, args.year, fh=fh)

    if args.stats_only:
        return

    print("\nGenerating charts...")
    generate_all_charts(stats, df, year=args.year)

    ai_text = ""
    if args.ai_summary:
        print("Generating AI summary...")
        ai_text = generate_summary(stats)

    print("Generating shareable card...")
    generate_card(stats, name=args.name, ai_text=ai_text, year=args.year)

    print("\nDone! Check the output/ folder.")
    for f in ("stats.txt", "monthly_mileage.png", "pace_trend.png",
              "hr_zones.png", "year_in_review_card.png"):
        print(f"  output/{f}")


if __name__ == "__main__":
    main()
