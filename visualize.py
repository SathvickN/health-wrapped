"""Matplotlib charts. Dark theme. Saves PNGs to output/ at 300 DPI."""

import os

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

BLUE = "#4FC3F7"
GREEN = "#81C784"
ORANGE = "#FFB74D"
RED = "#E57373"
WHITE = "#FFFFFF"
GRAY = "#B0BEC5"
BG = "#1A1A2E"

OUT = "output"


def _new_fig():
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    return fig, ax


def _save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=300, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_monthly_mileage(stats, year):
    miles = stats["monthly_miles"]
    best = stats["best_month"]
    fig, ax = _new_fig()
    colors = [ORANGE if m == best else BLUE for m in miles.index]
    bars = ax.bar(miles.index, miles.values, color=colors)
    for b, v in zip(bars, miles.values):
        ax.text(
            b.get_x() + b.get_width() / 2,
            b.get_height(),
            f"{v:.0f}",
            ha="center",
            va="bottom",
            color=WHITE,
            fontsize=10,
        )
    ax.set_title(f"Monthly Mileage — {year}", color=WHITE, fontsize=16)
    ax.set_ylabel("Miles", color=GRAY)
    ax.tick_params(colors=GRAY)
    return _save(fig, "monthly_mileage.png")


def chart_hr_zones(stats):
    zones = stats["hr_zones"]
    if sum(zones.values()) == 0:
        print("  Skipping HR zones chart (no heart-rate data).")
        return None
    labels = ["Z1 easy", "Z2 aerobic", "Z3 tempo", "Z4 hard"]
    vals = [zones["Z1"], zones["Z2"], zones["Z3"], zones["Z4"]]
    colors = [BLUE, GREEN, ORANGE, RED]
    # Drop empty wedges to avoid clutter.
    data = [(l, v, c) for l, v, c in zip(labels, vals, colors) if v > 0]
    labels, vals, colors = zip(*data)

    fig, ax = _new_fig()
    wedges, _ = ax.pie(vals, colors=colors, startangle=90,
                       wedgeprops=dict(width=0.5))
    ax.text(0, 0, "HR\nZones", ha="center", va="center", color=WHITE, fontsize=18)
    ax.legend(
        wedges,
        [f"{l} — {v:.0f}%" for l, v in zip(labels, vals)],
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        facecolor=BG,
        edgecolor=GRAY,
        labelcolor=WHITE,
    )
    ax.set_title("Heart Rate Zone Distribution", color=WHITE, fontsize=16)
    return _save(fig, "hr_zones.png")


def _activity_bar(series, title, ylabel, fname, fmt, year):
    """Generic vertical bar chart over activity types (top 8)."""
    s = series.head(8)
    if s.empty:
        return None
    fig, ax = _new_fig()
    colors = [BLUE if i else ORANGE for i in range(len(s))]  # top one highlighted
    bars = ax.bar(range(len(s)), s.values, color=colors)
    for b, v in zip(bars, s.values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt(v),
                ha="center", va="bottom", color=WHITE, fontsize=10)
    ax.set_xticks(range(len(s)))
    ax.set_xticklabels([n[:12] for n in s.index], rotation=35, ha="right")
    ax.set_title(f"{title} — {year}", color=WHITE, fontsize=16)
    ax.set_ylabel(ylabel, color=GRAY)
    ax.tick_params(colors=GRAY)
    fig.tight_layout()
    return _save(fig, fname)


def chart_activity_time(stats, year):
    hours = stats["minutes_by_activity"] / 60.0
    return _activity_bar(hours, "Time by Activity", "Hours",
                         "activity_time.png", lambda v: f"{v:.1f}", year)


def chart_activity_calories(stats, year):
    cals = stats["calories_by_activity"].dropna()
    if cals.sum() <= 0:
        print("  Skipping activity calories chart (no calorie data).")
        return None
    return _activity_bar(cals, "Calories by Activity", "Calories",
                         "activity_calories.png", lambda v: f"{v:,.0f}", year)


def generate_all_charts(stats, df, year=2026):
    os.makedirs(OUT, exist_ok=True)
    chart_monthly_mileage(stats, year)
    chart_hr_zones(stats)


def generate_activity_charts(stats, year=2026):
    os.makedirs(OUT, exist_ok=True)
    chart_activity_time(stats, year)
    chart_activity_calories(stats, year)
