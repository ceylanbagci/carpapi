from __future__ import annotations

"""Smoke-test PII redaction on free-text listing fields.

Tests pure redact_pii() — no schema, no DB. Verifies phone/email patterns
are stripped per context/compliance-rules.md.

Run from repo root:
    python eval/run_pii_redaction_eval.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pipeline"))

from carapi_pipeline.pii import redact_pii  # noqa: E402


# (label, input_text, must_NOT_contain_substrs, expected_phones, expected_emails)
CASES = [
    (
        "no PII passes through",
        "Low miles, one owner, NJ.",
        [],
        0,
        0,
    ),
    (
        "dashed phone redacted",
        "Call 555-123-4567 to schedule a test drive.",
        ["555-123-4567", "555"],
        1,
        0,
    ),
    (
        "parenthesized phone redacted",
        "Contact (212) 555-9000 or stop by.",
        ["(212)", "555-9000"],
        1,
        0,
    ),
    (
        "dotted phone redacted",
        "Call 415.555.7890 today",
        ["415.555.7890"],
        1,
        0,
    ),
    (
        "leading 1- phone redacted",
        "Dial 1-800-555-2671 for financing.",
        ["1-800-555-2671", "800-555-2671"],
        1,
        0,
    ),
    (
        "+1 phone redacted",
        "International: +1 510 555 1212",
        ["510 555 1212", "+1"],
        1,
        0,
    ),
    (
        "email redacted",
        "Email seller@example.com for pictures.",
        ["seller@example.com", "@example.com"],
        0,
        1,
    ),
    (
        "phone and email both redacted",
        "Call 555-867-5309 or email john.doe+listings@dealer.co",
        ["555-867-5309", "john.doe+listings@dealer.co"],
        1,
        1,
    ),
    (
        "VIN-like 17-char string is NOT misread as phone",
        "VIN: 4T1C11AK5NU123456 listed in NJ",
        [],  # VINs should pass through unchanged (no phone match)
        0,
        0,
    ),
    (
        "year + price are NOT phones",
        "2022 model, $24,500, NJ inventory ID 1234567",
        [],
        0,
        0,
    ),
    (
        "idempotent: redacted text re-redacted unchanged",
        "Call [phone redacted] or email [email redacted].",
        ["555", "@"],
        0,
        0,
    ),
    (
        "None passthrough",
        None,
        [],
        0,
        0,
    ),
]


def main() -> int:
    failures: list[str] = []
    for label, text, must_not, ex_phones, ex_emails in CASES:
        out, counts = redact_pii(text)
        if text is None:
            if out is not None:
                failures.append(f"{label}: None expected, got {out!r}")
            continue
        for needle in must_not:
            if out is not None and needle in out:
                failures.append(
                    f"{label}: leaked {needle!r} in {out!r}"
                )
        if counts["phones_redacted"] != ex_phones:
            failures.append(
                f"{label}: expected {ex_phones} phones, got {counts['phones_redacted']} in {out!r}"
            )
        if counts["emails_redacted"] != ex_emails:
            failures.append(
                f"{label}: expected {ex_emails} emails, got {counts['emails_redacted']} in {out!r}"
            )

    passed = len(CASES) - len(failures)
    print(f"\nPII redaction eval: {passed}/{len(CASES)} passed")
    if failures:
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
