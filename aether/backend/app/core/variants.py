import asyncio, math
from app.services.agent import agent
from app.eval import metrics


def _finite_or_none(value):
    # A NaN/inf score (seen once from perplexity on degenerate local-model text, see
    # metrics.perplexity) makes the whole task JSON-unserializable the moment it's
    # attached - crashing every subsequent poll of this task, not just the one
    # request, since the bad value stays in task["variants"] forever after. Scrubbing
    # every float that reaches a variant/candidate here means one bad score can never
    # again take down the rest of the comparison.
    if value is None:
        return None
    try:
        return value if math.isfinite(value) else None
    except TypeError:
        return value

# Used by the dedicated Playground endpoint (/api/compare) and the main chat/document
# flow (runner.py) - one place generates all 6 sampling-strategy variants and scores
# each, so the two surfaces can never drift apart on what a "variant" actually
# contains. Each of the 6 is built as a single self-contained unit (generation +
# candidates + metrics all in one coroutine) and surfaced via `stream_variants()` the
# moment it finishes, instead of waiting for the slowest of the 6 before showing
# anything - a user who only cares about greedy's answer shouldn't have to wait for
# beam search's local decode loop just because it happens to be last.
_PERPLEXITY_EXPLAIN = (
    "Perplexity: how predictable this text is under a small fixed reference model "
    "(distilgpt2) - computed as exp(average negative log-likelihood per token). Lower "
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
_SIMILARITY_EXPLAIN = (
    "Source similarity (BLEU / ROUGE-L): word-overlap between this variant and the "
    "source material used to ground it - not a correctness score (that's the grounding "
    "check above). High overlap means the reply stuck close to the source's wording; "
    "low overlap can mean either paraphrasing or drift, which is why this never replaces "
    "the grounding check. Only computed when grounding context exists - there's no "
    "single 'correct' reference for free-form chat otherwise."
)
_LOCAL_CANDIDATES_EXPLAIN = (
    "The 5 candidates this run actually produced, ranked by the local model's own real "
    "log-probability (not a proxy) - this is the exact model that generated them, so "
    "the ranking is the genuine probability ordering, not an estimate."
)
_NUCLEUS_CANDIDATES_EXPLAIN = (
    "5 independent samples at this preset's temperature/top_p, ranked by perplexity "
    "under the same local reference model used elsewhere on this page - a proxy, not "
    "the cloud provider's own probability, since hosted chat-completion APIs (confirmed "
    "on Groq) don't expose token log-probabilities at all. The top-ranked sample below "
    "is shown as this card's main text."
)
_NUCLEUS_PRESET = next(p for p in agent.SAMPLING_PRESETS if p["key"] == "nucleus")


async def _score_one(variant, message, context):
    try:
        ppl = _finite_or_none(await asyncio.to_thread(metrics.perplexity, variant["text"]))
    except Exception:
        ppl = None
    grounding_check = None
    similarity = None
    if context and message:
        try:
            grounding_check = await asyncio.to_thread(agent._verify_grounded, context, message, variant["text"])
        except Exception:
            grounding_check = None
        try:
            bleu_score = await asyncio.to_thread(metrics.bleu, variant["text"], [context])
            rouge_scores = await asyncio.to_thread(metrics.rouge, variant["text"], context)
            similarity = {"bleu": _finite_or_none(bleu_score), "rougeL": _finite_or_none(rouge_scores["rougeL"])}
        except Exception:
            similarity = None
    if variant.get("candidates"):
        for c in variant["candidates"]:
            c["score"] = _finite_or_none(c.get("score"))
    variant["metrics"] = {
        "perplexity": ppl, "perplexity_explanation": _PERPLEXITY_EXPLAIN,
        "grounding_check": grounding_check, "grounding_check_explanation": _GROUNDING_CHECK_EXPLAIN,
        "similarity": similarity, "similarity_explanation": _SIMILARITY_EXPLAIN,
    }
    return variant


async def _rank_cloud_samples(samples):
    ranked = []
    for s in samples:
        try:
            ppl = _finite_or_none(await asyncio.to_thread(metrics.perplexity, s["text"]))
        except Exception:
            ppl = None
        ranked.append({"text": s["text"], "score": ppl})
    # Lower perplexity = more predictable under the reference model = ranked first,
    # same "first is most favored" convention as the local beam/top-k candidates,
    # even though the underlying metric (perplexity vs. log-probability) differs.
    ranked.sort(key=lambda c: (c["score"] is None, c["score"]))
    return ranked


def _build_units(message, history, context, *, is_document, fmt, instruction):
    """One coroutine per sampling preset. Each returns a COMPLETE, display-ready
    variant (generation + candidates where applicable + metrics), so the first one to
    finish is already everything the UI needs - nothing is a two-pass fetch anymore."""
    subject = instruction if is_document else message

    async def cloud_unit(preset):
        if is_document:
            v = await asyncio.to_thread(agent.generate_document_variant, instruction, fmt, preset, context)
        else:
            v = await asyncio.to_thread(agent.generate_variant, message, preset, history, context)
        return await _score_one(v, subject, context)

    async def local_unit(preset):
        if is_document:
            candidates = await asyncio.to_thread(agent.generate_document_local_candidates, instruction, fmt, preset, context, 5)
        else:
            candidates = await asyncio.to_thread(agent.generate_local_candidates, message, preset, context, 5)
        if not candidates:
            candidates = [{"text": "(not applicable for code output)", "score": None}]
        v = {**preset, "text": candidates[0]["text"], "candidates": candidates,
             "candidates_explanation": _LOCAL_CANDIDATES_EXPLAIN}
        return await _score_one(v, subject, context)

    async def nucleus_unit(preset):
        if is_document:
            samples = await asyncio.gather(*[
                asyncio.to_thread(agent.generate_document_variant, instruction, fmt, preset, context) for _ in range(5)
            ])
        else:
            samples = await asyncio.gather(*[
                asyncio.to_thread(agent.generate_variant, message, preset, history, context) for _ in range(5)
            ])
        ranked = await _rank_cloud_samples(samples)
        v = {**preset, "text": ranked[0]["text"], "candidates": ranked,
             "candidates_explanation": _NUCLEUS_CANDIDATES_EXPLAIN}
        return await _score_one(v, subject, context)

    units = []
    for preset in agent.SAMPLING_PRESETS:
        if preset["key"] == "nucleus":
            units.append(asyncio.create_task(nucleus_unit(preset)))
        elif preset["kind"] == "local":
            units.append(asyncio.create_task(local_unit(preset)))
        else:
            units.append(asyncio.create_task(cloud_unit(preset)))
    return units


async def stream_variants(message=None, history=None, context=None, *, is_document=False,
                           fmt=None, instruction=None, on_variant=None):
    """Runs all 6 presets concurrently and calls `on_variant(variant)` as each finishes,
    in whatever order they actually complete, fastest first. Returns the full list at
    the end for callers that don't need progressive updates (e.g. the evaluation
    harness calling this directly)."""
    units = _build_units(message, history, context, is_document=is_document, fmt=fmt, instruction=instruction)
    results = []
    for coro in asyncio.as_completed(units):
        variant = await coro
        results.append(variant)
        if on_variant:
            maybe_awaitable = on_variant(variant)
            if asyncio.iscoroutine(maybe_awaitable):
                await maybe_awaitable
    return results


async def generate_all_variants(message, history=None, context=None):
    return await stream_variants(message, history, context, is_document=False)


async def generate_all_document_variants(instruction, fmt, context=None):
    return await stream_variants(None, None, context, is_document=True, fmt=fmt, instruction=instruction)
