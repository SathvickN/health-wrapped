"""Pillow 1080x1080 shareable year-in-review card."""

import os

from PIL import Image, ImageDraw, ImageFont

from compute_stats import format_pace, calorie_fun_line

W = H = 1080
PAD = 60
BG = (13, 17, 23)        # #0D1117
WHITE = (255, 255, 255)
GRAY = (139, 148, 158)   # #8B949E
GREEN = (129, 199, 132)
RED = (229, 115, 115)    # #E57373
BLUE = (79, 195, 247)    # #4FC3F7
ORANGE = (255, 183, 77)  # #FFB74D
BORDER = (33, 38, 45)    # #21262D

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_center(draw, cx, y, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text((cx - w / 2, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def _wrap(text, font, draw, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_bar_chart(d, stats, x0, y0, x1, y1, f_label, f_small, best=None):
    """Native monthly-mileage bars inside the card box (x0,y0)-(x1,y1)."""
    miles = stats["monthly_miles"]
    months = list(miles.index)
    vals = list(miles.values)
    if not months:
        return
    cx = (x0 + x1) / 2

    # Title.
    th = _text_center(d, cx, y0, "Monthly Mileage", f_label, GRAY)
    chart_top = y0 + th + 18
    label_h = 24                      # space for month label under axis
    base_y = y1 - label_h
    chart_h = base_y - chart_top
    if chart_h <= 0:
        return

    vmax = max(vals) or 1
    n = len(months)
    slot = (x1 - x0) / n
    bw = slot * 0.6
    for i, (mo, v) in enumerate(zip(months, vals)):
        sx = x0 + i * slot + (slot - bw) / 2
        bh = (v / vmax) * chart_h
        top = base_y - bh
        color = ORANGE if mo == best else BLUE
        d.rectangle([sx, top, sx + bw, base_y], fill=color)
        bcx = sx + bw / 2
        # Value above bar.
        vt = f"{v:.0f}"
        vb = d.textbbox((0, 0), vt, font=f_small)
        d.text((bcx - vb[2] / 2, top - 22), vt, font=f_small, fill=WHITE)
        # Month label below axis.
        mb = d.textbbox((0, 0), mo, font=f_small)
        d.text((bcx - mb[2] / 2, base_y + 4), mo, font=f_small, fill=GRAY)


def generate_card(stats, name="Your Name", ai_text="", year=2026,
                  out_path="output/run_report_card.png"):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    cx = W / 2

    f_title = _font(46)
    f_sub = _font(24)
    f_label = _font(20)
    f_value = _font(50)
    f_note = _font(22)
    f_small = _font(18)

    y = PAD
    y += _text_center(d, cx, y, f"{year} Run Report", f_title, WHITE) + 16
    y += _text_center(d, cx, y, f"{name} · {year}", f_sub, GRAY) + 36

    # Stats grid 4x2 — maximise stat density.
    h_m = int(stats["total_time_hours"])
    m_m = int(round((stats["total_time_hours"] - h_m) * 60))
    hr = stats["avg_hr"]
    cells = [
        ("Total Runs", f"{stats['total_runs']}"),
        ("Total Miles", f"{stats['total_miles']:.1f}"),
        ("Total Time", f"{h_m}h {m_m:02d}m"),
        ("Avg Pace", format_pace(stats["avg_pace"]).replace(" /mi", "")),
        ("Best Pace", format_pace(stats["best_pace"]).replace(" /mi", "")),
        ("Longest Run", f"{stats['longest_run_miles']:.1f} mi"),
        ("Avg Heart Rate", f"{hr:.0f} bpm" if hr == hr else "—"),
        ("Calories", f"{stats['total_calories']:,.0f}"),
    ]

    grid_w = W - 2 * PAD
    col_w = grid_w / 2
    n_rows = (len(cells) + 1) // 2
    row_h = 124
    f_val = _font(44)
    grid_top = y
    for i, (label, value) in enumerate(cells):
        r, c = divmod(i, 2)
        x0 = PAD + c * col_w
        y0 = grid_top + r * row_h
        d.rectangle([x0 + 6, y0 + 6, x0 + col_w - 6, y0 + row_h - 6],
                    outline=BORDER, width=2)
        ccx = x0 + col_w / 2
        d.text((ccx - d.textbbox((0, 0), label, font=f_label)[2] / 2, y0 + 18),
               label, font=f_label, fill=GRAY)
        vb = d.textbbox((0, 0), value, font=f_val)
        d.text((ccx - vb[2] / 2, y0 + 50), value, font=f_val, fill=WHITE)
    y = grid_top + n_rows * row_h + 14

    # Fun calorie-equivalent line.
    fun = calorie_fun_line(stats.get("total_calories", 0))
    if fun:
        y += _text_center(d, cx, y, fun, f_small, GREEN) + 8

    # AI summary (optional, wrapped, max ~2 lines).
    if ai_text:
        for line in _wrap(ai_text, f_small, d, int(grid_w * 0.9))[:2]:
            y += _text_center(d, cx, y, line, f_small, GRAY) + 8

    # Monthly mileage bar chart (fills lower area, theme-matched).
    foot_y = H - PAD - 10
    _draw_bar_chart(d, stats, PAD, y + 10, W - PAD, foot_y - 36,
                    f_label, f_small, best=stats["best_month"])

    # Footer.
    _text_center(d, cx, foot_y, f"{year} · Apple Health", f_small, GRAY)

    img.save(out_path)
    return out_path
