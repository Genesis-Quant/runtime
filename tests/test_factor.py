from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

import core.apps.factor as factor_package
from core.apps.factor import (
    FactorAnalysisParameters,
    FactorAnalysisResult,
    analyze_factors,
)
from core.apps.factor import api as factor_api
from core.database.compile.factor.scripts import build_script, write_script
from core.manage import apps as manage_apps
from core.manage.apps import factor as manage_factor


def factor_request() -> dict[str, Any]:
    return {
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "codes": ["000001.SZ", "600000.SH"],
        "factors": [],
    }


def manually_preprocessed_factor_request() -> dict[str, Any]:
    request = factor_request()
    request["derivatives"] = {
        "close_processed": {
            "type": "CS",
            "op": "unary.robust_zscore",
            "fields": {"col": "close"},
            "params": {},
        },
        "close_processed_group": {
            "type": "CS",
            "op": "unary.qcut",
            "fields": {"col": "close_processed"},
            "params": {"q": 5},
        },
    }
    return request


def test_factor_schema_adds_direct_columns_to_query() -> None:
    parameters = FactorAnalysisParameters.model_validate(
        {
            "dataset_query": factor_request(),
            "factor_columns": ["close"],
            "return_columns": ["pct_chg"],
        }
    )

    assert parameters.dataset_query.factors == [
        "close",
        "pct_chg",
        "circ_mv",
    ]


def test_factor_schema_rejects_column_role_conflicts() -> None:
    with pytest.raises(ValidationError, match="不能重叠"):
        FactorAnalysisParameters.model_validate(
            {
                "dataset_query": factor_request(),
                "factor_columns": ["close"],
                "return_columns": ["close"],
            }
        )


def test_factor_schema_requires_dsl_groups_when_preprocess_disabled() -> None:
    with pytest.raises(ValidationError, match="必须输出对应分组列"):
        FactorAnalysisParameters.model_validate(
            {
                "dataset_query": factor_request(),
                "factor_columns": ["close"],
                "return_columns": ["pct_chg"],
                "preprocess": False,
            }
        )


def test_factor_schema_accepts_manually_preprocessed_dsl() -> None:
    parameters = FactorAnalysisParameters.model_validate(
        {
            "dataset_query": manually_preprocessed_factor_request(),
            "factor_columns": ["close_processed"],
            "return_columns": ["pct_chg"],
            "preprocess": False,
        }
    )

    assert parameters.preprocess is False
    assert "close_processed_group" in (
        parameters.dataset_query.derivatives
    )


def test_factor_compiler_contains_public_functions() -> None:
    script = build_script()

    assert script.startswith("module factor\n")
    assert "def factorPreprocess(" in script
    assert "def factorInformationCoefficient(" in script
    assert "def factorGroupReturns(" in script
    assert script.index("def factorZScore(") < script.index(
        "def factorPreprocess("
    )


def test_factor_compiler_writes_query_dependencies(tmp_path: Path) -> None:
    path = write_script(output_dir=tmp_path)

    assert path == tmp_path / "factor.dos"
    assert path.is_file()
    assert (tmp_path / "common.dos").is_file()
    assert (tmp_path / "query.dos").is_file()


def test_factor_manage_command_is_registered_as_own_module() -> None:
    parser = manage_apps.build_parser()

    assert manage_factor in manage_apps.APPLICATIONS
    assert manage_factor.NAME == "factor"
    assert "factor" in parser.format_help()


class FakeLogger:
    def disable_stdout_sink(self) -> None:
        pass

    def list_sinks(self) -> list[Any]:
        return []

    def add_sink(self, sink: Any) -> None:
        pass


class FakeSession:
    def __init__(self) -> None:
        self.msg_logger = FakeLogger()
        self.uploads: list[dict[str, Any]] = []
        self.scripts: list[str] = []
        self.closed = False

    def upload(self, values: dict[str, Any]) -> None:
        self.uploads.append(values)

    def run(self, script: str) -> pd.DataFrame:
        self.scripts.append(script)
        factor = next(
            (
                values["coreFactorCurrentColumn"]
                for values in reversed(self.uploads)
                if "coreFactorCurrentColumn" in values
            ),
            None,
        )
        factor_value = {"close": 0.2, "open": 0.3, "close_processed": 0.4}.get(
            factor,
            0.1,
        )
        if "factor::factorInformationCoefficient" in script:
            return pd.DataFrame({
                "time": pd.to_datetime(["2025-01-02"]),
                "pct_chg_ic": [factor_value],
                "pct_chg_rank_ic": [factor_value / 2],
            })
        if "factor::factorGroupReturns" in script:
            return pd.DataFrame({
                "time": pd.to_datetime(["2025-01-02"]),
                "pct_chg_group0": [factor_value],
            })
        return pd.DataFrame()

    def close(self) -> None:
        self.closed = True


