import subprocess
import sys
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from core.apps.backtest import api as backtest_api
from core.apps.backtest.schema import BacktestParameters, DAILY_MESSAGE_FACTORS
from core.apps.factor.schema import FactorAnalysisParameters
from core.apps.query import FactorQuery
from core.apps.query import api as query_api


def query_request() -> dict[str, Any]:
    return {
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "codes": ["000001.SZ"],
        "factors": ["close"],
    }


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
        self.closed = False
        self.uploads: list[dict[str, Any]] = []
        self.scripts: list[str] = []

    def upload(self, values: dict[str, Any]) -> None:
        self.uploads.append(values)

    def run(self, script: str) -> bool:
        self.scripts.append(script)
        return False

    def close(self) -> None:
        self.closed = True


def test_execute_query_validates_dict_request(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    received: list[FactorQuery] = []

    def build_query_table(query: FactorQuery, *, session: Any) -> None:
        received.append(query)

    monkeypatch.setattr(query_api, "build_query_table", build_query_table)
    result = query_api.execute_query(query_request(), session=session)

    assert isinstance(received[0], FactorQuery)
    result.close()
    assert session.closed is True


def test_execute_codes_query_returns_distinct_query_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[tuple[FactorQuery, dict[str, str]]] = []

    class CodesSession:
        def run(self, script: str) -> np.ndarray:
            assert "exec distinct code" in script
            assert "from selectedData" in script
            return np.asarray(["000001.SZ", "600000.SH"])

    def build_query_table(query: FactorQuery, *, session: Any, **references: str) -> None:
        received.append((query, references))

    monkeypatch.setattr(query_api, "build_query_table", build_query_table)
    codes = query_api.execute_codes_query(
        query_request(),
        session=CodesSession(),
        source_ref="selectedSource",
        computed_ref="selectedComputed",
        filtered_ref="selectedFiltered",
        data_ref="selectedData",
    )

    assert codes == ["000001.SZ", "600000.SH"]
    assert isinstance(received[0][0], FactorQuery)
    assert received[0][1]["data_ref"] == "selectedData"


def test_build_query_table_validates_distinct_references() -> None:
    query = FactorQuery.model_validate(query_request())
    with pytest.raises(ValueError, match="不能重复"):
        query_api.build_query_table(query, session=None, source_ref="same", computed_ref="same")
    with pytest.raises(ValueError, match="不是合法的 DolphinDB 标识符"):
        query_api.build_query_table(query, session=None, data_ref="bad;drop")
    with pytest.raises(ValueError, match="内部保留名称"):
        query_api.build_query_table(query, session=None, source_ref="coreQueryStart")


def test_backtest_defaults_and_factor_order() -> None:
    parameters = BacktestParameters.model_validate({
        "dataset_query": query_request(),
        "callbacks": {"initialize": "def initialize(mutable context) {}"},
        "utils": None,
        "name": None,
        "config": None,
    })

    assert parameters.name is None
    assert parameters.config["cash"] == 1_000_000.0
    assert parameters.dataset_query.factors == [
        "close",
        *(factor for factor in DAILY_MESSAGE_FACTORS if factor != "close"),
    ]


def test_backtest_uses_codes_query_and_preserves_dataset_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    dataset_query = query_request()
    dataset_query["derivatives"] = {
        "eligible": {
            "type": "DIRECT",
            "op": "binary.gt",
            "fields": {"left": "pe", "right": 5},
            "params": {},
        }
    }
    dataset_query["filters"] = ["eligible"]
    codes_query = query_request()
    codes_query["factors"] = ["pe"]
    received: dict[str, Any] = {}

    def execute_codes_query(request: Any, *, session: Any, **references: str) -> list[str]:
        received["codes_query"] = request
        received["codes_references"] = references
        return ["600000.SH", "000001.SZ"]

    def build_query_table(request: Any, *, session: Any, **references: str) -> list[str]:
        received["dataset_query"] = request
        received["dataset_references"] = references
        return ["time", "code", *request.factors, *request.derivatives]

    monkeypatch.setattr(query_api, "execute_codes_query", execute_codes_query)
    monkeypatch.setattr(query_api, "build_query_table", build_query_table)
    result = backtest_api.run_backtest(dataset_query, {}, codes_query=codes_query, session=session)

    assert received["dataset_query"].codes == ["600000.SH", "000001.SZ"]
    assert received["dataset_query"].filters == ["eligible"]
    assert received["codes_references"]["data_ref"] == backtest_api.CODES_DATA_REF
    assert next(values["coreBacktestCodes"].tolist() for values in session.uploads if "coreBacktestCodes" in values) == ["600000.SH", "000001.SZ"]
    result.close()


@pytest.mark.parametrize("field", ["callbacks", "utils"])
def test_backtest_rejects_mismatched_function_names(field: str) -> None:
    data: dict[str, Any] = {
        "dataset_query": query_request(),
        "callbacks": {"initialize": "def initialize(mutable context) {}"},
    }
    data[field] = {"initialize": "def wrong(mutable context) {}"}
    with pytest.raises(ValidationError, match="定义的函数名是 'wrong'"):
        BacktestParameters.model_validate(data)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"cash": 0}, "cash.*大于 0"),
        ({"cash": float("nan")}, "NaN"),
        ({"commission": -0.1}, "commission.*不能小于 0"),
        ({"tax": float("inf")}, "正负无穷"),
        ({"matchingRatio": 1.1}, "matchingRatio.*0 到 1"),
        ({"orderBookMatchingRatio": -0.1}, "orderBookMatchingRatio.*0 到 1"),
        ({"matchingMode": "2"}, "matchingMode.*必须是整数"),
        ({"matchingMode": 4}, "matchingMode.*只能是"),
        ({"frequency": -1}, "frequency.*不能小于 0"),
        ({"outputOrderInfo": 1}, "outputOrderInfo.*必须是 bool"),
    ],
)
def test_backtest_rejects_invalid_known_config(
    config: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        BacktestParameters.model_validate({
            "dataset_query": query_request(),
            "callbacks": {},
            "config": config,
        })


def test_backtest_validates_all_reference_conflicts() -> None:
    with pytest.raises(ValidationError, match="不能重复"):
        BacktestParameters.model_validate({
            "dataset_query": query_request(),
            "callbacks": {},
            "source_ref": "sameRef",
            "message_ref": "sameRef",
        })
    with pytest.raises(ValidationError, match="内部保留名称"):
        BacktestParameters.model_validate({
            "dataset_query": query_request(),
            "callbacks": {},
            "message_ref": "coreBacktestData",
        })


@pytest.mark.parametrize(
    "callback",
    [
        "def onBar(mutable context) {}",
        "def onBar(context, message, indicator) {}",
        "def onBar(mutable context, message, message) {}",
    ],
)
def test_backtest_rejects_invalid_callback_signatures(callback: str) -> None:
    with pytest.raises(ValidationError):
        BacktestParameters.model_validate({
            "dataset_query": query_request(),
            "callbacks": {"onBar": callback},
        })


def test_backtest_rejects_callback_names_in_utils() -> None:
    with pytest.raises(ValidationError, match="同名函数|回调保留名称"):
        BacktestParameters.model_validate({
            "dataset_query": query_request(),
            "callbacks": {"initialize": "def initialize(mutable context) {}"},
            "utils": {"initialize": "def initialize(mutable context) {}"},
        })


def test_backtest_rejects_utility_name_colliding_with_runtime_variable() -> None:
    with pytest.raises(ValidationError, match="内部或结果变量重名"):
        BacktestParameters.model_validate({
            "dataset_query": query_request(),
            "callbacks": {},
            "utils": {"coreBacktestConfig": "def coreBacktestConfig(value) { return value }"},
        })


def test_backtest_rejects_leading_underscore_function_names() -> None:
    with pytest.raises(ValidationError, match="完整的 DolphinDB def"):
        BacktestParameters.model_validate({
            "dataset_query": query_request(),
            "callbacks": {},
            "utils": {"_helper": "def _helper(value) { return value }"},
        })


def test_factor_rejects_duplicate_columns() -> None:
    with pytest.raises(ValidationError, match="factor_columns 不能包含重复值"):
        FactorAnalysisParameters.model_validate({
            "dataset_query": query_request(),
            "factor_columns": ["close", " close "],
            "return_columns": ["pct_chg"],
        })


def test_factor_rejects_market_value_as_return() -> None:
    with pytest.raises(ValidationError, match="market_value_column 不能同时作为收益率列"):
        FactorAnalysisParameters.model_validate({
            "dataset_query": query_request(),
            "factor_columns": ["close"],
            "return_columns": ["circ_mv"],
            "market_value_column": "circ_mv",
        })


@pytest.mark.parametrize("value", ["2025/01/01", "2025-01", "2025-01-01 12:30"])
def test_query_rejects_non_iso_dates(value: str) -> None:
    request = query_request()
    request["start_date"] = value
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        FactorQuery.model_validate(request)


@pytest.mark.parametrize(
    "derivative",
    [
        {
            "type": "DIRECT",
            "op": "ternary.where",
            "fields": {"condition": 1, "if_true": "close", "if_false": "open"},
            "params": {},
        },
        {
            "type": "DIRECT",
            "op": "unary.not",
            "fields": {"col": 1},
            "params": {},
        },
        {
            "type": "DIRECT",
            "op": "binary.and",
            "fields": {"left": 1, "right": 2},
            "params": {},
        },
    ],
)
def test_query_rejects_non_bool_logical_operands(derivative: dict[str, Any]) -> None:
    request = query_request()
    request["factors"] = []
    request["derivatives"] = {"result": derivative}
    with pytest.raises(ValidationError):
        FactorQuery.model_validate(request)


def test_query_rejects_named_non_bool_logical_operand() -> None:
    request = query_request()
    request["factors"] = []
    request["derivatives"] = {
        "numeric": {
            "type": "DIRECT",
            "op": "unary.get",
            "fields": {"col": "close"},
            "params": {},
        },
        "result": {
            "type": "DIRECT",
            "op": "binary.and",
            "fields": {"left": "numeric", "right": True},
            "params": {},
        },
    }
    with pytest.raises(ValidationError, match="逻辑操作数引用必须返回 BOOL"):
        FactorQuery.model_validate(request)


def test_execute_query_validates_worker_factors_at_execution() -> None:
    query = FactorQuery.model_validate(query_request())
    query.factors = ["not_a_worker_factor"]
    with pytest.raises(ValueError, match="Worker 未声明"):
        query_api.execute_query(query, session=FakeSession())


def test_query_model_keeps_empty_codes_without_loading_market_data() -> None:
    request = query_request()
    request["codes"] = []

    query = FactorQuery.model_validate(request)

    assert query.codes == []


def test_model_import_does_not_load_runtime_clients() -> None:
    command = (
        "import sys; "
        "from core.apps.backtest.schema import BacktestParameters; "
        "from core.apps.factor.schema import FactorAnalysisParameters; "
        "from core.apps.query.schema import FactorQuery; "
        "print(*(name in sys.modules for name in "
        "('core.config', 'core.workers', 'core.apps.query.api', 'dolphindb', 'tushare')))"
    )
    completed = subprocess.run([sys.executable, "-c", command], check=True, capture_output=True, text=True)

    assert completed.stdout.strip() == "False False False False False"
