# Apple Health Wrapped 🏃

Turn your Apple Health running data into a Spotify-Wrapped-style stats card,
charts, and a text report — all processed **locally** on your machine. No data
leaves your computer.

> The `output/` folder and any health export are git-ignored. Your data is
> never committed.

> **Gotcha we hit (and fixed):** logging the same run in 3 apps (Apple Watch +
> Strava + Runna) triple-counted mileage — 215 mi showed as 546 mi — until we
> added [start-time de-duplication](#how-dedup-works).

---

## What you get

Running into `output/`:

| File | What |
|------|------|
| `year_in_review_card.png` | Shareable 1080×1080 card: 8 stat tiles + monthly bar chart |
| `monthly_mileage.png` | Bar chart of miles per month |
| `pace_trend.png` | Avg pace per month (line) |
| `hr_zones.png` | Heart-rate zone distribution (pie) |
| `stats.txt` | Plain-text year summary |
| `marathon_prep.txt` | YTD vs. training-block comparison (optional tool) |

Stats are **de-duplicated**: if you log the same run in multiple apps
(Apple Watch + Strava + Runna), it's counted once. See
[How dedup works](#how-dedup-works).

---

## Setup

Requires **Python 3.10+**.

```bash
git clone <your-repo-url>
cd health-wrapped

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Export your Apple Health data

1. On iPhone, open **Health** app.
2. Tap your **profile picture** (top right).
3. Scroll down → **Export All Health Data**.
4. Wait for the `export.zip` to generate (can take a few minutes).
5. AirDrop / email it to your Mac and drop it in this project folder.

The zip contains `apple_health_export/export.xml`. The tool reads the zip
directly — no need to unzip.

---

## Run it

```bash
python run.py --zip export.zip --year 2026 --name "Your Name"
```

First run parses the whole export (slow — minutes for large exports) and caches
the parsed workouts to `output/.workouts_<year>.pkl`. Later runs reuse the
cache instantly.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--zip` | `apple_health_export.zip` | Path to your Health export zip |
| `--year` | `2026` | Year to analyze |
| `--name` | `Your Name` | Name shown on the card |
| `--age` | none | Used for HR-zone max-HR (`220 − age`); default max 185 |
| `--stats-only` | off | Print/save text stats only, skip images |
| `--ai-summary` | off | Add a 2-sentence coach summary (needs local Ollama, see below) |
| `--no-cache` | off | Force re-parse instead of using the cached workouts |

Re-parse from scratch (e.g. after a new export):

```bash
python run.py --zip export.zip --year 2026 --name "Your Name" --no-cache
```

---

## Training-block report (optional)

Compare your full year against a training block (e.g. marathon prep from a
start date), including **total steps** pulled from the export:

```bash
python marathon_prep.py --zip export.zip --year 2026 --start 2026-03-05
```

Writes `output/marathon_prep.txt`.

---

## Optional: AI summary

`--ai-summary` generates a 2-sentence coach narrative using a **fully
open-source, locally-run** model: **Meta Llama 3.2 3B Instruct** (open weights),
**downloaded from the [Hugging Face Hub](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF)**.
No API key, no cloud — the weights come from Hugging Face and inference runs
on-device. If it can't run, the summary is skipped silently (the rest of the
card still generates).

**How it works:** on first use, `ai_summary.py` calls
`huggingface_hub.hf_hub_download` to fetch the GGUF weights
(`bartowski/Llama-3.2-3B-Instruct-GGUF`, Q4_K_M, ~2 GB) from Hugging Face, then
registers them once with the local [Ollama](https://ollama.com) engine
(`ollama create llama32-hf`) and runs inference locally.

```bash
# one-time: install the Ollama engine (https://ollama.com/download)
python run.py --zip export.zip --year 2026 --ai-summary
# first run downloads ~2 GB from Hugging Face, then caches it
```

`huggingface_hub` is in `requirements.txt`. Want a different model? Change
`HF_REPO` / `HF_FILE` at the top of `ai_summary.py` to any GGUF repo on
Hugging Face.

> The official `meta-llama/Llama-3.2-3B` repo on Hugging Face is **gated**
> (needs an account + access token). This project uses the ungated
> `bartowski` GGUF mirror, so no token is required.

---

## How dedup works

The same physical run is often recorded by several apps with near-identical
start times. `parse_health.py` clusters runs whose start times fall within
**15 minutes** and keeps one per cluster, by source priority:

```
Apple Watch  >  Strava  >  Runna
```

The representative source decides distance/duration/pace; heart-rate and
calories fall back to the first source in the cluster that has them (so an
Apple Watch HR is preserved even if a phone-app row is chosen). Adjust the
window or priority in `parse_health.py` (`DEDUP_WINDOW_MIN`, `_source_rank`).

---

## Project layout

```
run.py            # entry point: parse → stats → charts → card
parse_health.py   # stream export.xml → clean, de-duplicated workouts DataFrame
compute_stats.py  # aggregate workouts into a stats dict
visualize.py      # matplotlib charts (PNG)
generate_card.py  # Pillow shareable card
ai_summary.py     # optional summary: Llama 3.2 3B from Hugging Face, run locally
marathon_prep.py  # training-block vs YTD report + step totals
```

---

## Privacy

- All processing is local. The only optional network call is to a local Ollama
  instance you run yourself.
- `.gitignore` excludes every health artifact: `export.zip`, `apple_health_export/`,
  `export.xml`, and the entire `output/` folder.
- **Never commit your `export.zip`** — it contains your full health history.
