"""Optional local Ollama AI summary. Fails silently to empty string."""

import requests

from compute_stats import format_pace


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

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["response"].strip()
    except (requests.exceptions.RequestException, KeyError, ValueError) as e:
        print(f"  AI summary unavailable ({type(e).__name__}); skipping.")
        return ""
