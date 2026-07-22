"""验证统一长表查询、依赖提取、宽表整理和 DSL 衔接。"""

import json
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from core.database import query as factor_query
from core.operators import Derivative


def _direct(operation: str, fields: dict[str, object]) -> Derivative:
    """构造一个已校验 DIRECT 节点。"""
    return Derivative.model_validate(
        {"type": "DIRECT", "op": operation, "fields": fields, "params": {}}
    )


def _valid_request(**changes: Any) -> dict[str, Any]:
    """返回可按需覆盖的最小查询 JSON。"""
    value: dict[str, Any] = {
        "start_date": "2024-01-02",
        "end_date": "2024-01-04",
        "codes": ["A", "B"],
        "factors": ["close"],
        "derivatives": {},
    }
    value.update(changes)
    return value


def test_factor_query_normalizes_lists_and_accepts_derivatives() -> None:
    """股票和 factor 去空格去重，合法派生因子完成具体模型分发。"""
    request = factor_query.FactorQuery.model_validate(
        _valid_request(
            codes=[" A ", "B", "A"],
            factors=[" close ", "is_st", "close"],
            derivatives={
                " double_close ": _direct(
                    "binary.mul", {"left": "close", "right": 2}
                )
            },
        )
    )
    assert request.codes == ["A", "B"]
    assert request.factors == ["close", "is_st"]
    assert request.derivatives["double_close"].op == "binary.mul"
    assert request.lookback == timedelta(0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (timedelta(hours=6), timedelta(hours=6)),
        ("10D", timedelta(days=10)),
        ("P2DT12H", timedelta(days=2, hours=12)),
    ],
)
def test_factor_query_parses_lookback_timedelta(
    value: str | timedelta,
    expected: timedelta,
) -> None:
    """lookback 接受 pandas 和 ISO 8601 TimeDelta 字符串。"""
    request = factor_query.FactorQuery.model_validate(
        _valid_request(lookback=value)
    )
    assert request.lookback == expected


def test_factor_query_accepts_all_codes() -> None:
    """codes 为 NULL 表示查询区间内全部股票，不被误判为空列表。"""
    request = factor_query.FactorQuery.model_validate(
        _valid_request(codes=None)
    )
    assert request.codes is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"start_date": "bad"}, "不是有效日期"),
        ({"start_date": "2024-02-01", "end_date": "2024-01-01"}, "不能晚于"),
        ({"codes": []}, "codes 不能为空"),
        ({"lookback": "-1D"}, "lookback 不能小于 0"),
        ({"lookback": "not-a-duration"}, "lookback 不是有效 TimeDelta"),
        ({"lookback": 1}, "lookback 必须是 timedelta 或 TimeDelta 字符串"),
        ({"codes": ["A", " "]}, "codes 不能包含空值"),
        ({"factors": [], "derivatives": {}}, "至少提供一项"),
        ({"factors": ["time"]}, "factors 不能使用保留名称"),
        (
            {
                "factors": ["x"],
                "derivatives": {
                    " x ": _direct("unary.get", {"col": "x"})
                },
            },
            "名称冲突",
        ),
        ({"factors": [], "derivatives": {"time": _direct("nullary.true", {})}}, "保留名称"),
        ({"factors": [], "derivatives": {" ": _direct("nullary.true", {})}}, "空名称"),
        (
            {
                "factors": [],
                "derivatives": {
                    "signal": _direct("nullary.true", {}),
                    " signal ": _direct("nullary.false", {}),
                },
            },
            "去除首尾空格后重复",
        ),
    ],
)
def test_factor_query_rejects_invalid_contract(
    changes: dict[str, Any],
    message: str,
) -> None:
    """日期、空列表、空名称、保留名称和输出冲突均在查询前失败。"""
    with pytest.raises(ValidationError, match=message):
        factor_query.FactorQuery.model_validate(_valid_request(**changes))


def test_normalize_names_rejects_non_strings_and_empty_values() -> None:
    """内部依赖列表同样严格要求非空字符串并保持顺序去重。"""
    assert factor_query.normalize_names(["a", "a", "b"], "names") == ["a", "b"]
    with pytest.raises(ValueError, match="必须全部是字符串"):
        factor_query.normalize_names(["a", 1], "names")  # type: ignore[list-item]
    with pytest.raises(ValueError, match="不能包含空值"):
        factor_query.normalize_names([" "], "names")


