from __future__ import annotations

"""PII redaction for free-text listing fields.

Policy: see context/compliance-rules.md ("PII handling"). This module is
pure stdlib so the eval suite can exercise it without the rest of the
pipeline's dependencies.
"""

import re

# US phone: 10 digits, optionally formatted, optionally with +1 / leading 1.
# Matches: 555-123-4567, (555) 123-4567, 555.123.4567, 5551234567,
#          +1 555 123 4567, 1-555-123-4567
_PHONE_RE = re.compile(
    r"""
    (?<![\w])               # not preceded by a word char
    (?:\+?1[\s.\-]?)?       # optional country code
    \(?\d{3}\)?             # area code, optionally parenthesized
    [\s.\-]?                # separator
    \d{3}                   # exchange
    [\s.\-]?                # separator
    \d{4}                   # subscriber
    (?![\w])                # not followed by a word char
    """,
    re.VERBOSE,
)

# Conservative email regex. Catches the common cases without trying to
# implement RFC 5322 in a regex.
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

PHONE_PLACEHOLDER = "[phone redacted]"
EMAIL_PLACEHOLDER = "[email redacted]"


def redact_pii(text: str | None) -> tuple[str | None, dict[str, int]]:
    """Strip phone numbers and email addresses from free-text fields.

    Returns (redacted_text, counts_by_kind). Idempotent: running twice does
    not double-redact (placeholders contain no digits or '@').
    """
    counts = {"phones_redacted": 0, "emails_redacted": 0}
    if not text:
        return text, counts

    def _phone_sub(_m: re.Match[str]) -> str:
        counts["phones_redacted"] += 1
        return PHONE_PLACEHOLDER

    def _email_sub(_m: re.Match[str]) -> str:
        counts["emails_redacted"] += 1
        return EMAIL_PLACEHOLDER

    # Email first so '@'-containing strings don't mask phones in adjacent text.
    redacted = _EMAIL_RE.sub(_email_sub, text)
    redacted = _PHONE_RE.sub(_phone_sub, redacted)
    return redacted, counts
