"""Aggregate the parsed workouts DataFrame into a stats dict."""

import calendar
import random

import numpy as np
import pandas as pd

# (name, kcal each, ...) for the fun calorie-equivalent line.
_FOODS = [
    ("Big Macs", 563),
    ("pizza slices", 285),
    ("glazed donuts", 260),
    ("Chipotle burritos", 1075),
    ("pints of ice cream", 1000),
    ("cheeseburgers", 300),
    ("chocolate bars", 230),
    ("cans of soda", 140),
    ("tacos", 210),
]


def calorie_fun_line(total_cal: float) -> str:
    """e.g. 'Enough to torch ~43 Big Macs.'"""
    if not total_cal or total_cal <= 0:
        return ""
    name, kcal = random.choice(_FOODS)
    n = max(1, round(total_cal / kcal))
    return f"Enough to torch ~{n:,} {name}."

# Default max HR when age is unknown.
DEFAULT_MAX_HR = 185.0

_MONTH_ORDER = list(calendar.month_abbr)[1:]  # Jan..Dec


def format_pace(pace_float: float) -> str:
    """Convert 8.75 -> '8:45 /mi'."""
    if pace_float is None or pd.isna(pace_float):
        return "—"
    minutes = int(pace_float)
    seconds = int(round((pace_float - minutes) * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d} /mi"


def _hr_zones(df: pd.DataFrame, max_hr: float) -> dict:
    """Distribute runs into 4 HR zones by % of max HR (based on avg_hr)."""
    hrs = df["avg_hr"].dropna()
    zones = {"Z1": 0.0, "Z2": 0.0, "Z3": 0.0, "Z4": 0.0}
    if len(hrs) == 0:
        return zones
    counts = {"Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0}
    for hr in hrs:
        pct = hr / max_hr
        if pct < 0.60:
            counts["Z1"] += 1
        elif pct < 0.70:
            counts["Z2"] += 1
        elif pct < 0.80:
            counts["Z3"] += 1
        else:
            counts["Z4"] += 1
    total = len(hrs)
    return {z: round(100.0 * c / total, 1) for z, c in counts.items()}


def compute_activity_stats(df: pd.DataFrame) -> dict:
    """Aggregate ALL workout types into a stats dict for the Activity card."""
    df = df.copy()
    has_cal = df["calories"].notna().any()
    has_dist = df["distance_mi"].notna().any()
    has_hr = df["avg_hr"].notna().any()

    minutes_by_activity = (
        df.groupby("activity")["duration_min"].sum().sort_values(ascending=False)
    )
    count_by_activity = (
        df.groupby("activity").size().sort_values(ascending=False)
    )

    top_activity = minutes_by_activity.index[0]
    most_frequent = count_by_activity.index[0]

    return {
        "total_workouts": len(df),
        "total_time_hours": float(df["duration_min"].sum() / 60.0),
        "total_calories": float(df["calories"].sum()) if has_cal else 0.0,
        "total_distance_mi": float(df["distance_mi"].sum()) if has_dist else 0.0,
        "avg_hr": float(df["avg_hr"].mean()) if has_hr else float("nan"),
        "active_days": int(df["date"].dt.date.nunique()),
        "n_types": int(minutes_by_activity.size),
        "minutes_by_activity": minutes_by_activity,
        "count_by_activity": count_by_activity,
        "top_activity": top_activity,
        "top_activity_hours": float(minutes_by_activity.iloc[0] / 60.0),
        "most_frequent": most_frequent,
        "most_frequent_count": int(count_by_activity.iloc[0]),
    }


def compute_all_stats(df: pd.DataFrame, max_hr: float = DEFAULT_MAX_HR) -> dict:
    df = df.copy()
    df["month"] = df["date"].dt.month
    df["month_name"] = df["date"].dt.strftime("%b")
    df["week"] = df["date"].dt.isocalendar().week.astype(int)

    total_runs = len(df)
    total_miles = float(df["distance_mi"].sum())
    total_time_hours = float(df["duration_min"].sum() / 60.0)
    avg_pace = float(df["pace_min_per_mi"].mean())

    best_idx = df["pace_min_per_mi"].idxmin()
    best_pace = float(df.loc[best_idx, "pace_min_per_mi"])
    best_pace_date = df.loc[best_idx, "date"]

    long_idx = df["distance_mi"].idxmax()
    longest_run_miles = float(df.loc[long_idx, "distance_mi"])
    longest_run_date = df.loc[long_idx, "date"]

    avg_hr = float(df["avg_hr"].mean()) if df["avg_hr"].notna().any() else float("nan")
    total_calories = float(df["calories"].sum()) if df["calories"].notna().any() else 0.0

    # Monthly aggregates, ordered Jan..Dec but only months present.
    present_months = [m for m in _MONTH_ORDER if m in set(df["month_name"])]
    monthly_miles = (
        df.groupby("month_name")["distance_mi"].sum().reindex(present_months)
    )
    pace_by_month = (
        df.groupby("month_name")["pace_min_per_mi"].mean().reindex(present_months)
    )
    weekly_miles = df.groupby("week")["distance_mi"].sum().sort_index()

    best_month = monthly_miles.idxmax()
    best_month_miles = float(monthly_miles.max())

    # Pace improvement: first present month avg pace - last present month avg.
    first_month_pace = pace_by_month.iloc[0]
    last_month_pace = pace_by_month.iloc[-1]
    pace_improvement = float((first_month_pace - last_month_pace) * 60.0)  # sec/mi

    return {
        "total_runs": total_runs,
        "total_miles": total_miles,
        "total_time_hours": total_time_hours,
        "avg_pace": avg_pace,
        "best_pace": best_pace,
        "best_pace_date": best_pace_date,
        "longest_run_miles": longest_run_miles,
        "longest_run_date": longest_run_date,
        "avg_hr": avg_hr,
        "total_calories": total_calories,
        "monthly_miles": monthly_miles,
        "weekly_miles": weekly_miles,
        "pace_by_month": pace_by_month,
        "hr_zones": _hr_zones(df, max_hr),
        "best_month": best_month,
        "best_month_miles": best_month_miles,
        "pace_improvement": pace_improvement,
        "first_month_pace": float(first_month_pace),
        "last_month_pace": float(last_month_pace),
        "max_hr_used": max_hr,
    }