def test_derivative_factors_walks_nested_fields_on_and_named_dependencies() -> None:
    """依赖提取只保留原始列，不把命名因子、参数字符串或 time/code 当 factor。"""
    positive = _direct("binary.gt", {"left": "close", "right": 0})
    mean = Derivative.model_validate(
        {
            "type": "TS",
            "op": "unary.rolling_mean",
            "fields": {"col": "close"},
            "params": {"window": 3, "min_periods": 2},
            "on": positive,
        }
    )
    combined = _direct(
        "multiary.add",
        {"cols": ["mean_close", "volume", _direct("unary.get", {"col": "is_st"})]},
    )
    dependencies = factor_query.derivative_factors(
        {"mean_close": mean, "result": combined}
    )
    assert dependencies == {"close", "volume", "is_st"}


class QuerySession:
    """根据 SQL 类别返回预设查询表。"""

    def __init__(
        self,
        *,
        current: pd.DataFrame | None = None,
        baseline: pd.DataFrame | None = None,
        universe: pd.DataFrame | None = None,
    ):
        self.current = current
        self.baseline = baseline
        self.universe = universe
        self.uploads: list[dict[str, Any]] = []
        self.scripts: list[str] = []
        self.closed = False

    def upload(self, values: dict[str, Any]) -> None:
        """记录上传参数。"""
        self.uploads.append(values)

    def run(self, script: str):
        """按当前值、基准值或行宇宙查询返回数据。"""
        self.scripts.append(script)
        if "select distinct time" in script:
            if self.universe is None:
                return None
            return self.universe[["time"]].drop_duplicates()
        if "select distinct code" in script:
            if self.universe is None:
                return None
            return self.universe[["code"]].drop_duplicates()
        if "time < coreQueryStart" in script:
            return self.baseline
        if "select time, code, factor, value" in script:
            return self.current
        return None

    def close(self) -> None:
        """记录关闭。"""
        self.closed = True


def _long(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    """构造统一四列长表测试数据。"""
    return pd.DataFrame(rows, columns=factor_query.LONG_COLUMNS).assign(
        time=lambda frame: pd.to_datetime(frame["time"])
    )


def test_fetch_query_parts_queries_current_baseline_and_anchor() -> None:
    """显式股票共享全市场交易日，只有财报因子查询区间前基准。"""
    current = _long([("2024-01-02", "A", "close", 11.0)])
    baseline = _long([("2024-01-01", "A", "total_assets", 10.0)])
    universe = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["A", "B"],
        }
    )
    session = QuerySession(current=current, baseline=baseline, universe=universe)
    parts = factor_query.fetch_query_parts(
        session,
        start=pd.Timestamp("2024-01-02"),
        output_start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-04"),
        codes=["A"],
        factors=["close", "total_assets", "is_st", "weight_000300SH"],
    )
    assert parts[0].equals(current) and parts[1].equals(baseline)
    assert parts[2].to_dict("records") == [
        {"time": pd.Timestamp("2024-01-02"), "code": "A"},
        {"time": pd.Timestamp("2024-01-03"), "code": "A"},
    ]
    uploaded = {key for values in session.uploads for key in values}
    assert {
        "coreQueryCodes",
        "coreQueryOutputStart",
        "coreQueryEndExclusive",
        "coreQueryFactors",
        "coreQueryCarryFactors",
        "coreQueryAnchorFactors",
    } <= uploaded
    baseline_upload = next(
        values["coreQueryCarryFactors"]
        for values in session.uploads
        if "coreQueryCarryFactors" in values
    )
    assert baseline_upload.tolist() == ["total_assets"]


def test_fetch_query_parts_handles_no_factors_all_codes_and_null_responses() -> None:
    """常量 DSL 不查询值或基准，全股票空 anchor 响应规范为空表。"""
    session = QuerySession(universe=None)
    current, baseline, universe = factor_query.fetch_query_parts(
        session,
        start=pd.Timestamp("2024-01-02"),
        output_start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-04"),
        codes=None,
        factors=[],
    )
    assert current.empty and baseline.empty and universe.empty
    assert len(session.scripts) == 1
    assert not any("coreQueryCodes" in values for values in session.uploads)


