from __future__ import annotations

"""Optional LLMLingua-based prompt compression.

Per context/ai-cache-rules.md (guideline 3): apply token compression
inside TokenCache.query() before hashing and sending. LLMLingua reduces
tokens 2–5× while preserving semantic meaning, runs locally, and is well
suited to dealer descriptions / scraped HTML / address strings.

This module is OPTIONAL. If `llmlingua` is not installed, `make_compressor`
returns None and TokenCache passes prompts through unchanged. The cache
is still functional; you just don't get compression.

Install with:  pip install llmlingua
"""

import logging
import re
from typing import Callable

log = logging.getLogger(__name__)


def strip_html_and_boilerplate(text: str) -> str:
    """Cheap pre-compression cleanup: remove tags and collapse whitespace.

    Always runs (no optional dep). Useful even when LLMLingua isn't
    installed — boilerplate stripping alone often saves 30–50% of tokens
    on scraped HTML.
    """
    if not text:
        return text
    # Drop script/style blocks entirely.
    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # HTML comments.
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    # Strip remaining tags.
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode the most common HTML entities without pulling in html.unescape's
    # full table (we don't need fidelity, we need brevity).
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_compressor(rate: float = 0.5) -> Callable[[str], str] | None:
    """Build a compressor callable, or return None if LLMLingua isn't installed.

    The returned callable takes a prompt string and returns the compressed
    form. HTML/boilerplate stripping always runs first, then LLMLingua
    compression to the target ratio.

    Args:
      rate: target compression ratio. 0.5 = compressed prompt is ~50% of
        the original token count. Lower is more aggressive. Recommended
        0.3–0.7 depending on how factually dense the prompt is.
    """
    try:
        from llmlingua import PromptCompressor  # type: ignore[import-not-found]
    except ImportError:
        log.warning(
            "llmlingua not installed; TokenCache will pass prompts through "
            "unchanged. Install with: pip install llmlingua"
        )
        return None

    compressor = PromptCompressor()

    def compress(prompt: str) -> str:
        cleaned = strip_html_and_boilerplate(prompt)
        # Skip LLMLingua entirely on short prompts — overhead exceeds savings.
        if len(cleaned) < 400:
            return cleaned
        try:
            result = compressor.compress_prompt(cleaned, rate=rate)
            return result.get("compressed_prompt", cleaned)
        except Exception as exc:  # noqa: BLE001
            log.warning("LLMLingua compression failed: %s; using cleaned form", exc)
            return cleaned

    return compress
