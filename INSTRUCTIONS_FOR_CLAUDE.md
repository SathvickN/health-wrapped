# INSTRUCTIONS FOR CLAUDE
# apple-health-wrapped — Full Build Guide

I am giving you a file called `apple_health_export.zip`. This is a raw Apple Health data export from an iPhone. Your job is to build a complete Python project that parses this file and generates run stats, charts, and a shareable card image.

Read this entire document before writing any code. Every detail matters.

---

## What you are building

A Python project with these files:

```
apple-health-wrapped/
├── run.py                  ← main entry point
├── parse_health.py         ← XML parsing
├── compute_stats.py        ← aggregations and calculations
├── visualize.py            ← matplotlib charts
├── generate_card.py        ← Pillow card image
├── ai_summary.py           ← optional Ollama AI summary
├── requirements.txt
└── output/                 ← created at runtime, gitignored
```

---

## Step 1 — Understand the zip file structure

The zip Apple exports contains:

```
apple_health_export/
├── export.xml              ← THIS IS THE MAIN FILE. Everything is in here.
├── export_cda.xml          ← ignore this
└── workout-routes/         ← GPX files for each workout, ignore for now
    ├── route_2026-01-05.gpx
    └── ...
```

The `export.xml` file can be very large (500MB to 2GB for multi-year exports). Do NOT try to load it all into memory at once. Use iterative XML parsing with `xml.etree.ElementTree.iterparse`.

---

## Step 2 — Parse the XML (parse_health.py)

### How the XML is structured

Every data point in Apple Health is a `<Record>` element. Workouts (runs) are `<Workout>` elements.

**A workout element looks like this:**

```xml
<Workout
  workoutActivityType="HKWorkoutActivityTypeRunning"
  duration="52.34"
  durationUnit="min"
  totalDistance="5.23"
  totalDistanceUnit="mi"
  totalEnergyBurned="487"
  totalEnergyBurnedUnit="Cal"
  sourceName="Sathvick's Apple Watch Ultra"
  sourceVersion="10.3.1"
  creationDate="2026-05-30 07:14:22 -0700"
  startDate="2026-05-30 07:14:22 -0700"
  endDate="2026-05-30 08:06:56 -0700">

  <WorkoutStatistics
    type="HKQuantityTypeIdentifierHeartRate"
    startDate="2026-05-30 07:14:22 -0700"
    endDate="2026-05-30 08:06:56 -0700"
    average="148"
    minimum="112"
    maximum="179"
    unit="count/min"/>

  <WorkoutStatistics
    type="HKQuantityTypeIdentifierActiveEnergyBurned"
    .../>

</Workout>
```

**Key fields to extract from each running workout:**

| Field | XML attribute | Notes |
|-------|--------------|-------|
| Date | `startDate` | parse as datetime |
| Distance (miles) | `totalDistance` | check unit is "mi", convert if "km" |
| Duration (minutes) | `duration` | float |
| Calories | `totalEnergyBurned` | float |
| Avg HR | child `WorkoutStatistics` where type contains `HeartRate`, attribute `average` |
| Elevation | look for `WorkoutStatistics` where type contains `FlightsClimbed` or `ElevationAscended` |

**Filter for runs only:**

```python
workoutActivityType="HKWorkoutActivityTypeRunning"
```

Also include these as runs if present:
- `HKWorkoutActivityTypeTrailRunning`

### The parse function to write

```python
def parse_workouts(zip_path: str, year: int = None) -> pd.DataFrame:
    """
    Opens the zip, finds export.xml, iteratively parses it,
    extracts all running workouts, returns a clean DataFrame.
    
    Columns in output DataFrame:
    - date (datetime)
    - distance_mi (float)
    - duration_min (float)
    - pace_min_per_mi (float)  # computed: duration / distance
    - calories (float)
    - avg_hr (float or NaN)
    - max_hr (float or NaN)
    - elevation_ft (float or NaN)
    - source (str)  # device name
    """
```

**Important parsing details:**

