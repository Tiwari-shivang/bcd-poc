"""Shared text builders for catalogue JSON (Salesforce uploads + OIP schema file)."""


def fk_lines_from_columns(table_name: str, columns: list) -> list[str]:
    lines: list[str] = []
    for col in columns or []:
        if col.get("is_fk"):
            tgt = col.get("references") or ""
            lines.append(f"{table_name}.{col.get('name')} -> {tgt}")
    return lines


def format_column_line(col: dict) -> str:
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


def build_table_catalog_summary(table: dict) -> str:
    table_name = table.get("table")
    columns = table.get("columns", [])
    relationships = list(table.get("relationships", []))

    if not relationships:
        relationships.extend(fk_lines_from_columns(str(table_name), columns))

    lines = [f"Table: {table_name}"]

    if columns:
        lines.append("Columns:")
        for col in columns:
            lines.append(format_column_line(col))

    if relationships:
        lines.append("Relationships:")
        lines.extend(relationships)

    return "\n".join(lines) + "\n"
