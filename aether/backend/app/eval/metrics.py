import math, threading

# BLEU/ROUGE use well-established, independently-validated implementations (sacrebleu is
# the de-facto research-standard BLEU, rouge-score is Google's own ROUGE implementation)
# rather than a hand-rolled n-gram counter — both metrics have enough edge cases (BLEU's
# brevity penalty, ROUGE's stemming) that reusing a validated implementation is more
# trustworthy than reimplementing the formula from scratch for a course project.
import sacrebleu
from rouge_score import rouge_scorer

_rouge = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)


def bleu(candidate: str, references: list[str]) -> float:
    """Sentence-level BLEU (0-100) of `candidate` against one or more `references`."""
    candidate = (candidate or "").strip()
    references = [r for r in (references or []) if r and r.strip()]
    if not candidate or not references:
        return 0.0
    return sacrebleu.sentence_bleu(candidate, references).score


def rouge(candidate: str, reference: str) -> dict:
    """ROUGE-1/2/L F-measures (0-1) of `candidate` against a single `reference`."""
    candidate, reference = (candidate or "").strip(), (reference or "").strip()
    if not candidate or not reference:
        return {"rouge1": 0.0, "rouge2": 0.0, "rougeL": 0.0}
    scores = _rouge.score(reference, candidate)
    return {name: result.fmeasure for name, result in scores.items()}


# Perplexity needs per-token log-probabilities from the model that generated the text —
# AETHER's live providers (confirmed against Groq specifically: `logprobs` → 400 "not
# supported with this model") don't expose those through their hosted chat-completions
# API, which is a real, provider-level limitation, not something fixable by changing this
# code. The standard workaround used throughout NLG evaluation literature is to score the
# already-generated text with a small, fixed, independent reference LM instead — this
# makes the metric a provider-agnostic fluency/predictability proxy (how surprising is
# this text to a generic language model?) rather than a property of the specific model
# that wrote it, which is a different but still meaningful and widely-used reading of
# "perplexity of generated text."
_PERPLEXITY_MODEL = "distilgpt2"
_tokenizer = None
_model = None
_load_lock = threading.Lock()


def _load_scorer():
    # generate_topk/generate_beam/perplexity all run concurrently via asyncio.to_thread
    # (variants.py gathers every sampling preset at once) — the first call each needs to
    # both import `transformers` and download/load distilgpt2. Without this lock, two
    # threads hitting that first-time path simultaneously raced hard enough that one of
    # them got a partial module and failed with "cannot import name 'GPT2LMHeadModel'
    # from 'transformers'", even though the import machinery is normally thread-safe —
    # observed directly in this app's own concurrent top_k+beam calls.
    global _tokenizer, _model
    with _load_lock:
        if _model is None:
            from transformers import GPT2LMHeadModel, GPT2TokenizerFast
            _tokenizer = GPT2TokenizerFast.from_pretrained(_PERPLEXITY_MODEL)
            _model = GPT2LMHeadModel.from_pretrained(_PERPLEXITY_MODEL)
            _model.eval()
    return _tokenizer, _model


def perplexity(text: str):
    """Perplexity of `text` under a fixed distilgpt2 reference scorer, or None if the
    text is too short to score (fewer than 2 tokens — there's no next-token prediction
    to evaluate)."""
    import torch
    text = (text or "").strip()
    if not text:
        return None
    tokenizer, model = _load_scorer()
    encoding = tokenizer(text, return_tensors="pt", truncation=True, max_length=1024)
    input_ids = encoding.input_ids
    if input_ids.shape[1] < 2:
        return None
    with torch.no_grad():
        # Passing input_ids as labels makes GPT2LMHeadModel compute the standard
        # shifted-by-one next-token cross-entropy internally, averaged over the sequence
        # — exactly the quantity perplexity = exp(average negative log-likelihood) needs.
        loss = model(input_ids, labels=input_ids).loss.item()
    return math.exp(loss)


# Top-k sampling and beam search both need direct access to the model's raw per-token
# logits at every decoding step — no hosted chat-completions API exposes that (confirmed
# against Groq: `top_k` → 400 "unsupported property"; `n>1`, which beam search would
# need to track multiple hypotheses, → 400 "must be at most 1"). The only way to run
# these two strategies for real, rather than faking them, is to run the decode loop
# locally — reusing the same distilgpt2 already loaded for perplexity scoring, so this
# doesn't pull in a second model. distilgpt2 is a small, non-instruction-tuned base
# model (continues text, doesn't follow instructions the way the cloud models do), so
# its output quality is expected to be much rougher than the cloud presets — that's
# disclosed in the UI rather than hidden, since the point is demonstrating the actual
# algorithm, not competing on output quality.
def generate_topk(prompt: str, k: int = 50, max_new_tokens: int = 60) -> str:
    import torch
    tokenizer, model = _load_scorer()
    input_ids = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).input_ids
    with torch.no_grad():
        output = model.generate(
            input_ids, do_sample=True, top_k=k, temperature=1.0,
            max_new_tokens=max_new_tokens, pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(output[0][input_ids.shape[1]:], skip_special_tokens=True).strip()


def generate_beam(prompt: str, num_beams: int = 4, max_new_tokens: int = 60) -> str:
    import torch
    tokenizer, model = _load_scorer()
    input_ids = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).input_ids
    with torch.no_grad():
        output = model.generate(
            input_ids, num_beams=num_beams, do_sample=False, early_stopping=True,
            max_new_tokens=max_new_tokens, pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(output[0][input_ids.shape[1]:], skip_special_tokens=True).strip()
