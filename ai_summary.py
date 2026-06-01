"""Optional AI summary.

The model is downloaded **from Hugging Face** (`huggingface_hub`) as a GGUF
file, then run locally through the Ollama engine. No API key, no cloud — the
weights come straight from the Hugging Face Hub and inference is on-device.

Fails silently to an empty string if anything is unavailable.
"""

import subprocess
import tempfile

import requests

from compute_stats import format_pace

# Ungated GGUF mirror of Meta's Llama 3.2 3B Instruct on the Hugging Face Hub.
HF_REPO = "bartowski/Llama-3.2-3B-Instruct-GGUF"
HF_FILE = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
# Local name Ollama registers the Hugging Face weights under.
OLLAMA_MODEL = "llama32-hf"
OLLAMA_URL = "http://localhost:11434/api/generate"


def _ollama_has_model(name: str) -> bool:
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True,
                             text=True, timeout=30)
        return any(line.split()[:1] == [name] or line.startswith(name + ":")
                   for line in out.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_model() -> bool:
    """Download the GGUF from Hugging Face and register it with Ollama once."""
    if _ollama_has_model(OLLAMA_MODEL):
        return True
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("  huggingface_hub not installed; skipping AI summary.")
        return False
    try:
        print(f"  Downloading {HF_FILE} from Hugging Face ({HF_REPO})...")
        gguf_path = hf_hub_download(repo_id=HF_REPO, filename=HF_FILE)
        with tempfile.NamedTemporaryFile("w", suffix=".Modelfile",
                                         delete=False) as mf:
            mf.write(f"FROM {gguf_path}\n")
            modelfile = mf.name
        print(f"  Registering with Ollama as '{OLLAMA_MODEL}'...")
        subprocess.run(["ollama", "create", OLLAMA_MODEL, "-f", modelfile],
                       check=True, timeout=300)
        return True
    except Exception as e:  # noqa: BLE001 - optional feature, never fatal
        print(f"  Could not prepare HF model ({type(e).__name__}); skipping.")
        return False


def generate_analysis(stats: dict) -> str:
    """Full coaching analysis (markdown) generated locally from real stats."""
    if not ensure_model():
        return ""

    hr = stats.get("avg_hr")
    hr_line = f"- Average heart rate: {hr:.0f} bpm\n" if hr == hr else ""
    facts = (
        f"- Total runs: {stats['total_runs']}\n"
        f"- Total miles: {stats['total_miles']:.1f}\n"
        f"- Total time: {stats['total_time_hours']:.1f} hours\n"
        f"- Average pace: {format_pace(stats['avg_pace'])}\n"
        f"- Best pace: {format_pace(stats['best_pace'])}\n"
        f"- Longest run: {stats['longest_run_miles']:.1f} miles\n"
        f"{hr_line}"
        f"- Best month: {stats['best_month']} ({stats['best_month_miles']:.0f} mi)\n"
        f"- Pace change, first to last month: {stats['pace_improvement']:.0f} s/mi"
    )
    system = ("You are an experienced, encouraging running coach. Analyze the "
              "runner's year using ONLY the stats provided. Reference the actual "
              "numbers. Be specific and honest, not generic.")
    prompt = (
        "Here are a runner's stats for the year:\n\n"
        f"{facts}\n\n"
        "Write a concise markdown analysis with exactly these sections:\n"
        "## Overview\n(2 sentences)\n"
        "## What's going well\n(2-3 bullet points)\n"
        "## What to work on\n(2-3 bullet points)\n"
        "## Suggested next goal\n(1 sentence)\n\n"
        "Reference the real numbers above. No preamble, start at the heading."
    )
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "system": system,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 600},
            },
            timeout=180,
        )
        response.raise_for_status()
        text = response.json()["response"].strip()
        # Start at the first markdown heading if the model added preamble.
        idx = text.find("## ")
        return text[idx:].strip() if idx != -1 else text
    except (requests.exceptions.RequestException, KeyError, ValueError) as e:
        print(f"  AI analysis unavailable ({type(e).__name__}); skipping.")
        return ""


def generate_summary(stats: dict) -> str:
    if not ensure_model():
        return ""

    # Small (3B) models obey best with a strict role, a one-shot format
    # example, and hard generation limits (short output, stop at newline).
    system = ("You output exactly ONE original running motivation quote and "
              "nothing else. No preamble, no explanation, no author, no "
              "quotation marks. One line only.")
    prompt = ("Example: Miles make the runner.\n"
              "Now write a different short, punchy running quote (5-10 words):")

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "system": system,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.9, "num_predict": 32,
                            "stop": ["\n"]},
            },
            timeout=120,
        )
        response.raise_for_status()
        quote = _clean_quote(response.json()["response"])
        return quote if _looks_like_quote(quote) else _fallback_quote()
    except (requests.exceptions.RequestException, KeyError, ValueError) as e:
        print(f"  AI summary unavailable ({type(e).__name__}); using a quote.")
        return _fallback_quote()


# Words that mark text as the model's meta-chatter, not the quote itself.
_META = ("punctuation", "quotation", "quote", "preamble", "note", "author",
         "sentence", "here is", "here are", "here's", "example", "you can",
         "subject", "tone", "sure", "output", "feel free", "let me know",
    "looking for", "hope this", "is this what", "i hope")

# Clean curated fallbacks so the card always shows something good.
_QUOTES = [
    "One run can change your day. Many runs can change your life.",
    "The miracle isn't that I finished — it's that I had the courage to start.",
    "Run when you can, walk if you have to, crawl if you must; just never give up.",
    "Your only limit is the one you set yourself.",
    "Every mile begins with a single step. Keep stepping.",
    "Pain is temporary. Pride is forever.",
    "Don't count the miles, make the miles count.",
    "The road doesn't end where your doubt begins.",
]


def _fallback_quote() -> str:
    import random
    return random.choice(_QUOTES)


def _looks_like_quote(q: str) -> bool:
    """Reject empty, too-long, or meta-laden model output."""
    if not q:
        return False
    words = q.split()
    if not (3 <= len(words) <= 16):
        return False
    return not any(w in q.lower() for w in _META)


def _clean_quote(text: str) -> str:
    """Strip a small chatty model's preamble down to just the quote."""
    text = text.replace('"', "").replace("“", "").replace("”", "")
    lines = [ln.strip(" -*•\t") for ln in text.splitlines() if ln.strip()]
    good = [ln for ln in lines if not any(w in ln.lower() for w in _META)]
    return (good[0] if good else (lines[-1] if lines else "")).strip()