1. Use `zipfile.ZipFile` to open the zip without extracting it to disk
2. Use `xml.etree.ElementTree.iterparse` for memory efficiency — do NOT use `ET.parse()` on large files
3. Parse dates with `datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")` — the timezone suffix varies
4. If distance is 0 or duration is 0, skip that workout (it's a corrupted record)
5. Compute `pace_min_per_mi = duration_min / distance_mi`
6. Skip obvious outliers: pace < 4.0 min/mi or pace > 20.0 min/mi (GPS errors)
7. If `year` is provided, filter to that year only

### Memory-efficient iterparse pattern to use:

```python
import zipfile
import xml.etree.ElementTree as ET

with zipfile.ZipFile(zip_path) as zf:
    with zf.open('apple_health_export/export.xml') as f:
        current_workout = None
        for event, elem in ET.iterparse(f, events=('start', 'end')):
            if event == 'start' and elem.tag == 'Workout':
                if elem.attrib.get('workoutActivityType') in RUNNING_TYPES:
                    current_workout = dict(elem.attrib)
                    current_workout['hr_stats'] = []
            elif event == 'start' and elem.tag == 'WorkoutStatistics' and current_workout:
                current_workout['hr_stats'].append(dict(elem.attrib))
            elif event == 'end' and elem.tag == 'Workout':
                if current_workout:
                    workouts.append(process_workout(current_workout))
                    current_workout = None
                elem.clear()  # CRITICAL: free memory
```

---

## Step 3 — Compute stats (compute_stats.py)

Write a function `compute_all_stats(df: pd.DataFrame) -> dict` that returns a dictionary with:

```python
{
    "total_runs": int,
    "total_miles": float,           # sum of distance_mi
    "total_time_hours": float,      # sum of duration_min / 60
    "avg_pace": float,              # mean of pace_min_per_mi
    "best_pace": float,             # min of pace_min_per_mi
    "best_pace_date": datetime,
    "longest_run_miles": float,
    "longest_run_date": datetime,
    "avg_hr": float,                # mean of avg_hr, ignore NaN
    "total_calories": float,
    "monthly_miles": pd.Series,     # index=month name, values=miles
    "weekly_miles": pd.Series,      # index=week number, values=miles
    "pace_by_month": pd.Series,     # index=month name, values=avg pace
    "hr_zones": dict,               # {Z1: %, Z2: %, Z3: %, Z4: %} based on avg_hr
    "best_month": str,              # month name with most miles
    "best_month_miles": float,
    "pace_improvement": float,      # first month avg pace - last month avg pace (positive = faster)
}
```

**HR zone calculation** — use % of max HR. Assume max HR = 220 - age. If age unknown, use 185 as max HR for a reasonable default.

```
Z1 easy:     < 60% max HR
Z2 aerobic:  60-70% max HR
Z3 tempo:    70-80% max HR
Z4 hard:     > 80% max HR
```

**Format pace as string helper:**

```python
def format_pace(pace_float: float) -> str:
    """Convert 8.75 to '8:45 /mi'"""
    minutes = int(pace_float)
    seconds = int((pace_float - minutes) * 60)
    return f"{minutes}:{seconds:02d} /mi"
```

---

## Step 4 — Visualize (visualize.py)

Use `matplotlib`. Dark theme throughout using `plt.style.use('dark_background')`.

**Color palette to use:**

```python
BLUE = "#4FC3F7"
GREEN = "#81C784"
ORANGE = "#FFB74D"
RED = "#E57373"
WHITE = "#FFFFFF"
GRAY = "#B0BEC5"
BG = "#1A1A2E"
```

### Chart 1: Monthly mileage bar chart

- X axis: month names (Jan, Feb, Mar...)
- Y axis: miles
- Bar color: BLUE, highlight the best month in ORANGE
- Title: "Monthly Mileage — 2026"
- Show value labels on top of each bar
- Save as `output/monthly_mileage.png` at 300 DPI

### Chart 2: Pace progression line chart

- X axis: month names
- Y axis: avg pace per month (formatted as MM:SS — use secondary y-axis label trick)
- Line color: GREEN
- Add a horizontal dashed line for overall average pace in GRAY
- Title: "Avg Pace by Month — 2026"
- Save as `output/pace_trend.png` at 300 DPI

### Chart 3: HR zones donut chart

- Donut chart (not pie — use `wedgeprops=dict(width=0.5)`)
- Colors: Z1=BLUE, Z2=GREEN, Z3=ORANGE, Z4=RED
- Center text: "HR Zones"
- Legend with percentages
- Title: "Heart Rate Zone Distribution"
- Save as `output/hr_zones.png` at 300 DPI

---

## Step 5 — Generate the shareable card (generate_card.py)

Use `Pillow` (PIL). This is the main shareable output — make it look good.

**Card dimensions:** 1080 x 1080px (square, Instagram-friendly)

**Design:**

```
Background: dark navy (#0D1117) — same as GitHub dark
Font: use a system font. Try these in order:
  1. /System/Library/Fonts/Helvetica.ttc (macOS)
  2. /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf (Linux)
  3. ImageFont.load_default() as fallback

Layout (from top, with padding=60px):

[60px top padding]
"🏃 2026 Running Wrapped"       — white, 36px, centered
"Sathvick · {total_runs} runs"  — gray, 20px, centered
[40px gap]

[Stats grid — 2x3, each cell ~300x140px]
  Total Miles    |  Total Time
  312.4          |  52h 14m
  ───────────────────────────────
  Longest Run    |  Best Pace
  16.2 mi        |  7:58 /mi
  ───────────────────────────────
  Avg Heart Rate |  Calories
  148 bpm        |  24,830 cal

[30px gap]
[Divider line — gray, 80% width]
[20px gap]

"Pace improved 37s/mi from Jan → May"  — green, 18px, centered

[20px gap]
[AI summary if available — gray italic, 16px, centered, max 2 lines]

[Bottom padding]
"github.com/yourusername/apple-health-wrapped" — gray small text
```

**Stat cell styling:**
- Label: gray (#8B949E), 16px
- Value: white, 42px bold
- Each cell has a subtle border (#21262D)

Save as `output/year_in_review_card.png`.

---

## Step 6 — AI summary (ai_summary.py)

Only runs if `--ai-summary` flag is passed. Requires Ollama running locally.

```python
import requests

def generate_summary(stats: dict) -> str:
    prompt = f"""You are a running coach. Given these stats, write exactly 2 sentences summarizing this runner's year. Be specific, encouraging, and mention one key achievement and one area to focus on next.

Stats:
- Total runs: {stats['total_runs']}
- Total miles: {stats['total_miles']:.1f}
- Best pace: {format_pace(stats['best_pace'])}
- Avg pace: {format_pace(stats['avg_pace'])}
- Longest run: {stats['longest_run_miles']:.1f} miles
- Pace improvement: {stats['pace_improvement']:.0f} seconds/mile faster since January

Write only the 2 sentences. No preamble."""

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
        timeout=30
    )
    return response.json()["response"].strip()
```

If Ollama is not running or times out, return an empty string gracefully — do not crash the whole run.

---

## Step 7 — Entry point (run.py)

```python
import argparse
from parse_health import parse_workouts
from compute_stats import compute_all_stats
from visualize import generate_all_charts
from generate_card import generate_card
from ai_summary import generate_summary
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default="apple_health_export.zip")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--stats-only", action="store_true")
    parser.add_argument("--ai-summary", action="store_true")
    parser.add_argument("--name", default="Your Name", help="Name shown on card")
    args = parser.parse_args()

    os.makedirs("output", exist_ok=True)

    print(f"Parsing {args.zip}...")
    df = parse_workouts(args.zip, year=args.year)
    print(f"Found {len(df)} running workouts in {args.year}")

    if len(df) == 0:
        print("No runs found. Check that the zip file contains Apple Health export data.")
        return

    stats = compute_all_stats(df)

    # Print stats to console
    print_stats(stats)

    if args.stats_only:
        return

    print("Generating charts...")
    generate_all_charts(stats, df)

    ai_text = ""
    if args.ai_summary:
        print("Generating AI summary...")
        ai_text = generate_summary(stats)

    print("Generating shareable card...")
    generate_card(stats, name=args.name, ai_text=ai_text)

    print("\nDone! Check the output/ folder.")
    print("  output/monthly_mileage.png")
    print("  output/pace_trend.png")
    print("  output/hr_zones.png")
    print("  output/year_in_review_card.png")

if __name__ == "__main__":
    main()
```

---

## Step 8 — requirements.txt

```
pandas>=2.0.0
matplotlib>=3.7.0
Pillow>=10.0.0
requests>=2.28.0
tqdm>=4.65.0
numpy>=1.24.0
```

---

## Step 9 — .gitignore

Create a `.gitignore` with:

```
# Health data — NEVER commit this
apple_health_export.zip
apple_health_export/
export.xml
output/

# Python
__pycache__/
*.pyc
.env
venv/
```

---

## Step 10 — Test it

After writing all files, test with:

```bash
python run.py --zip apple_health_export.zip --year 2026 --name "Sathvick"
```

If there are fewer than 5 runs, the pace trend chart may look empty — handle this gracefully by skipping that chart and printing a message.

---

## Common errors to handle

| Error | Cause | Fix |
|-------|-------|-----|
| `KeyError: 'apple_health_export/export.xml'` | Zip structure differs | Try `apple_health_export/Export.xml` or list zip contents and find the xml |
| `ZeroDivisionError` in pace calc | distance is 0 | Skip runs with distance < 0.1 mi |
| Pillow font not found | system font missing | Fall back to `ImageFont.load_default()` |
| Ollama timeout | model not running | Catch `requests.exceptions.ConnectionError`, return empty string |
| Very large XML (>1GB) | multi-year export | `iterparse` + `elem.clear()` handles this — do not use `ET.parse()` |

---

## What good output looks like

When you run `python run.py --stats-only`, the console should print something like:

```
Parsing apple_health_export.zip...
Found 47 running workouts in 2026

═══════════════════════════════════
  2026 Running Stats
═══════════════════════════════════
  Total runs:       47
  Total miles:      312.4 mi
  Total time:       52h 14m
  Avg pace:         8:51 /mi
  Best pace:        7:58 /mi  (Mar 3)
  Longest run:      16.2 mi   (Apr 12)
  Avg heart rate:   148 bpm
  Best month:       April — 89.1 mi

  Pace trend:       9:21 → 8:44  (↓ 37s/mi improvement)

  HR Zones:
    Z1 easy         34%
    Z2 aerobic      41%
    Z3 tempo        18%
    Z4 hard          7%
═══════════════════════════════════
```

---

## Final checklist before you say you're done

- [ ] `parse_health.py` uses `iterparse` not `ET.parse()`
- [ ] `elem.clear()` is called after processing each Workout element
- [ ] Division by zero is handled in pace calculation
- [ ] Font loading has a fallback
- [ ] Ollama call is wrapped in try/except
- [ ] `output/` folder is created if it doesn't exist
- [ ] `.gitignore` excludes the zip and output folder
- [ ] All 4 output images are saved at 300 DPI
- [ ] Code runs end-to-end with `python run.py`
