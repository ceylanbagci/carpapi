from __future__ import annotations

"""PII guard for prompts entering the TokenCache.

Hard rule from context/compliance-rules.md and context/ai-cache-rules.md:
raw dealer data (VINs, customer phone/email, internal IDs) must NEVER be
sent to Claude. Anonymized metadata only.

This guard runs at TokenCache.query() entry and raises before the prompt
hashes or hits the wire. It is conservative — false positives are
preferable to leaking PII.
"""

import re

# 17-char VIN. Same pattern as carapi_pipeline.dedupe.normalize_vin.
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")

# Reuse the patterns from carapi_pipeline/pii.py. Duplicated here so the
# guard has zero dependency on the pipeline package — the cache must be
# usable from anywhere in the project.
_PHONE_RE = re.compile(
    r"""
    (?<![\w])
    (?:\+?1[\s.\-]?)?
    \(?\d{3}\)?
    [\s.\-]?
    \d{3}
    [\s.\-]?
    \d{4}
    (?![\w])
    """,
    re.VERBOSE,
)

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Bare 9-digit SSN-shaped strings — extremely unlikely in legitimate prompts;
# block defensively.
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Common US street-address pattern: digits + word(s) + street suffix.
# Suffix list kept conservative to avoid false positives on phrases like
# "drive past the lot" — "Drive" only matches when preceded by a numeric
# block and a word.
_ADDRESS_RE = re.compile(
    r"\b\d+\s+[A-Za-z][\w\s]{0,40}?\s+"
    r"(?:Street|St\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Road|Rd\.?|Drive|Dr\.?|"
    r"Lane|Ln\.?|Court|Ct\.?|Place|Pl\.?|Highway|Hwy\.?|Parkway|Pkwy\.?|"
    r"Way|Terrace|Ter\.?)\b",
    re.IGNORECASE,
)


class PIIInPromptError(ValueError):
    """Raised when a prompt contains PII that policy forbids sending to Claude."""

    def __init__(self, kind: str, sample: str) -> None:
        # Truncate the sample so the exception message itself doesn't leak
        # more PII into logs.
        snippet = sample[:8] + ("…" if len(sample) > 8 else "")
        super().__init__(
            f"{kind} detected in prompt (matched {snippet!r}); "
            "redact or anonymize before sending. See context/ai-cache-rules.md."
        )
        self.kind = kind


def assert_safe(prompt: str) -> None:
    """Raise PIIInPromptError if the prompt contains forbidden PII patterns.

    Order matters only for which error surfaces first; any one match is
    sufficient to block.
    """
    if prompt is None or not prompt:
        return
    m = _VIN_RE.search(prompt)
    if m:
        raise PIIInPromptError("VIN", m.group(0))
    m = _SSN_RE.search(prompt)
    if m:
        raise PIIInPromptError("SSN-shaped string", m.group(0))
    m = _PHONE_RE.search(prompt)
    if m:
        raise PIIInPromptError("phone number", m.group(0))
    m = _EMAIL_RE.search(prompt)
    if m:
        raise PIIInPromptError("email address", m.group(0))
    m = _ADDRESS_RE.search(prompt)
    if m:
        raise PIIInPromptError("street address", m.group(0))
