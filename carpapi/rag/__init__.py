"""CarPapi RAG pipeline.

Two retrieval paths convergent under one ``answer`` step:

  - **Structured retrieval** — Claude (Haiku) reads the user message and
    emits a JSON CarQuery via tool use. The query is JSON-Schema-validated
    by the existing ``carapi_api.query_exec.validate_car_query`` and run
    against ``public.listings`` as parameterised SQL. The LLM never sees
    or writes SQL; this is the policy from ``architecture.md``.

  - **Vector retrieval** — Titan v2 embeds the message. Cosine similarity
    against ``public.listings.embedding`` (pgvector HNSW index) returns
    top-K listings ranked by semantic similarity. Useful when filters are
    fuzzy ("a fun used SUV under 25k").

Both paths converge at ``answer.synthesize()``: Claude (Sonnet) is given
the retrieved listings as context and asked to produce a short prose
explanation. The model is forbidden from inventing listings — the
response must reference only IDs that came back from retrieval.

All Bedrock calls go through ``carpapi.cache.token_cache.TokenCache`` per
``context/ai-cache-rules.md``.
"""
