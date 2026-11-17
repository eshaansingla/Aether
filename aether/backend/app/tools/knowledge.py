import re
import httpx

# A factual-lookup shape: "what is X", "who is X", "tell me about X", etc. Short and
# cheap to check, so it costs nothing for the common case (greetings, opinions, casual
# chat) where no lookup should happen at all.
_FACTUAL_PATTERNS = re.compile(
    r"^\s*(who|what|when|where|which)\s+(is|are|was|were)\b|"
    r"\btell me about\b|\bwho is\b|\bwhat is\b|\binformation about\b|\btell me more about\b",
    re.IGNORECASE,
)

def looks_factual(text: str) -> bool:
    return bool(_FACTUAL_PATTERNS.search(text))

# "Who is the founder of X" leaves "the founder of X" as the naive subject, which
# DuckDuckGo's instant-answer lookup can't match (it needs the entity's own name, not a
# descriptive phrase about it) - so the lookup silently returns nothing and the model is
# left to invent a specific name with no grounding at all. Pulling the actual entity out
# from behind "<role/attribute> of" still gets a real abstract to check the model's claim
# against, even though that abstract may not itself state who the role belongs to - the
# chat system prompt already tells the model to say so plainly rather than guess when
# the given material doesn't cover the question.
_RELATIONAL_PATTERN = re.compile(
    r"^(?:the\s+)?(?:founder|co-?founder|ceo|ceo's name|author|writer|president|prime\s+minister|"
    r"chief\s+minister|director|inventor|discoverer|owner|creator|head|chairman|"
    r"chancellor|vice-?chancellor|principal|capital|population|currency|CEO)s?\s+of\s+(.+)$",
    re.IGNORECASE,
)

def _extract_subject(text: str) -> str:
    low = text.strip()
    for pattern in (
        r"(?i)^(?:who|what|when|where|which)\s+(?:is|are|was|were)\s+(.+?)\??$",
        r"(?i)tell me (?:more )?about\s+(.+?)\??$",
        r"(?i)information about\s+(.+?)\??$",
    ):
        m = re.search(pattern, low)
        if m:
            subject = m.group(1).strip(" ?.!")
            relational = _RELATIONAL_PATTERN.match(subject)
            return relational.group(1).strip(" ?.!") if relational else subject
    return low.strip(" ?.!")

# A document-writing request names its topic after "about"/"on" ("write an essay about
# the French Revolution", "a report on renewable energy") rather than asking a question,
# so it needs its own extraction shape. Deliberately limited to non-fiction forms
# (essay/report/article/...), not story/poem/song/script: grounding those in a
# Wikipedia-style abstract would push the model to write a dry factual summary instead
# of the creative piece actually asked for. A request with no such topic (a personal
# letter, a to-do list, "my dog") has nothing to look up - returning None is correct
# there, not a failure, since fabricating a lookup subject out of thin air would ground
# the answer in the wrong thing.
_DOC_TOPIC_PATTERN = re.compile(
    r"\b(?:essay|report|article|research\s+paper|paper|summary|blog\s*post|speech|"
    r"note|paragraph)s?\b.*?\b(?:on|about)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_CREATIVE_PATTERN = re.compile(
    r"\b(?:story|stories|poem|poetry|song|lyrics|script|dialogue|fiction|fictional|"
    r"novel|fairy\s*tale|tale)\b",
    re.IGNORECASE,
)

def extract_document_topic(instruction: str) -> str | None:
    if _CREATIVE_PATTERN.search(instruction):
        return None
    m = _DOC_TOPIC_PATTERN.search(instruction.strip())
    if not m:
        return None
    topic = m.group(1).strip(" ?.!\"'")
    # Strip a trailing clause the model doesn't need grounded, e.g. "...about dogs in
    # 300 words" or "...about climate change, save it as climate.docx".
    topic = re.split(r"\s+(?:in \d+ words|save (?:it|this)|and save|format(?:ted)? as)\b", topic, flags=re.IGNORECASE)[0].strip()
    return topic or None

def lookup_subject(subject: str) -> str | None:
    # A small local model has no real knowledge base - it generates plausible-sounding
    # specifics (dates, locations, accrediting bodies) whether or not they're true. A
    # quick, keyless lookup gives something real to ground the answer in instead,
    # without the latency cost of switching to a bigger local model.
    #
    # Wikipedia's own API currently hard-blocks non-browser traffic outright (its
    # robot policy rejects requests regardless of a compliant User-Agent - see
    # https://phabricator.wikimedia.org/T400119), so this goes through DuckDuckGo's
    # Instant Answer API instead, which sources the same Wikipedia abstracts without
    # that block, and is a documented public API meant for exactly this kind of use.
    # A subject this short (a single letter, "it", a stray initial) is never going to be
    # the real name of the thing being asked about - DuckDuckGo will still happily
    # resolve it to an unrelated dictionary/encyclopedia entry (e.g. "x" -> the letter X),
    # and that mismatched entry is worse than no grounding at all, since it reads like a
    # real, on-topic answer right up until it obviously isn't.
    if not subject or len(subject) < 3:
        return None
    try:
        r = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": subject, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers={"User-Agent": "AETHER-local-desktop-assistant/1.0"},
            timeout=4,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        text = (data.get("AbstractText") or "").strip()
        source = data.get("AbstractSource") or "web"
        # A short abstract (or none at all, on a more obscure topic) leaves the model
        # with too little to ground a whole essay/report in - DuckDuckGo's RelatedTopics
        # carry extra one-line facts about the same subject that fill that gap cheaply,
        # without a second network round trip.
        related = [
            t.get("Text", "").strip()
            for t in (data.get("RelatedTopics") or [])
            if isinstance(t, dict) and t.get("Text")
        ][:5]
        if not text and not related:
            return None
        parts = [f'{source} - "{subject}": {text}'] if text else [f'"{subject}":']
        parts.extend(f"- {line}" for line in related)
        return "\n".join(parts)
    except Exception:
        return None

def wikipedia_summary(query: str) -> str | None:
    return lookup_subject(_extract_subject(query))

# An essay/report topic is often phrased as "the causes of X"/"the history of X" rather
# than X's own name - DuckDuckGo's instant-answer lookup needs the name itself ("World
# War 1" matches; "the causes of World War 1" does not, even though the topic is
# obviously the same war). Falling back to the stripped entity on a miss catches this
# without losing the more specific phrasing as the first attempt.
_TOPIC_RELATIONAL_PATTERN = re.compile(
    r"^(?:the\s+)?(?:causes?|effects?|impacts?|history|background|overview|importance|"
    r"benefits?|advantages?|disadvantages?|role|significance|consequences?|results?|"
    r"origins?)\s+of\s+(.+)$",
    re.IGNORECASE,
)

def lookup_topic(topic: str) -> str | None:
    result = lookup_subject(topic)
    if result:
        return result
    m = _TOPIC_RELATIONAL_PATTERN.match(topic.strip())
    return lookup_subject(m.group(1).strip()) if m else None
