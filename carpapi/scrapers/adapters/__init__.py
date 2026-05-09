"""Per-CMS adapter modules.

Adapters are added in Phase 2 (after CMS-discovery results show which
platforms are worth implementing). Each adapter implements the protocol
defined in carpapi/scrapers/dealership_page.py: parse(html, url) → dict.

Naming: one file per CMS, snake_case (dealer_dot_com.py, dealeron.py,
dealer_inspire.py, etc.).
"""
