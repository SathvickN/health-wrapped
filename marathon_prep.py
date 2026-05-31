"""Side-by-side stats: full-year 2026 (YTD) vs marathon-prep window (from a
start date, default Mar 5 2026).

Run stats come from the cached/parsed workouts. Steps are streamed from the
Apple Health export.xml. Multiple devices log StepCount over the same
intervals (Apple Watch, iPhone, Oura), so naive summing triple-counts. We
dedup per calendar day by keeping the single source with the most steps that
day — a reasonable proxy for Apple Health's interval-priority merge.
"""

import argparse
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime

import pandas as pd

from parse_health import parse_workouts, _find_xml_name
from compute_stats import format_pace

STEP_TYPE = "HKQuantityTypeIdentifierStepCount"


def daily_steps(zip_path, year):
    """Return {date(YYYY-MM-DD): deduped step count} for the year."""
    per_day_src = defaultdict(lambda: defaultdict(float))
    with zipfile.ZipFile(zip_path) as zf:
        xml_name = _find_xml_name(zf)
        with zf.open(xml_name) as f:
            for _ev, el in ET.iterparse(f, events=("end",)):
                if el.tag == "Record" and el.attrib.get("type") == STEP_TYPE:
                    sd = el.attrib.get("startDate", "")
                    if sd[:4] == str(year):
                        day = sd[:10]
                        src = el.attrib.get("sourceName", "?")
                        per_day_src[day][src] += float(el.attrib.get("value", 0))
                if el.tag in ("Record", "Workout"):
                    el.clear()
    # Per day, keep the max single-source total (avoids cross-device double count).
    return {day: max(srcs.values()) for day, srcs in per_day_src.items()}


def run_block(df, steps_by_day, label):
    n = len(df)
    if n == 0:
        return f"\n  {label}: no runs in window.\n"
    total_mi = df["distance_mi"].sum()
    total_min = df["duration_min"].sum()
    h, m = divmod(int(round(total_min)), 60)
    long_i = df["distance_mi"].idxmax()
    fast_i = df["pace_min_per_mi"].idxmin()
    avg_pace = df["pace_min_per_mi"].mean()
    avg_hr = df["avg_hr"].mean()
    elev = df["elevation_ft"].sum() if df["elevation_ft"].notna().any() else 0.0
    cals = df["calories"].sum() if df["calories"].notna().any() else 0.0

    steps_total = sum(steps_by_day.values())
    step_days = len(steps_by_day)
    avg_steps = steps_total / step_days if step_days else 0

    lines = [
        f"\n═══════════════════════════════════",
        f"  {label}",
        f"═══════════════════════════════════",
        f"  Total runs:       {n}",
        f"  Total miles:      {total_mi:.1f} mi",
        f"  Total time:       {h}h {m % 60:02d}m",
        f"  Avg pace:         {format_pace(avg_pace)}",
        f"  Fastest run:      {format_pace(df.loc[fast_i,'pace_min_per_mi'])}"
        f"  ({df.loc[fast_i,'date'].strftime('%b %-d')}, "
        f"{df.loc[fast_i,'distance_mi']:.1f} mi)",
        f"  Longest run:      {df.loc[long_i,'distance_mi']:.1f} mi"
        f"  ({df.loc[long_i,'date'].strftime('%b %-d')})",
        f"  Avg distance/run: {total_mi/n:.1f} mi",
        f"  Avg heart rate:   "
        + (f"{avg_hr:.0f} bpm" if pd.notna(avg_hr) else "n/a"),
        f"  Total elevation:  {elev:,.0f} ft",
        f"  Total calories:   {cals:,.0f}",
        f"  ----",
        f"  Total steps:      {steps_total:,.0f}",
        f"  Active days:      {step_days}",
        f"  Avg steps/day:    {avg_steps:,.0f}",
        f"═══════════════════════════════════",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default="export.zip")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--start", default="2026-03-05",
                    help="Marathon-prep start date (inclusive), YYYY-MM-DD.")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    cache = f"output/.workouts_{args.year}.pkl"
    import os
    if os.path.exists(cache) and not args.no_cache:
        df = pd.read_pickle(cache)
    else:
        df = parse_workouts(args.zip, year=args.year)

    start = datetime.strptime(args.start, "%Y-%m-%d")

    print("Streaming steps from export.xml (one pass)...")
    steps = daily_steps(args.zip, args.year)
    steps_prep = {d: v for d, v in steps.items() if d >= args.start}

    df_prep = df[df["date"] >= start].reset_index(drop=True)

    out = run_block(df, steps, f"YTD {args.year} (all)")
    out += "\n"
    out += run_block(df_prep, steps_prep,
                     f"Marathon prep (from {start.strftime('%b %-d, %Y')})")
    print(out)
    with open("output/marathon_prep.txt", "w") as fh:
        fh.write(out)
    print("\nSaved -> output/marathon_prep.txt")


if __name__ == "__main__":
    main()
