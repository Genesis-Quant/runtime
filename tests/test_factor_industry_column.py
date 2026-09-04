from __future__ import annotations

from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from runtime.apps.factor.api import analyze_factors
from runtime.apps.factor.schema import FactorAnalysisParameters


def factor_parameters(**updates: object) -> dict[str, object]:
    parameters: dict[str, object] = {
        "codes_query": None,
        "dataset_query": {
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "lookback": "P5D",
            "codes": [],
            "factors": ["close", "circ_mv"],
            "derivatives": {
                "future_return": {
                    "type": "TS",
                    "op": "unary.pct_change",
                    "fields": {"col": "close"},
                    "params": {"periods": 1},
                },
            },
            "filters": [],
        },
        "factor_columns": ["close"],
        "return_columns": ["future_return"],
        "return_specs": {
            "future_return": {"kind": "simple", "periods": 1},
        },
        "n_groups": 5,
        "n_select": 10,
        "preprocess": True,
        "market_value_column": "circ_mv",
        "industry_column": "industry",
    }
    parameters.update(updates)
    return parameters


def test_dynamic_industry_column_must_be_present_in_dataset_query() -> None:
    with pytest.raises(ValidationError, match="industry_l2"):
        FactorAnalysisParameters.model_validate(
            factor_parameters(industry_column="industry_l2")
        )

    data = factor_parameters(industry_column="industry_l2")
    data["dataset_query"]["factors"].append("industry_l2")
    parameters = FactorAnalysisParameters.model_validate(data)
    assert parameters.dataset_query.factors == ["close", "circ_mv", "industry_l2"]


def test_legacy_industry_mapping_does_not_add_query_column() -> None:
    parameters = FactorAnalysisParameters.model_validate(factor_parameters())

    assert parameters.industry_column == "industry"
    assert "industry" not in parameters.dataset_query.factors


def test_industry_column_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError, match="industry_column"):
        FactorAnalysisParameters.model_validate(
            factor_parameters(industry_column="industry_l4")
        )


@pytest.mark.parametrize(
    ("industry_column", "uses_legacy_mapping"),
    [
        ("industry", True),
        ("industry_l0", False),
        ("industry_l3", False),
    ],
)
def test_analyze_factors_uses_selected_industry_column(
        industry_column: str,
        uses_legacy_mapping: bool,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    monkeypatch.setattr(
        "runtime.apps.factor.api.redirect_session_output",
        lambda current_session: None,
    )
    build_query_table = Mock()
    monkeypatch.setattr(
        "runtime.apps.factor.api.query_api.build_query_table",
        build_query_table,
    )

    if uses_legacy_mapping:
        monkeypatch.setattr(
            "runtime.apps.factor.api.get_stock_metadata",
            lambda: ({}, {}, {"000001.SZ": "金融"}),
        )
    else:
        monkeypatch.setattr(
            "runtime.apps.factor.api.get_stock_metadata",
            lambda: (_ for _ in ()).throw(
                AssertionError("动态行业不应加载静态行业映射")
            ),
        )

    data = factor_parameters(industry_column=industry_column)
    if not uses_legacy_mapping:
        data["dataset_query"]["factors"].append(industry_column)
    analyze_factors(
        data["dataset_query"],
        data["factor_columns"],
        data["return_columns"],
        return_specs=data["return_specs"],
        session=session,
        n_groups=data["n_groups"],
        n_select=data["n_select"],
        preprocess=data["preprocess"],
        market_value_column=data["market_value_column"],
        industry_column=industry_column,
    )

    uploaded = session.upload.call_args.args[0]
    assert uploaded["coreFactorIndustryColumn"] == industry_column
    assert uploaded["coreFactorTurnoverPeriods"].tolist() == [1]
    assert ("coreFactorCodeToIndustry" in uploaded) is uses_legacy_mapping
    query = build_query_table.call_args.args[0]
    assert (industry_column in query.factors) is not uses_legacy_mapping
    scripts = "\n".join(call.args[0] for call in session.run.call_args_list)
    assert "coreFactorIndustryColumn" in scripts
    assert (
        'coreFactorInputData["industry"] = coreFactorCodeToIndustry'
        in scripts
    ) is uses_legacy_mapping
