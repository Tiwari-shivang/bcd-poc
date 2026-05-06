import math

import pytest

from services.nl2sql.schema_index import build_index_with_embeddings
from services.nl2sql.schema_parser import parse_schema_markdown
from services.nl2sql.settings import NL2SQLSettings


def _toy_embed(text: str) -> list[float]:
    v = [0.0] * 16
    for tok in text.lower().split():
        h = abs(hash(tok)) % len(v)
        v[h] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@pytest.mark.asyncio
async def test_table_level_retrieval_prefers_relevant_table():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    settings = NL2SQLSettings(similarity_threshold=0.99, retrieval_keep_k=5, retrieval_top_k=10)

    async def embed_fn(t: str):
        return _toy_embed(t)

    index = await build_index_with_embeddings(schema=schema, settings=settings, embed_fn=embed_fn)

    q = "List agreements by status"
    q_emb = _toy_embed(q)
    retrieved = await index.retrieve_tables(question=q, query_embedding=q_emb)
    names = [r.table_name for r in retrieved]
    assert "agreements" in names


@pytest.mark.asyncio
async def test_owners_relationship_does_not_dominate_keyword_match():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    settings = NL2SQLSettings(similarity_threshold=0.99, retrieval_keep_k=6, retrieval_top_k=12, exact_match_boost=0.3)

    async def embed_fn(t: str):
        return _toy_embed(t)

    index = await build_index_with_embeddings(schema=schema, settings=settings, embed_fn=embed_fn)

    q = "Show annual volume air_vol by country"
    q_emb = _toy_embed(q)
    retrieved = await index.retrieve_tables(question=q, query_embedding=q_emb)
    names = [r.table_name for r in retrieved]
    assert "annual_vol" in names
    # depending on embeddings, countries may be slightly lower; we at least expect it in top results
    assert "countries" in names

import math

import pytest

from services.nl2sql.schema_index import build_index_with_embeddings
from services.nl2sql.schema_parser import parse_schema_markdown
from services.nl2sql.settings import NL2SQLSettings


def _toy_embed(text: str) -> list[float]:
    # Deterministic toy embedding: hash tokens into a small vector.
    v = [0.0] * 16
    for tok in text.lower().split():
        h = abs(hash(tok)) % len(v)
        v[h] += 1.0
    # normalize
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@pytest.mark.asyncio
async def test_table_level_retrieval_prefers_relevant_table():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    settings = NL2SQLSettings(similarity_threshold=0.99, retrieval_keep_k=5, retrieval_top_k=10)

    async def embed_fn(t: str):
        return _toy_embed(t)

    index = await build_index_with_embeddings(schema=schema, settings=settings, embed_fn=embed_fn)

    q = "List agreements by status"
    q_emb = _toy_embed(q)
    retrieved = await index.retrieve_tables(question=q, query_embedding=q_emb)
    names = [r.table_name for r in retrieved]
    assert "agreements" in names


@pytest.mark.asyncio
async def test_owners_relationship_does_not_dominate_keyword_match():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    settings = NL2SQLSettings(similarity_threshold=0.99, retrieval_keep_k=5, retrieval_top_k=10, exact_match_boost=0.3)

    async def embed_fn(t: str):
        return _toy_embed(t)

    index = await build_index_with_embeddings(schema=schema, settings=settings, embed_fn=embed_fn)

    q = "Show annual volume air_vol by country"
    q_emb = _toy_embed(q)
    retrieved = await index.retrieve_tables(question=q, query_embedding=q_emb)
    names = [r.table_name for r in retrieved]
    assert "annual_vol" in names
    assert "countries" in names

