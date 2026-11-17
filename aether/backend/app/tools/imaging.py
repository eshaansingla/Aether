import re
from pathlib import Path
from urllib.parse import quote

import httpx

from app.tools.files import safe_output_path

# Every provider actually configured for this project (OpenAI, Groq, Gemini) is either
# out of credits, has a $0/zero free-tier quota on every image-capable model, or (Groq)
# has no image-generation model at all — confirmed directly against each. Pollinations
# (https://pollinations.ai) is a separate, genuinely free, keyless image-generation API:
# a GET request to an image.pollinations.ai URL returns real generated image bytes, no
# account or key required. Used here only for image generation; text generation still
# goes through the configured AETHER_PROVIDER.
_BASE_URL = "https://image.pollinations.ai/prompt"


def generate_image(prompt: str, width: int = 768, height: int = 768) -> Path:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Please describe the image you want.")
    url = f"{_BASE_URL}/{quote(prompt)}"
    r = httpx.get(
        url,
        params={"width": width, "height": height, "nologo": "true"},
        timeout=60,
        follow_redirects=True,
    )
    if r.status_code == 402:
        # Pollinations' free tier is keyless but capped at 1 image per ~45s per IP —
        # a real, expected limit on a free service, not an error worth a raw traceback.
        raise RuntimeError("The free image service allows one image about every 45 seconds — please wait a moment and try again.")
    r.raise_for_status()
    content_type = r.headers.get("content-type", "")
    if "image" not in content_type:
        # The API returns an error page (still HTTP 200) rather than an image when the
        # prompt is rejected by its own content filter — this is the only reliable way
        # to tell the two apart, since both come back as a normal 200 response.
        raise RuntimeError("The image service didn't return an image for this prompt (it may have been filtered).")

    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", prompt.strip().lower()).strip("_")[:50] or "aether_image"
    ext = "png" if "png" in content_type else "jpg"
    path = safe_output_path(f"{clean}.{ext}", ext)
    path.write_bytes(r.content)
    return path