def test_fetch_query_parts_expands_every_stock_to_every_trading_date() -> None:
    """全股票查询把各股票零散行情日期扩展为统一的完整交易日日历。"""
    session = QuerySession(
        universe=pd.DataFrame(
            {
                "time": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "code": ["A", "B"],
            }
        )
    )

    _, _, calendar = factor_query.fetch_query_parts(
        session,
        start=pd.Timestamp("2024-01-02"),
        output_start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-03"),
        codes=None,
        factors=[],
    )

    assert calendar.to_dict("records") == [
        {"time": pd.Timestamp("2024-01-02"), "code": "A"},
        {"time": pd.Timestamp("2024-01-03"), "code": "A"},
        {"time": pd.Timestamp("2024-01-02"), "code": "B"},
        {"time": pd.Timestamp("2024-01-03"), "code": "B"},
    ]


def test_fetch_query_parts_handles_empty_automatic_code_scope() -> None:
    """计算区间有交易日但输出区间没有股票时直接返回空结果。"""
    class EmptyCodeSession(QuerySession):
        """只在自动股票范围查询中返回空表。"""

        def run(self, script: str):
            """保留交易日响应，并模拟输出区间没有股票。"""
            if "select distinct code" in script:
                self.scripts.append(script)
                return pd.DataFrame({"code": pd.Series(dtype="object")})
            return super().run(script)

    session = EmptyCodeSession(
        universe=pd.DataFrame(
            {
                "time": pd.to_datetime(["2024-01-01"]),
                "code": ["A"],
            }
        )
    )
    current, baseline, calendar = factor_query.fetch_query_parts(
        session,
        start=pd.Timestamp("2024-01-01"),
        output_start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-03"),
        codes=None,
        factors=["close"],
    )
    assert current.empty and baseline.empty and calendar.empty
    assert not any("coreQueryCodes" in values for values in session.uploads)


def test_fetch_query_parts_skips_baseline_for_exact_daily_factors() -> None:
    """行情、ST 和 weight_* 都不能继承开始日前的值。"""
    session = QuerySession(
        current=None,
        universe=pd.DataFrame(
            {"time": pd.to_datetime(["2024-01-02"]), "code": ["A"]}
        ),
    )
    current, baseline, _ = factor_query.fetch_query_parts(
        session,
        start=pd.Timestamp("2024-01-02"),
        output_start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-04"),
        codes=["A"],
        factors=["close", "is_st", "weight_000300SH"],
    )
    assert current.empty and baseline.empty
    assert not any("coreQueryCarryFactors" in values for values in session.uploads)


def test_build_source_fills_exact_and_carries_regular_factors() -> None:
    """价格不填、财报前填、ST/权重补零，未知 factor 保留 NULL。"""
    baseline = _long(
        [
            ("2024-01-01", "A", "total_assets", 100.0),
            ("2024-01-01", "B", "total_assets", 200.0),
        ]
    )
    current = _long(
        [
            ("2024-01-02", "A", "close", 11.0),
            ("2024-01-03", "A", "is_st", 1.0),
            ("2024-01-02", "A", "weight_000300SH", 5.0),
            ("2024-01-04", "A", "close", 14.0),
        ]
    )
    universe = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"] * 2),
            "code": ["A"] * 3 + ["B"] * 3,
        }
    )
    factors = [
        "close",
        "total_assets",
        "is_st",
        "weight_000300SH",
        "missing",
    ]
    result = factor_query.build_source(
        current,
        baseline,
        universe,
        factors,
        start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-04"),
    )
    assert result["close"].iloc[[0, 2]].tolist() == [11.0, 14.0]
    assert result["close"].iloc[[1, 3, 4, 5]].isna().all()
    assert result["total_assets"].tolist() == [
        100.0,
        100.0,
        100.0,
        200.0,
        200.0,
        200.0,
    ]
    assert result["is_st"].tolist() == [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    assert result["weight_000300SH"].tolist() == [5.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert result["missing"].isna().all()


def test_build_source_applies_weekend_events_on_next_universe_row() -> None:
    """周末财报进入内部填充时间线，但结果只保留周五和下周一行情行。"""
    baseline = _long(
        [("2024-01-04", "A", "total_assets", 100.0)]
    )
    current = _long(
        [("2024-01-06", "A", "total_assets", 200.0)]
    )
    universe = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-05", "2024-01-08"]),
            "code": ["A", "A"],
        }
    )

    result = factor_query.build_source(
        current,
        baseline,
        universe,
        ["total_assets"],
        start=pd.Timestamp("2024-01-05"),
        end=pd.Timestamp("2024-01-08"),
    )

    assert result["time"].tolist() == [
        pd.Timestamp("2024-01-05"),
        pd.Timestamp("2024-01-08"),
    ]
    assert result["total_assets"].tolist() == [100.0, 200.0]