def test_factor_api_builds_server_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()

    def build_query_table(
        request: Any,
        *,
        session: Any,
        **references: str,
    ) -> tuple[Any, list[str]]:
        return request, ["time", "code", *request.factors]

    metadata = pd.DataFrame(
        {
            "code": ["000001.SZ", "600000.SH"],
            "industry": ["银行", "银行"],
            "sector": ["金融", "金融"],
        }
    )
    monkeypatch.setattr(
        factor_api.query_api,
        "build_query_table",
        build_query_table,
    )
    monkeypatch.setattr(
        factor_api,
        "get_stock_metadata",
        lambda: (
            ("000001.SZ", "600000.SH"),
            metadata,
            {
                "000001.SZ": "金融",
                "600000.SH": "金融",
            },
        ),
    )

    result = analyze_factors(
        factor_request(),
        ["close", "open"],
        ["pct_chg"],
        session=session,
    )

    assert isinstance(result, FactorAnalysisResult)
    assert result.factor_columns == ("close", "open")
    assert "coreFactorProcessedData" in "\n".join(session.scripts)
    assert "factor::factorInformationCoefficient" not in "\n".join(session.scripts)
    assert "factor::factorGroupReturns" not in "\n".join(session.scripts)

    information_coefficient = result.information_coefficient
    assert information_coefficient.columns.tolist() == [
        "time",
        "close_pct_chg_ic",
        "close_pct_chg_rank_ic",
        "open_pct_chg_ic",
        "open_pct_chg_rank_ic",
    ]
    group_returns = result.group_returns
    assert group_returns.columns.tolist() == [
        "time",
        "close_pct_chg_group0",
        "open_pct_chg_group0",
    ]
    assert "factor::factorInformationCoefficient" in "\n".join(session.scripts)
    assert "factor::factorGroupReturns" in "\n".join(session.scripts)
    assert not hasattr(result, "information_coefficients")
    assert not hasattr(result, "all_group_returns")


def test_factor_api_can_use_dsl_preprocessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()

    def build_query_table(
        request: Any,
        *,
        session: Any,
        **references: str,
    ) -> tuple[Any, list[str]]:
        return request, [
            "time",
            "code",
            *request.factors,
            *request.derivatives,
        ]

    monkeypatch.setattr(
        factor_api.query_api,
        "build_query_table",
        build_query_table,
    )
    monkeypatch.setattr(
        factor_api,
        "industry_metadata",
        lambda level: pytest.fail(
            "关闭预处理时不应加载行业元数据"
        ),
    )

    result = analyze_factors(
        manually_preprocessed_factor_request(),
        ["close_processed"],
        ["pct_chg"],
        session=session,
        preprocess=False,
    )

    scripts = "\n".join(session.scripts)
    assert result.parameters.preprocess is False
    assert "factor::factorPreprocess" not in scripts
    assert (
        "coreFactorProcessedData = coreFactorInputData"
        in scripts
    )
    assert "factor::factorInformationCoefficient" not in scripts
    assert "factor::factorGroupReturns" not in scripts

    result.information_coefficient
    result.group_returns
    scripts = "\n".join(session.scripts)
    assert "factor::factorInformationCoefficient" in scripts
    assert "factor::factorGroupReturns" in scripts


class FakeFactorResult:
    def __init__(self) -> None:
        self.accessed: list[str] = []
        self.processed_table = pd.DataFrame(
            {
                "time": pd.to_datetime(["2025-01-02"]),
                "code": ["000001.SZ"],
                "alpha": [0.5],
                "alpha_group": [1],
            }
        )
        self.information_coefficient_table = pd.DataFrame({
            "time": pd.to_datetime(["2025-01-02"]),
            "alpha_return_ic": [0.2],
            "alpha_return_rank_ic": [0.1],
            "beta_return_ic": [0.3],
            "beta_return_rank_ic": [0.4],
        })
        self.group_returns_table = pd.DataFrame({
            "time": pd.to_datetime(["2025-01-02"]),
            "alpha_return_group0": [0.01],
            "beta_return_group0": [0.02],
        })

    @property
    def processed_data(self) -> pd.DataFrame:
        self.accessed.append("processed_data")
        return self.processed_table

    @property
    def information_coefficient(self) -> pd.DataFrame:
        self.accessed.append("information_coefficient")
        return self.information_coefficient_table

    @property
    def group_returns(self) -> pd.DataFrame:
        self.accessed.append("group_returns")
        return self.group_returns_table

    def __enter__(self) -> "FakeFactorResult":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def test_factor_cli_writes_only_requested_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_file = tmp_path / "factor.json"
    input_file.write_text(
        """
        {
          "dataset_query": {"start_date": "2025-01-01"},
          "factor_columns": ["alpha", "beta"],
          "return_columns": ["return"],
          "preprocess": false,
          "output_dir": "output"
        }
        """,
        encoding="utf-8",
    )
    received: dict[str, Any] = {}
    factor_result = FakeFactorResult()

    def fake_analyze_factors(**arguments: Any) -> FakeFactorResult:
        received.update(arguments)
        return factor_result

    monkeypatch.setattr(
        factor_package,
        "analyze_factors",
        fake_analyze_factors,
    )

    assert manage_apps.main(
        [
            "factor",
            "--input-file",
            str(input_file),
            "--output",
            "information_coefficient",
        ]
    ) == 0

    output_dir = tmp_path / "output"
    assert sorted(path.name for path in output_dir.glob("*.parquet")) == [
        "factor_information_coefficients.parquet",
    ]
    information_coefficients = pd.read_parquet(
        output_dir / "factor_information_coefficients.parquet"
    )
    assert information_coefficients.columns.tolist() == [
        "time",
        "alpha_return_ic",
        "alpha_return_rank_ic",
        "beta_return_ic",
        "beta_return_rank_ic",
    ]
    assert factor_result.accessed == ["information_coefficient"]
    assert received["preprocess"] is False
