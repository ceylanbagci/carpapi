from __future__ import annotations

"""DealerRater.com crawler — STUB.

⚠️  Important: DealerRater's Terms of Service prohibit automated access
without prior written permission. This module is intentionally not
implemented for production use.

Per project policy (context/scraper-rules.md):
    "Allowed inputs: licensed APIs, sanctioned partner feeds, public
    sources whose ToS permit automated access."

Before completing this module, do ONE of:
    1. Obtain a written license/API agreement from DealerRater.
    2. Confirm a public RSS/feed/API exists that DOES permit automated
       access at the rate we need.
    3. Drop this source from the roadmap.

If any of those are satisfied, replace the body of `fetch_listings` with
the real implementation. Until then it raises so accidental imports cannot
silently kick off ToS-violating traffic.

Per project policy (guideline 4): when implemented, use only the approved
zero-AI stack (requests, BeautifulSoup4, Selenium, lxml). No LLM calls
in this layer ever.

Reference: https://www.dealerrater.com/terms-of-service.aspx
"""

import os


_ENABLE_FLAG = "CARAPI_ENABLE_DEALERRATER"


class ToSCheckRequired(RuntimeError):
    """Raised to prevent accidental ToS violation."""


def fetch_listings(query: str, **_kwargs: object) -> list[dict]:
    """Placeholder. Refuses to run until ToS posture is documented."""
    if os.environ.get(_ENABLE_FLAG) != "1":
        raise ToSCheckRequired(
            "carpapi.scrapers.dealerrater is a stub. DealerRater's ToS "
            "prohibits automated access by default. To enable this module, "
            f"first document ToS approval (license/API/written permission) in "
            "context/scraper-rules.md, then set "
            f"{_ENABLE_FLAG}=1 and replace the body of fetch_listings()."
        )
    # Even when the flag is set, the real implementation is not yet written.
    raise NotImplementedError(
        "fetch_listings is not implemented. Implement against the approved "
        "stack (requests, BeautifulSoup4, lxml, Selenium) only."
    )