def test_build_source_supports_empty_values_and_empty_universe() -> None:
    """只有 anchor 时生成 NULL 原始列，完全无键时返回稳定空 schema。"""
    universe = pd.DataFrame(
        {"time": pd.to_datetime(["2024-01-02"]), "code": ["A"]}
    )
    with_anchor = factor_query.build_source(
        factor_query.empty_long(),
        factor_query.empty_long(),
        universe,
        ["close", "is_st"],
        start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-02"),
    )
    assert pd.isna(with_anchor.loc[0, "close"])
    assert with_anchor.loc[0, "is_st"] == 0

    empty = factor_query.build_source(
        _long([("2024-01-02", "A", "close", 10.0)]),
        factor_query.empty_long(),
        pd.DataFrame(columns=["time", "code"]),
        ["close"],
        start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-02"),
    )
    assert empty.empty and list(empty.columns) == ["time", "code", "close"]


def test_build_source_with_only_exact_factors_does_not_forward_fill() -> None:
    """只有 ST/指数权重时按日补零，不进入普通因子的前向填充分支。"""
    universe = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["A", "A"],
        }
    )
    current = _long(
        [("2024-01-02", "A", "weight_000300SH", 100.0)]
    )
    result = factor_query.build_source(
        current,
        factor_query.empty_long(),
        universe,
        ["is_st", "weight_000300SH"],
        start=pd.Timestamp("2024-01-02"),
        end=pd.Timestamp("2024-01-03"),
    )
    assert result["is_st"].tolist() == [0.0, 0.0]
    assert result["weight_000300SH"].tolist() == [100.0, 0.0]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            pd.DataFrame(
                {
                    "time": ["2024-01-02"],
                    "code": ["A"],
                    "factor": ["close"],
                    "value": [10.0],
                }
            ),
            "time 列必须为 datetime64",
        ),
        (
            pd.DataFrame(
                {
                    "time": pd.to_datetime(["2024-01-02"]),
                    "code": ["A"],
                    "factor": ["close"],
                    "value": ["10"],
                }
            ),
            "value 列必须为 float",
        ),
    ],
)
def test_check_long_rejects_invalid_dtypes(
    data: pd.DataFrame,
    message: str,
) -> None:
    """最新写入契约之外的长表 dtype 在查询边界直接报错。"""
    with pytest.raises(ValueError, match=message):
        factor_query.check_long(data, "测试数据")


def test_check_universe_rejects_invalid_time_dtype() -> None:
    """行情锚点 time 不是 datetime64 时报告数据契约错误。"""
    universe = pd.DataFrame({"time": ["2024-01-02"], "code": ["A"]})
    with pytest.raises(ValueError, match="交易日日历的 time 列必须为 datetime64"):
        factor_query.check_universe(universe)


def test_select_columns_normalizes_none_and_column_order() -> None:
    """空响应和乱序表均返回统一四列契约。"""
    assert factor_query.select_columns(
        None,
        factor_query.LONG_COLUMNS,
        "测试查询",
    ).empty
    value = pd.DataFrame(
        {
            "value": [1.0],
            "factor": ["x"],
            "code": ["A"],
            "time": [pd.Timestamp("2024-01-01")],
        }
    )
    result = factor_query.select_columns(
        value,
        factor_query.LONG_COLUMNS,
        "测试查询",
    )
    assert list(result.columns) == list(factor_query.LONG_COLUMNS)

    exact = _long([("2024-01-01", "A", "x", 1.0)])
    assert factor_query.select_columns(
        exact,
        factor_query.LONG_COLUMNS,
        "测试查询",
    ) is exact


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "必须返回 DataFrame"),
        (pd.DataFrame({"time": []}), "返回结果缺少列"),
    ],
)
def test_select_columns_rejects_invalid_database_responses(
    value: object,
    message: str,
) -> None:
    """数据库返回错误类型或缺列时在查询边界报告明确上下文。"""
    with pytest.raises((TypeError, ValueError), match=message):
        factor_query.select_columns(
            value,
            factor_query.LONG_COLUMNS,
            "测试查询",
        )


