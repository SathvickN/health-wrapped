# 🏃 apple-health-wrapped

> Your Apple Health data, finally making sense. Generate beautiful run stats, charts, and a shareable year-in-review card from your raw Apple Health export.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![No API Key](https://img.shields.io/badge/API%20key-not%20required-brightgreen)

---

## What this does

Apple Health silently collects years of your run data. This project parses your raw `export.xml` and generates:

- **Run stats dashboard** — total miles, time, pace trends, HR zones, elevation
- **Monthly mileage chart** — bar chart showing your training volume over time
- **Pace progression chart** — are you actually getting faster?
- **Year-in-review card** — one shareable PNG with your biggest numbers
- **AI summary** — a 2-sentence narrative of your training year (uses Ollama locally, no data leaves your machine)

---

## Sample output

```
2026 Running Stats ─────────────────────────────
Total runs:          47
Total miles:         312.4 mi
Total time:          52h 14m
Longest run:         16.2 mi  (Apr 12)
Best pace:           7:58 /mi (Mar 3)
Avg heart rate:      148 bpm
Best month:          April — 89.1 mi

Pace trend:   Jan 9:21 → May 8:44  ↓ 37s/mi improvement

HR zones:
  Z1 easy      34%  ████████░░░░░░
  Z2 aerobic   41%  ██████████░░░░
  Z3 tempo     18%  █████░░░░░░░░░
  Z4 hard       7%  ██░░░░░░░░░░░░
```

---

## Setup

### Requirements

- Python 3.10+
- Your Apple Health export zip (see instructions below)

### Install

```bash
git clone https://github.com/yourusername/apple-health-wrapped
cd apple-health-wrapped
pip install -r requirements.txt
```

### Get your Apple Health data

1. Open the **Health app** on your iPhone
2. Tap **Summary** at the bottom
3. Tap your **profile picture or initials** (top right)
4. Scroll down and tap **Export All Health Data**
5. Tap **Export** — this creates a zip file
6. AirDrop or transfer the zip to your computer
7. Place it in the project root as `apple_health_export.zip`

### Run

```bash
# Parse and generate everything
python run.py

# Just the stats (no charts)
python run.py --stats-only

# Specific year
python run.py --year 2026

# With AI summary (requires Ollama running locally)
python run.py --ai-summary
```

Output goes to `output/` folder:
- `output/stats.txt` — full text stats
- `output/monthly_mileage.png` — bar chart
- `output/pace_trend.png` — line chart
- `output/hr_zones.png` — pie/bar chart
- `output/year_in_review_card.png` — shareable card

---

## Optional: AI summary with Ollama

For a local AI-generated narrative summary of your training year:

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.2:3b

# Then run with flag
python run.py --ai-summary
```

Everything stays on your machine. No data is sent anywhere.

---

## Project structure

```
apple-health-wrapped/
├── run.py                  ← entry point, run this
├── parse_health.py         ← reads export.xml, extracts workouts
├── compute_stats.py        ← all the math and aggregations
├── visualize.py            ← matplotlib charts
├── generate_card.py        ← Pillow year-in-review card
├── ai_summary.py           ← optional Ollama integration
├── requirements.txt
├── sample_output.png       ← example card (included in repo)
└── README.md
```

---

## requirements.txt

```
pandas
matplotlib
Pillow
requests
tqdm
```

---

## Use your own data

This project is designed to be personal. Clone it, drop in your own `apple_health_export.zip`, and run it. The only file you need is the zip Apple gives you — no accounts, no API keys, no subscriptions.

---

## Privacy

Your health data never leaves your machine. The only network request is the optional Ollama call, which also runs locally. The zip file is read in-memory and the raw XML is never written to disk by this project.

---

## Contributing

PRs welcome. Ideas:
- Support for Strava/Garmin GPX overlays
- Weekly streak tracking
- Weight and body composition trends
- Sleep vs run performance correlation

---

## License

MIT
