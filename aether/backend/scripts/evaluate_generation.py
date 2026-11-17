"""
Evaluation harness for AETHER's text generation (BLEU, ROUGE, perplexity), run per
sampling strategy so the results are a real comparison across the 6 presets the
Playground/chat picker offers - not just a single number for "the model".

Run against the live backend (python -m uvicorn app.main:app ...) via /api/compare,
which runs all 6 strategies for each prompt in one call. /api/tasks is NOT used here:
every generative action now pauses at "awaiting_selection" waiting for a human pick
(the chat/document variant-picker feature), so it would never reach "completed" in an
unattended script.

BLEU and ROUGE only make sense where there's a reference text with one broadly correct
answer (a factual question, a summary of a given source) - they're intentionally left
out of the open-ended cases below (an essay, a poem) where no single "correct" text
exists to compare against; forcing a similarity score onto free-form creative output
would be a meaningless number, not a real evaluation. Perplexity, which measures how
predictable the generated text is under a fixed external reference LM rather than how
close it is to some other text, is computed for every case instead.

Usage: python scripts/evaluate_generation.py
Writes a timestamped run to eval_results/run_<timestamp>.json (so past runs are kept,
not overwritten) and refreshes eval_results/latest_summary.md with the aggregated
per-strategy table, ready to paste into docs/PROJECT_REPORT.md.
"""
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.eval.metrics import bleu, rouge

BASE = "http://127.0.0.1:8000"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "eval_results"

TEST_CASES = [
    {"id": "factual_capital", "prompt": "What is the capital of France?", "reference": "Paris"},
    {"id": "factual_author", "prompt": "Who wrote Romeo and Juliet?", "reference": "William Shakespeare"},
    {"id": "factual_symbol", "prompt": "What is the chemical symbol for gold?", "reference": "Au"},
    {"id": "factual_planet", "prompt": "What is the largest planet in the solar system?", "reference": "Jupiter"},
    {"id": "factual_river", "prompt": "What is the longest river in the world?", "reference": "The Nile"},
    {
        "id": "summarization",
        "prompt": (
            "Summarize this in one sentence: The Eiffel Tower is a wrought-iron lattice "
            "tower on the Champ de Mars in Paris, France. It was designed by Gustave "
            "Eiffel's company and built between 1887 and 1889 as the entrance to the "
            "1889 World's Fair, and remains the most-visited paid monument in the world."
        ),
        "reference": "The Eiffel Tower is a wrought-iron tower in Paris built in 1889 for the World's Fair and is the world's most-visited paid monument.",
    },
    {
        "id": "summarization_2",
        "prompt": (
            "Summarize this in one sentence: Photosynthesis is the process by which "
            "green plants, algae, and some bacteria convert light energy into chemical "
            "energy stored in glucose, using carbon dioxide and water, and releasing "
            "oxygen as a byproduct."
        ),
        "reference": "Photosynthesis converts light energy into glucose using carbon dioxide and water, releasing oxygen as a byproduct.",
    },
    {"id": "open_ended_essay", "prompt": "Write a short paragraph about the importance of renewable energy.", "reference": None},
    {"id": "open_ended_creative", "prompt": "Write a short poem about the ocean.", "reference": None},
]


def compare(prompt: str) -> list[dict]:
    r = httpx.post(f"{BASE}/api/compare", json={"message": prompt, "history": [], "attachments": []}, timeout=180)
    r.raise_for_status()
    return r.json()["variants"]


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    per_strategy = {}  # key -> list of {bleu, rougeL, perplexity}
    full_results = []

    for case in TEST_CASES:
        print(f"=== {case['id']} ===", flush=True)
        variants = compare(case["prompt"])
        case_result = {"id": case["id"], "prompt": case["prompt"], "variants": []}
        for v in variants:
            entry = {"key": v["key"], "label": v["label"], "text": v["text"], "perplexity": v["metrics"]["perplexity"]}
            if case["reference"]:
                entry["bleu"] = bleu(v["text"], [case["reference"]])
                entry["rougeL"] = rouge(v["text"], case["reference"])["rougeL"]
            case_result["variants"].append(entry)
            per_strategy.setdefault(v["key"], {"label": v["label"], "bleu": [], "rougeL": [], "perplexity": []})
            if entry["perplexity"] is not None:
                per_strategy[v["key"]]["perplexity"].append(entry["perplexity"])
            if "bleu" in entry:
                per_strategy[v["key"]]["bleu"].append(entry["bleu"])
                per_strategy[v["key"]]["rougeL"].append(entry["rougeL"])
            print(f"  {v['key']:10s} ppl={entry['perplexity']!s:>8} "
                  f"bleu={entry.get('bleu', '-')!s:>6} rougeL={entry.get('rougeL', '-')!s:>6}", flush=True)
        full_results.append(case_result)
        print(flush=True)

    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / f"run_{run_id}.json", "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2)

    # Aggregate: mean per strategy across every test case that produced that metric.
    rows = []
    for key, data in per_strategy.items():
        rows.append({
            "key": key, "label": data["label"],
            "mean_perplexity": round(statistics.mean(data["perplexity"]), 2) if data["perplexity"] else None,
            "mean_bleu": round(statistics.mean(data["bleu"]), 2) if data["bleu"] else None,
            "mean_rougeL": round(statistics.mean(data["rougeL"]), 3) if data["rougeL"] else None,
            "n_perplexity": len(data["perplexity"]), "n_reference": len(data["bleu"]),
        })

    lines = [
        f"# Evaluation run {run_id}",
        "",
        f"{len(TEST_CASES)} prompts ({sum(1 for c in TEST_CASES if c['reference'])} with a reference answer "
        f"for BLEU/ROUGE, {len(TEST_CASES)} scored for perplexity) × 6 sampling strategies.",
        "",
        "| Strategy | Mean perplexity (n) | Mean BLEU (n) | Mean ROUGE-L (n) |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['mean_perplexity']} ({r['n_perplexity']}) | "
            f"{r['mean_bleu']} ({r['n_reference']}) | {r['mean_rougeL']} ({r['n_reference']}) |"
        )
    lines += [
        "",
        "Perplexity is scored by a fixed local reference model (distilgpt2), independent of "
        "which provider generated the text - see `app/eval/metrics.py`. BLEU/ROUGE-L are "
        "scored only against prompts that have one reasonably correct reference answer; "
        "open-ended prompts (essay, poem) are excluded from those two columns by design, "
        "not because they failed.",
    ]
    summary_path = RESULTS_DIR / "latest_summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved {RESULTS_DIR / f'run_{run_id}.json'} and {summary_path}")


if __name__ == "__main__":
    main()