def test_query_source_uses_borrowed_and_owned_sessions(monkeypatch) -> None:
    """query_source 传递内部依赖，借用会话不关闭，自建会话会关闭。"""
    universe = pd.DataFrame(
        {"time": pd.to_datetime(["2024-01-02"]), "code": ["A"]}
    )
    borrowed = QuerySession(current=None, baseline=None, universe=universe)
    result = factor_query.query_source(
        _valid_request(),
        session=borrowed,
        required_factors=["volume"],
    )
    assert list(result.columns) == ["time", "code", "close", "volume"]
    assert result["code"].tolist() == ["A", "B"]
    assert not borrowed.closed

    owned = QuerySession(current=None, baseline=None, universe=universe)
    monkeypatch.setattr(factor_query, "create_session", lambda: owned)
    factor_query.query_source(_valid_request())
    assert owned.closed

    with pytest.raises(ValueError, match="required_factors 不能使用保留名称"):
        factor_query.query_source(
            _valid_request(),
            session=borrowed,
            required_factors=["time"],
        )


def test_query_source_loads_lookback_before_output_start() -> None:
    """lookback 扩展 source 起点，同时保留原始输出起点供股票范围查询。"""
    universe = pd.DataFrame(
        {
            "time": pd.to_datetime(["2023-12-31", "2024-01-02"]),
            "code": ["A", "A"],
        }
    )
    session = QuerySession(
        current=_long(
            [
                ("2023-12-31", "A", "close", 9.0),
                ("2024-01-02", "A", "close", 10.0),
            ]
        ),
        universe=universe,
    )

    result = factor_query.query_source(
        _valid_request(codes=["A"], lookback="2D"),
        session=session,
    )

    assert result["time"].tolist() == [
        pd.Timestamp("2023-12-31"),
        pd.Timestamp("2024-01-02"),
    ]
    uploaded = session.uploads[0]
    assert uploaded["coreQueryStart"] == pd.Timestamp("2023-12-31")
    assert uploaded["coreQueryOutputStart"] == pd.Timestamp("2024-01-02")


class DslSession(QuerySession):
    """在最终 compute_factors 调用时用 Python 构造同形状结果。"""

    def run(self, script: str):
        """模拟加载脚本及命名派生列计算。"""
        self.scripts.append(script)
        if "compute_factors(coreDslSource" in script:
            upload = next(
                values for values in self.uploads if "coreDslSource" in values
            )
            result = upload["coreDslSource"].copy()
            result["double_close"] = result["close"] * 2
            return result
        if script.startswith("use ta"):
            return None
        return super().run(script)


class ResultDslSession(QuerySession):
    """返回指定 DSL 结果，用于验证执行边界。"""

    def __init__(self, computed: object) -> None:
        super().__init__()
        self.computed = computed

    def run(self, script: str):
        """加载脚本时返回空，计算时返回测试指定对象。"""
        self.scripts.append(script)
        if "compute_factors(coreDslSource" in script:
            return self.computed
        return None


