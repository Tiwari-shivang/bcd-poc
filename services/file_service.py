import json

from fastapi import UploadFile
from sqlalchemy.orm import Session

import DTOs
import helpers
import models

class FileService:
    async def upload_file(self, file: UploadFile, description: str, db: Session):
        file_content = await file.read()
        content = file_content.decode("utf-8")

        schema_json = json.loads(content)

        for table in schema_json:
            summary = self.build_summary(table)

            vector_data = await helpers.generate_embeddings(summary)

            data = models.EmbeddingModel()
            data.data = vector_data.data[0].embedding
            data.content = summary
            data.key = table.get("table")
            data.description = description
            db.add(data)
            db.commit()
            db.refresh(data)
        return DTOs.UploadResponse(
            message="Uploaded successfully",
            description=description,
        )

    def build_summary(self, table: dict) -> str:
        """Build a rich, self-contained textual summary of a table for embedding.

        The original implementation only emitted column names, which left the
        LLM unable to tell enums from text columns or to find the correct
        column name when similar names exist on multiple tables. Here we emit
        type, enum values, primary/foreign keys and relationships.
        """
        table_name = table.get("table")
        columns = table.get("columns", [])
        relationships = table.get("relationships", [])

        lines = [f"Table: {table_name}"]

        if columns:
            lines.append("Columns:")
            for col in columns:
                lines.append(self._format_column_line(col))

        if relationships:
            lines.append("Relationships:")
            lines.extend(relationships)

        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_column_line(col: dict) -> str:
        name = col.get("name", "")
        col_type = col.get("type", "unknown")
        parts = [col_type]

        if col.get("type") == "enum":
            values = col.get("values") or []
            if values:
                parts.append("values: " + ", ".join(values))
        if col.get("is_pk"):
            parts.append("Primary Key")
        if col.get("is_fk"):
            reference = col.get("references")
            parts.append(
                f"Foreign Key -> {reference}" if reference else "Foreign Key"
            )
        if col.get("not_null"):
            parts.append("Not Null")
        if col.get("unique"):
            parts.append("Unique")

        return f"- {name} ({'; '.join(parts)})"