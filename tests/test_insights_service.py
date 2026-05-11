import os
import asyncio
import json

os.environ.setdefault("OPEN_AI_KEY", "test-key")

from helpers.agent_helper import parse_chart_specs_json
from services.insights_service import InsightsService, SCHEMA_PATHS, _resolved_output_key


def test_resolve_uuid_fields_replaces_foreign_keys_with_names():
    service = InsightsService()
    rows = [
        {
            "nearing_expiry_count": 1,
            "account_id": "1566df8e-5853-4feb-b0e0-52bd560d99f3",
            "country_id": "08be731b-5755-4d9d-b4f1-55e2309a162a",
        }
    ]

    class DummySession:
        pass

    def fake_fetch_display_values(_, __, ___, table_name, display_column, ids):
        values = {
            ("accounts", "name"): {
                "1566df8e-5853-4feb-b0e0-52bd560d99f3": "Acme Corp",
            },
            ("countries", "name"): {
                "08be731b-5755-4d9d-b4f1-55e2309a162a": "Germany",
            },
        }
        assert ids
        return values[(table_name, display_column)]

    service._fetch_display_values = fake_fetch_display_values.__get__(service, InsightsService)

    resolved = service._resolve_uuid_fields(
        DummySession(),
        rows,
        schema_path=str(SCHEMA_PATHS["salesforce"]),
    )

    assert resolved == [
        {
            "nearing_expiry_count": 1,
            "account_name": "Acme Corp",
            "country_name": "Germany",
        }
    ]


def test_resolve_uuid_fields_drops_unmapped_uuid_columns():
    service = InsightsService()
    rows = [{"id": "1566df8e-5853-4feb-b0e0-52bd560d99f3", "client_count": 20}]

    resolved = service._resolve_uuid_fields(
        None,
        rows,
        schema_path=str(SCHEMA_PATHS["salesforce"]),
    )

    assert resolved == [{"client_count": 20}]


def test_resolve_uuid_fields_supports_oip_display_columns():
    service = InsightsService()
    rows = [{"customer_id": "1566df8e-5853-4feb-b0e0-52bd560d99f3", "project_count": 2}]

    class DummySession:
        pass

    def fake_fetch_display_values(_, __, ___, table_name, display_column, ids):
        assert ids == {"1566df8e-5853-4feb-b0e0-52bd560d99f3"}
        assert (table_name, display_column) == ("customers", "global_customer_name")
        return {"1566df8e-5853-4feb-b0e0-52bd560d99f3": "Global Customer A"}

    service._fetch_display_values = fake_fetch_display_values.__get__(service, InsightsService)

    resolved = service._resolve_uuid_fields(
        DummySession(),
        rows,
        schema_path=str(SCHEMA_PATHS["oip"]),
    )

    assert resolved == [{"customer_global_customer_name": "Global Customer A", "project_count": 2}]


def test_get_oip_insights_requires_configured_db():
    service = InsightsService()

    result = asyncio.run(service.get_oip_insights(vector_db=None, oip_exec_db=None))

    assert result == {
        "ok": False,
        "error": "oip_not_configured",
        "message": "OIP insights require `DB_URL_OIP` to be configured on the server.",
        "insights": [],
    }


def test_parse_chart_specs_json_accepts_recharts_payload():
    raw = json.dumps(
        [
            {
                "chart_title": "Contract Mix",
                "chart_description": "Distribution by type",
                "chart_type": "pie",
                "chart_config": {"name_key": "contract_type", "value_key": "contract_count"},
                "sql": "SELECT contract_type, COUNT(*) AS contract_count FROM agreements GROUP BY contract_type",
            },
            {
                "chart_title": "Country Demand",
                "chart_description": "Demand by country",
                "chart_type": "bar",
                "chart_config": {"x_key": "country_name", "y_key": "total_volume"},
                "sql": "SELECT country_name, total_volume FROM demand",
            },
            {
                "chart_title": "Monthly Trend",
                "chart_description": "Trend over time",
                "chart_type": "line",
                "chart_config": {"x_key": "month", "y_key": "agreement_count"},
                "sql": "SELECT month, agreement_count FROM monthly_counts",
            },
        ]
    )

    parsed = parse_chart_specs_json(raw)

    assert [item["chart_type"] for item in parsed] == ["pie", "bar", "line"]


def test_normalize_chart_config_rewrites_uuid_dimension_to_resolved_name():
    service = InsightsService()
    rows = [{"account_name": "Acme Corp", "nearing_expiry_count": 2}]

    config = service._normalize_chart_config(
        "bar",
        {"x_key": "account_id", "y_key": "nearing_expiry_count"},
        rows,
        schema_path=str(SCHEMA_PATHS["salesforce"]),
    )

    assert config == {"x_key": "account_name", "y_key": "nearing_expiry_count"}


def test_get_oip_charts_requires_configured_db():
    service = InsightsService()

    result = asyncio.run(service.get_oip_charts(vector_db=None, oip_exec_db=None))

    assert result == {
        "ok": False,
        "error": "oip_not_configured",
        "message": "OIP chart APIs require `DB_URL_OIP` to be configured on the server.",
        "charts": [],
    }


def test_resolved_output_key_uses_display_column():
    assert _resolved_output_key("account_id", "name") == "account_name"
    assert _resolved_output_key("gcn_id", "client_name") == "gcn_client_name"


def test_enrich_pie_chart_legends_adds_static_legend_metadata():
    service = InsightsService()
    payload = {
        "chart_type": "pie",
        "chart_config": {"name_key": "contract_type", "value_key": "contract_count"},
        "data": [
            {"contract_type": "NDA", "contract_count": 4},
            {"contract_type": "MSA", "contract_count": 6},
        ],
    }

    service._enrich_pie_chart_legends(payload)

    assert payload["chart_config"]["show_legend"] is True
    assert payload["chart_config"]["legend_key"] == "contract_type"
    assert payload["legend"] == [
        {"label": "NDA", "value": 4.0, "percentage": 40.0},
        {"label": "MSA", "value": 6.0, "percentage": 60.0},
    ]


def test_enrich_pie_chart_legends_aggregates_duplicate_labels():
    service = InsightsService()
    payload = {
        "chart_type": "pie",
        "chart_config": {"name_key": "segment", "value_key": "count"},
        "data": [
            {"segment": "Enterprise", "count": 2},
            {"segment": "Enterprise", "count": 3},
            {"segment": "SMB", "count": 5},
        ],
    }

    service._enrich_pie_chart_legends(payload)

    assert payload["legend"] == [
        {"label": "Enterprise", "value": 5.0, "percentage": 50.0},
        {"label": "SMB", "value": 5.0, "percentage": 50.0},
    ]