def test_execute_query_runs_validated_definitions_in_same_session(monkeypatch) -> None:
    """DSL 依赖加入内部 source，JSON 上传后返回时只保留请求输出。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["A", "A"],
            "close": [10.0, 11.0],
            "volume": [100.0, 120.0],
        }
    )
    session = DslSession()
    captured: list[list[str]] = []

    def fake_source(request, *, session, required_factors):
        captured.append(required_factors)
        return source

    monkeypatch.setattr(factor_query, "query_source", fake_source)
    request = _valid_request(
        derivatives={
            "double_close": _direct("binary.mul", {"left": "close", "right": 2})
        }
    )
    result = factor_query.execute_query(request, session=session)
    assert result["double_close"].tolist() == [20.0, 22.0]
    assert list(result.columns) == ["time", "code", "close", "double_close"]
    assert captured == [["close"]]
    definitions_json = next(
        values["coreDslDefinitionsJson"]
        for values in session.uploads
        if "coreDslDefinitionsJson" in values
    )
    assert json.loads(definitions_json)["double_close"]["op"] == "binary.mul"


@pytest.mark.parametrize(
    ("computed", "message"),
    [
        (None, "必须返回 DataFrame"),
        (
            pd.DataFrame(
                {
                    "time": pd.to_datetime(["2024-01-02"]),
                    "code": ["A"],
                    "close": [10.0],
                }
            ),
            "缺少输出列",
        ),
        (
            pd.DataFrame(
                {
                    "time": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                    "code": ["A", "A"],
                    "close": [10.0, 11.0],
                    "double_close": [20.0, 22.0],
                }
            ),
            "改变了行数",
        ),
    ],
)
def test_execute_query_rejects_invalid_dsl_results(
    monkeypatch,
    computed: object,
    message: str,
) -> None:
    """DSL 返回 None、缺列或改变行数时不能把损坏结果交给调用方。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02"]),
            "code": ["A"],
            "close": [10.0],
        }
    )
    monkeypatch.setattr(
        factor_query,
        "query_source",
        lambda *args, **kwargs: source,
    )
    request = _valid_request(
        derivatives={
            "double_close": _direct(
                "binary.mul",
                {"left": "close", "right": 2},
            )
        }
    )

    with pytest.raises((TypeError, RuntimeError), match=message):
        factor_query.execute_query(
            request,
            session=ResultDslSession(computed),
        )


def test_execute_query_reads_real_long_table_and_feeds_dsl(
    monkeypatch,
    ddb_session,
) -> None:
    """真实 DolphinDB 查询完成稀疏填充，再把宽表直接交给 DSL。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-01",
                    "2024-01-01",
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-03",
                    "2024-01-03",
                    "2024-01-03",
                ]
            ),
            "code": [
                "A",
                "B",
                "A",
                "B",
                "A",
                "B",
                "A",
                "A",
                "B",
                "A",
            ],
            "factor": [
                "pb",
                "pb",
                "total_assets",
                "total_assets",
                "close",
                "close",
                "close",
                "pb",
                "close",
                "is_st",
            ],
            "value": [
                1.5,
                2.5,
                100.0,
                200.0,
                11.0,
                21.0,
                12.0,
                1.6,
                22.0,
                1.0,
            ],
        }
    )
    ddb_session.upload({"coreQueryFixtureRaw": source})
    ddb_session.run(
        """
coreQueryFixture = select
    time,
    symbol(code) as code,
    symbol(factor) as factor,
    value
from coreQueryFixtureRaw
"""
    )
    monkeypatch.setattr(factor_query, "CORE_TABLE", "coreQueryFixture")

    result = factor_query.execute_query(
        _valid_request(
            codes=None,
            factors=["pb", "total_assets", "is_st"],
            derivatives={
                "double_assets": _direct(
                    "binary.mul", {"left": "total_assets", "right": 2}
                )
            },
        ),
        session=ddb_session,
    )

    columns = ["code", "total_assets", "is_st", "double_assets"]
    assert result[columns].to_dict("records") == [
        {
            "code": "A",
            "total_assets": 100.0,
            "is_st": 0.0,
            "double_assets": 200.0,
        },
        {
            "code": "A",
            "total_assets": 100.0,
            "is_st": 1.0,
            "double_assets": 200.0,
        },
        {
            "code": "B",
            "total_assets": 200.0,
            "is_st": 0.0,
            "double_assets": 400.0,
        },
        {
            "code": "B",
            "total_assets": 200.0,
            "is_st": 0.0,
            "double_assets": 400.0,
        },
    ]
    assert result["pb"].iloc[1] == 1.6
    assert result["pb"].iloc[[0, 2, 3]].isna().all()


def test_execute_query_uses_lookback_for_first_ts_value(
    monkeypatch,
    ddb_session,
) -> None:
    """真实 DolphinDB TS 使用预热数据计算首个输出日，返回时移除预热行。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03"]
            ),
            "code": ["A", "A", "A"],
            "factor": ["close", "close", "close"],
            "value": [10.0, 11.0, 12.0],
        }
    )
    ddb_session.upload({"coreQueryLookbackRaw": source})
    ddb_session.run(
        """
coreQueryLookback = select
    time,
    symbol(code) as code,
    symbol(factor) as factor,
    value
from coreQueryLookbackRaw
"""
    )
    monkeypatch.setattr(factor_query, "CORE_TABLE", "coreQueryLookback")
    change = Derivative.model_validate(
        {
            "type": "TS",
            "op": "unary.pct_change",
            "fields": {"col": "close"},
            "params": {"periods": 1},
            "on": _direct("unary.not_null", {"col": "close"}),
        }
    )
    request = _valid_request(
        start_date="2024-01-02",
        end_date="2024-01-03",
        codes=["A"],
        factors=[],
        derivatives={"change": change},
    )

    cold = factor_query.execute_query(request, session=ddb_session)
    warm = factor_query.execute_query(
        {**request, "lookback": "1D"},
        session=ddb_session,
    )

    assert cold["time"].tolist() == pd.to_datetime(
        ["2024-01-02", "2024-01-03"]
    ).tolist()
    assert pd.isna(cold["change"].iloc[0])
    np.testing.assert_allclose(cold["change"].iloc[1], 12 / 11 - 1)
    assert warm["time"].tolist() == cold["time"].tolist()
    np.testing.assert_allclose(warm["change"], [0.1, 12 / 11 - 1])


