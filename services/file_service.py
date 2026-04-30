import json
from pathlib import Path

from fastapi import UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import DTOs
import helpers
import models
from helpers import catalog_summary, datasource


class FileService:
    async def upload_file(
        self,
        file: UploadFile,
        description: str,
        vector_db: Session,
        *,
        data_source: str = "salesforce",
    ):
        file_content = await file.read()
        content = file_content.decode("utf-8")
        schema_json = json.loads(content)

        norm = datasource.normalize_source(data_source)
        if norm is None:
            raise HTTPException(
                status_code=400,
                detail='data_source must be "salesforce" or "oip"',
            )

        for table in schema_json:
            summary = catalog_summary.build_table_catalog_summary(table)
            vector_data = await helpers.generate_embeddings(summary)

            emb = models.EmbeddingModel()
            emb.data = vector_data.data[0].embedding
            emb.content = summary
            emb.key = table.get("table")
            emb.description = description
            emb.data_source = norm
            vector_db.add(emb)
            vector_db.commit()
            vector_db.refresh(emb)

        return DTOs.UploadResponse(
            message="Uploaded successfully",
            description=description,
        )



PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OIP_SCHEMA_PATH = PROJECT_ROOT / "schema_oip.json"


async def seed_oip_embeddings_from_repo_file(
    vector_db: Session,
    *,
    schema_path: Path | None = None,
    description: str = "OIP catalogue (seeded)",
) -> int:
    """Idempotently ingest `schema_oip.json` embeddings with ``data_source=oip``.

    Skips tables that already have an OIP row for the same `key`.
    Returns number of new rows inserted.
    """
    path = schema_path or DEFAULT_OIP_SCHEMA_PATH
    if not path.is_file():
        return 0

    raw = path.read_text(encoding="utf-8")
    tables = json.loads(raw)
    inserted = 0

    for table in tables:
        tbl = table.get("table")
        if not tbl:
            continue

        exists = vector_db.execute(
            select(models.EmbeddingModel.id).where(
                models.EmbeddingModel.key == tbl,
                models.EmbeddingModel.data_source == datasource.OIP,
            )
        ).scalar_one_or_none()
        if exists:
            continue

        summary = catalog_summary.build_table_catalog_summary(table)
        vec = await helpers.generate_embeddings(summary)
        emb = models.EmbeddingModel()
        emb.data = vec.data[0].embedding
        emb.content = summary
        emb.key = tbl
        emb.description = description
        emb.data_source = datasource.OIP
        vector_db.add(emb)
        vector_db.commit()
        vector_db.refresh(emb)
        inserted += 1

    return inserted
