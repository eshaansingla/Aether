import asyncio
from app.services.agent import agent
from app.eval import metrics

# Used by both the dedicated Playground endpoint (/api/compare) and the main chat/
# document flow (runner.py) — one place generates all 6 sampling-strategy variants and
# scores each with perplexity, so the two surfaces can never drift apart on what a
# "variant" actually contains.
_PERPLEXITY_EXPLAIN = (
    "Perplexity: how predictable this text is under a small fixed reference model "
    "(distilgpt2) — computed as exp(average negative log-likelihood per token). Lower "
    "means more predictable/fluent text under that model; it is not a measure of "
    "factual correctness. Not computed against the live provider's own probabilities, "
    "since hosted chat-completion APIs (confirmed on Groq) don't expose those."
)


_GROUNDING_CHECK_EXPLAIN = (
    "Grounding check: a separate pass asks whether every specific fact in this variant "
    "is actually present in the source material used to answer. Shown per variant "
    "(rather than silently filtering) because seeing a higher-temperature strategy "
    "drift from the facts is itself part of what this comparison demonstrates."
)

# BLEU/ROUGE need a reference text — live chat has no "correct answer" to score against
# in general, but when grounding context exists (a factual lookup or an attached
# document), that source text is the closest thing available. This is deliberately
# NOT presented as a correctness score: high word-overlap with the source means the
# reply stuck close to the source's own wording, not that it's factually right (the
# grounding_check above is what actually checks truthfulness). Shown only when context
# exists; omitted (null) otherwise rather than scored against nothing.
_SIMILARITY_EXPLAIN = (
    "Source similarity (BLEU / ROUGE-L): word-overlap between this variant and the "
    "source material used to ground it — not a correctness score (that's the grounding "
    "check above). High overlap means the reply stuck close to the source's wording; "
    "low overlap can mean either paraphrasing or drift, which is why this never replaces "
    "the grounding check. Only computed when grounding context exists — there's no "
    "single 'correct' reference for free-form chat otherwise."
)


async def _attach_metrics(variants, message=None, context=None):
    results = []
    for v in variants:
        try:
            ppl = await asyncio.to_thread(metrics.perplexity, v["text"])
        except Exception:
            ppl = None
        grounding_check = None
        similarity = None
        if context and message:
            try:
                grounding_check = await asyncio.to_thread(agent._verify_grounded, context, message, v["text"])
            except Exception:
                grounding_check = None
            try:
                bleu_score = await asyncio.to_thread(metrics.bleu, v["text"], [context])
                rouge_scores = await asyncio.to_thread(metrics.rouge, v["text"], context)
                similarity = {"bleu": bleu_score, "rougeL": rouge_scores["rougeL"]}
            except Exception:
                similarity = None
        results.append({**v, "metrics": {
            "perplexity": ppl, "perplexity_explanation": _PERPLEXITY_EXPLAIN,
            "grounding_check": grounding_check, "grounding_check_explanation": _GROUNDING_CHECK_EXPLAIN,
            "similarity": similarity, "similarity_explanation": _SIMILARITY_EXPLAIN,
        }})
    return results


async def generate_all_variants(message, history=None, context=None):
    variants = await asyncio.gather(*[
        asyncio.to_thread(agent.generate_variant_any, message, preset, history, context)
        for preset in agent.SAMPLING_PRESETS
    ])
    return await _attach_metrics(variants, message, context)


async def generate_all_document_variants(instruction, fmt, context=None):
    variants = await asyncio.gather(*[
        asyncio.to_thread(agent.generate_document_variant, instruction, fmt, preset, context)
        for preset in agent.SAMPLING_PRESETS
    ])
    return await _attach_metrics(variants, instruction, context)