def test_execute_query_handles_empty_and_raw_only_results(monkeypatch) -> None:
    """空 source 不调用 DSL，无派生因子直接返回请求原始列。"""
    session = QuerySession()
    monkeypatch.setattr(
        factor_query,
        "query_source",
        lambda *args, **kwargs: pd.DataFrame(columns=["time", "code", "close"]),
    )
    empty = factor_query.execute_query(_valid_request(), session=session)
    assert empty.empty and list(empty.columns) == ["time", "code", "close"]

    raw = pd.DataFrame(
        {"time": pd.to_datetime(["2024-01-02"]), "code": ["A"], "close": [1.0]}
    )
    monkeypatch.setattr(factor_query, "query_source", lambda *args, **kwargs: raw)
    result = factor_query.execute_query(_valid_request(), session=session)
    assert result.equals(raw)


def test_execute_query_closes_owned_session(monkeypatch) -> None:
    """execute_query 创建的会话在空结果分支也会关闭。"""
    session = QuerySession()
    monkeypatch.setattr(factor_query, "create_session", lambda: session)
    monkeypatch.setattr(
        factor_query,
        "query_source",
        lambda *args, **kwargs: pd.DataFrame(columns=["time", "code", "close"]),
    )
    factor_query.execute_query(_valid_request())
    assert session.closed


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (None, []),
        (pd.DataFrame(columns=["factor"]), []),
        (pd.DataFrame({"factor": ["close", "is_st"]}), ["close", "is_st"]),
    ],
)
def test_available_factors_normalizes_database_responses(
    monkeypatch,
    result: pd.DataFrame | None,
    expected: list[str],
) -> None:
    """factor 元数据支持空库和有值结果，并关闭自建会话。"""
    session = QuerySession()
    session.run = lambda script: result
    monkeypatch.setattr(factor_query, "create_session", lambda: session)
    assert factor_query.available_factors() == expected
    assert session.closed


def test_available_factors_does_not_close_borrowed_session() -> None:
    """借用会话的所有权仍由调用方持有。"""
    session = QuerySession()
    session.run = lambda script: pd.DataFrame({"factor": ["close"]})
    assert factor_query.available_factors(session=session) == ["close"]
    assert not session.closed


@pytest.mark.parametrize(
    ("result", "error", "message"),
    [
        ([], TypeError, "必须返回 DataFrame"),
        (pd.DataFrame({"name": ["close"]}), ValueError, "缺少列"),
    ],
)
def test_available_factors_rejects_invalid_database_responses(
    result: object,
    error: type[Exception],
    message: str,
) -> None:
    """factor 元数据返回错误类型或缺列时给出明确错误。"""
    session = QuerySession()
    session.run = lambda script: result
    with pytest.raises(error, match=message):
        factor_query.available_factors(session=session)
