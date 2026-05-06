from services.nl2sql.schema_parser import parse_schema_markdown


def test_parse_schema_has_tables():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    assert schema.has_table("accounts")
    assert schema.has_table("agreements")
    assert schema.has_table("owners")


def test_parse_relationship_direction():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    accounts = schema.table("accounts")
    assert accounts is not None
    assert any(
        r.src_table == "accounts" and r.dst_table == "owners" and r.src_column == "owner_id"
        for r in accounts.relationships
    )


def test_parse_enums():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    accounts = schema.table("accounts")
    col = next(c for c in accounts.columns if c.name == "advito_client_status")
    assert col.enum_values is not None
    assert "Client" in col.enum_values

from services.nl2sql.schema_parser import parse_schema_markdown


def test_parse_schema_has_tables():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    assert schema.has_table("accounts")
    assert schema.has_table("agreements")
    assert schema.has_table("owners")


def test_parse_relationship_direction():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    accounts = schema.table("accounts")
    assert accounts is not None
    # accounts.owner_id -> owners.id should be a directed edge accounts -> owners
    assert any(r.src_table == "accounts" and r.dst_table == "owners" and r.src_column == "owner_id" for r in accounts.relationships)


def test_parse_enums():
    md = open("schema.md", "r", encoding="utf-8").read()
    schema = parse_schema_markdown(md)
    accounts = schema.table("accounts")
    col = next(c for c in accounts.columns if c.name == "advito_client_status")
    assert col.enum_values is not None
    assert "Client" in col.enum_values

