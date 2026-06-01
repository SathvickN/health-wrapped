"""Activity Report — insights across ALL workout types (run, walk, cycle,
strength, ...). Companion to run.py.

    python run.py       --zip export.zip --year 2026 --name "You"   # runs only
    python activity.py  --zip export.zip --year 2026 --name "You"   # everything
"""

import argparse
import os

from PIL import Image, ImageDraw

import generate_card as gc
from parse_health import parse_activities
from compute_stats import compute_activity_stats, calorie_fun_line

OUT = "output/activity_review_card.png"


def _fit_value(d, text, max_w, sizes=(38, 32, 26, 22)):
    """Pick the largest value font that fits the tile width."""
    for s in sizes:
        f = gc._font(s)
        if d.textbbox((0, 0), text, font=f)[2] <= max_w:
            return f
    return gc._font(sizes[-1])


def _draw_hbars(d, series, x0, y0, x1, y1, title):
    """Horizontal bars: time per activity type (top rows)."""
    gc._text_center(d, (x0 + x1) / 2, y0, title, gc._font(20), gc.GRAY)
    top = series.head(6)
    if top.empty:
        return
    row_top = y0 + 34
    avail = y1 - row_top
    rh = avail / len(top)
    name_w = 230
    bar_x0 = x0 + name_w
    bar_x1 = x1 - 96
    vmax = float(top.max()) or 1.0
    f_name = gc._font(18)
    f_val = gc._font(17)
    for i, (name, mins) in enumerate(top.items()):
        cy = row_top + i * rh + rh / 2
        bh = min(26, rh - 10)
        d.text((x0, cy - 10), name[:18], font=f_name, fill=gc.WHITE)
        seg = (mins / vmax) * (bar_x1 - bar_x0)
        d.rectangle([bar_x0, cy - bh / 2, bar_x0 + max(2, seg), cy + bh / 2],
                    fill=gc.BLUE)
        h = int(mins // 60)
        m = int(mins % 60)
        label = f"{h}h {m:02d}m" if h else f"{m}m"
        d.text((bar_x1 + 10, cy - 9), label, font=f_val, fill=gc.GRAY)


def build_card(stats, name, year, out_path=OUT):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    W = H = gc.W
    PAD = gc.PAD
    img = Image.new("RGB", (W, H), gc.BG)
    d = ImageDraw.Draw(img)
    cx = W / 2

    f_title = gc._font(46)
    f_sub = gc._font(24)
    f_label = gc._font(19)
    f_small = gc._font(18)

    y = PAD
    y += gc._text_center(d, cx, y, f"{year} Activity Report", f_title, gc.WHITE) + 16
    y += gc._text_center(d, cx, y, f"{name} · {year}", f_sub, gc.GRAY) + 32

    h_h = int(stats["total_time_hours"])
    h_m = int(round((stats["total_time_hours"] - h_h) * 60))
    hr = stats["avg_hr"]
    cells = [
        ("Workouts", f"{stats['total_workouts']}"),
        ("Active Time", f"{h_h}h {h_m:02d}m"),
        ("Calories", f"{stats['total_calories']:,.0f}"),
        ("Activity Types", f"{stats['n_types']}"),
        ("Total Distance", f"{stats['total_distance_mi']:.0f} mi"),
        ("Avg Heart Rate", f"{hr:.0f} bpm" if hr == hr else "—"),
        ("Active Days", f"{stats['active_days']}"),
        ("Top Activity", stats["top_activity"]),
    ]

    grid_w = W - 2 * PAD
    col_w = grid_w / 2
    n_rows = (len(cells) + 1) // 2
    row_h = 110
    grid_top = y
    for i, (label, value) in enumerate(cells):
        r, c = divmod(i, 2)
        x0 = PAD + c * col_w
        y0 = grid_top + r * row_h
        d.rectangle([x0 + 6, y0 + 6, x0 + col_w - 6, y0 + row_h - 6],
                    outline=gc.BORDER, width=2)
        ccx = x0 + col_w / 2
        d.text((ccx - d.textbbox((0, 0), label, font=f_label)[2] / 2, y0 + 16),
               label, font=f_label, fill=gc.GRAY)
        fv = _fit_value(d, value, col_w - 40)
        vb = d.textbbox((0, 0), value, font=fv)
        d.text((ccx - vb[2] / 2, y0 + 46), value, font=fv, fill=gc.WHITE)
    y = grid_top + n_rows * row_h + 14

    fun = calorie_fun_line(stats["total_calories"])
    if fun:
        y += gc._text_center(d, cx, y, fun, f_small, gc.GREEN) + 8

    foot_y = H - PAD - 10
    _draw_hbars(d, stats["minutes_by_activity"], PAD, y + 6, W - PAD,
                foot_y - 36, "Time by Activity")
    gc._text_center(d, cx, foot_y, f"{year} · Apple Health", f_small, gc.GRAY)

    img.save(out_path)
    return out_path


def print_stats(stats, year):
    lines = [
        "",
        "═══════════════════════════════════",
        f"  {year} Activity Report",
        "═══════════════════════════════════",
        f"  Total workouts:   {stats['total_workouts']}",
        f"  Active time:      {int(stats['total_time_hours'])}h "
        f"{int(round((stats['total_time_hours'] % 1) * 60)):02d}m",
        f"  Total calories:   {stats['total_calories']:,.0f}",
        f"  Total distance:   {stats['total_distance_mi']:.1f} mi",
        f"  Activity types:   {stats['n_types']}",
        f"  Active days:      {stats['active_days']}",
        f"  Top activity:     {stats['top_activity']} "
        f"({stats['top_activity_hours']:.1f} h)",
        f"  Most frequent:    {stats['most_frequent']} "
        f"({stats['most_frequent_count']}x)",
        "  ----",
        "  Time by activity:",
    ]
    for name, mins in stats["minutes_by_activity"].items():
        lines.append(f"    {name:<22} {mins/60:>6.1f} h")
    lines.append("═══════════════════════════════════")
    text = "\n".join(lines)
    print(text)
    with open("output/activity_stats.txt", "w") as fh:
        fh.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default="apple_health_export.zip")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--name", default="Your Name")
    ap.add_argument("--stats-only", action="store_true")
    args = ap.parse_args()

    os.makedirs("output", exist_ok=True)
    print(f"Parsing {args.zip} (all activities)...")
    df = parse_activities(args.zip, year=args.year)
    print(f"Found {len(df)} workouts in {args.year}")
    if len(df) == 0:
        print("No workouts found in this year.")
        return

    stats = compute_activity_stats(df)
    print_stats(stats, args.year)
    if args.stats_only:
        return

    print("\nGenerating activity card...")
    build_card(stats, name=args.name, year=args.year)
    print("\nDone! Check the output/ folder.")
    for f in ("activity_stats.txt", "activity_review_card.png"):
        print(f"  output/{f}")


if __name__ == "__main__":
    main()
