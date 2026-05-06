import pytest

from services.nl2sql.models import QueryPlan
from services.nl2sql.schema_parser import parse_schema_markdown
from services.nl2sql.settings import NL2SQLSettings
from services.nl2sql.validator import LowConfidenceError, PlanValidator, ValidationError


def _schema():
    md = open("schema.md", "r", encoding="utf-8").read()
    return parse_schema_markdown(md)


def test_low_confidence_rejected():
    schema = _schema()
    settings = NL2SQLSettings(planner_confidence_threshold=0.8)
    v = PlanValidator(schema=schema, settings=settings)
    plan = QueryPlan(
        intent="list",
        tables=["accounts"],
        columns=["accounts.id"],
        joins=[],
        filters=[],
        group_by=[],
        order_by=[],
        limit=10,
        aggregations=[],
        confidence=0.2,
        reasoning_summary="uncertain",
    )
    with pytest.raises(LowConfidenceError):
        v.validate(plan)


def test_unknown_column_rejected():
    schema = _schema()
    settings = NL2SQLSettings(planner_confidence_threshold=0.0)
    v = PlanValidator(schema=schema, settings=settings)
    plan = QueryPlan(
        intent="lookup",
        tables=["accounts"],
        columns=["accounts.not_a_real_column"],
        joins=[],
        filters=[],
        group_by=[],
        order_by=[],
        limit=10,
        aggregations=[],
        confidence=1.0,
        reasoning_summary="",
    )
    with pytest.raises(ValidationError):
        v.validate(plan)


def test_multi_hop_joins_validate():
    schema = _schema()
    settings = NL2SQLSettings(planner_confidence_threshold=0.0)
    v = PlanValidator(schema=schema, settings=settings)
    plan = QueryPlan(
        intent="list",
        tables=["agreements", "countries", "annual_vol"],
        columns=["agreements.id", "countries.name", "annual_vol.air_vol"],
        joins=[
            {
                "left_table": "countries",
                "left_column": "agreement_id",
                "right_table": "agreements",
                "right_column": "id",
                "join_type": "inner",
            },
            {
                "left_table": "annual_vol",
                "left_column": "country_id",
                "right_table": "countries",
                "right_column": "id",
                "join_type": "inner",
            },
        ],
        filters=[],
        group_by=[],
        order_by=[],
        limit=10,
        aggregations=[],
        confidence=1.0,
        reasoning_summary="",
    )
    validated = v.validate(plan)
    assert "agreements" in validated.normalized_tables

import pytest

from services.nl2sql.models import QueryPlan
from services.nl2sql.schema_parser import parse_schema_markdown
from services.nl2sql.settings import NL2SQLSettings
from services.nl2sql.validator import PlanValidator, ValidationError, LowConfidenceError


def _schema():
    md = open("schema.md", "r", encoding="utf-8").read()
    return parse_schema_markdown(md)


def test_low_confidence_rejected():
    schema = _schema()
    settings = NL2SQLSettings(planner_confidence_threshold=0.8)
    v = PlanValidator(schema=schema, settings=settings)
    plan = QueryPlan(
        intent="list",
        tables=["accounts"],
        columns=["accounts.id"],
        joins=[],
        filters=[],
        group_by=[],
        order_by=[],
        limit=10,
        aggregations=[],
        confidence=0.2,
        reasoning_summary="uncertain",
    )
    with pytest.raises(LowConfidenceError):
        v.validate(plan)


def test_unknown_column_rejected():
    schema = _schema()
    settings = NL2SQLSettings(planner_confidence_threshold=0.0)
    v = PlanValidator(schema=schema, settings=settings)
    plan = QueryPlan(
        intent="lookup",
        tables=["accounts"],
        columns=["accounts.not_a_real_column"],
        joins=[],
        filters=[],
        group_by=[],
        order_by=[],
        limit=10,
        aggregations=[],
        confidence=1.0,
        reasoning_summary="",
    )
    with pytest.raises(ValidationError):
        v.validate(plan)


def test_multi_hop_joins_validate():
    schema = _schema()
    settings = NL2SQLSettings(planner_confidence_threshold=0.0)
    v = PlanValidator(schema=schema, settings=settings)
    plan = QueryPlan(
        intent="list",
        tables=["agreements", "countries", "annual_vol"],
        columns=["agreements.id", "countries.name", "annual_vol.air_vol"],
        joins=[
            {
                "left_table": "countries",
                "left_column": "agreement_id",
                "right_table": "agreements",
                "right_column": "id",
                "join_type": "inner",
            },
            {
                "left_table": "annual_vol",
                "left_column": "country_id",
                "right_table": "countries",
                "right_column": "id",
                "join_type": "inner",
            },
        ],
        filters=[],
        group_by=[],
        order_by=[],
        limit=10,
        aggregations=[],
        confidence=1.0,
        reasoning_summary="",
    )
    validated = v.validate(plan)
    assert validated.normalized_tables[0] == "agreements"

