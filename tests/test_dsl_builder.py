"""Tests for the named Python facade over existing DSL models."""

import pytest

from runtime.apps.query.dsl import CS, DIRECT, TS, DslBuildError


def test_named_operations_reuse_names_as_dependencies() -> None:
    spread = DIRECT.sub("spread", left="close", right="open")
    mean = TS.rolling_mean("mean", col=spread, window=20)
    rank = CS.rank_pct("rank", col=mean)

    assert spread.derivative.op == "binary.sub"
    assert mean.derivative.fields.col == "spread"
    assert mean.dependencies == (spread,)
    assert rank.derivative.fields.col == "mean"
    assert rank.dependencies == (mean,)


def test_operator_alias_uses_existing_model_shapes() -> None:
    binary = DIRECT.add("binary", left="open", right="close")
    multiary = DIRECT.add("multiary", cols=["open", "high", "low", "close"])
    grouped = CS.mean("grouped", col="close", by="industry")

    assert binary.derivative.op == "binary.add"
    assert multiary.derivative.op == "multiary.add"
    assert grouped.derivative.op == "grouped.mean"


def test_unnamed_operations_remain_nested() -> None:
    valid_ohlc = DIRECT.and_(
        "valid_ohlc",
        cols=[
            DIRECT.gt(left="close", right=0),
            DIRECT.gt(left="open", right=0),
        ],
    )

    dumped = valid_ohlc.derivative.model_dump(mode="json")
    assert valid_ohlc.dependencies == ()
    assert dumped["fields"]["cols"] == [
        {
            "type": "DIRECT",
            "op": "binary.gt",
            "fields": {"left": "close", "right": 0},
            "params": {},
        },
        {
            "type": "DIRECT",
            "op": "binary.gt",
            "fields": {"left": "open", "right": 0},
            "params": {},
        },
    ]


def test_anonymous_operation_preserves_named_dependencies() -> None:
    pool = DIRECT.gt("pool", left="weight", right=0)
    selected = DIRECT.and_(
        "selected",
        cols=[
            pool,
            DIRECT.gt(left=TS.shift(col="roe", periods=1), right=0),
        ],
    )

    assert selected.dependencies == (pool,)


def test_invalid_operator_arguments_return_existing_schema_errors() -> None:
    with pytest.raises(DslBuildError, match="参数无效"):
        TS.rolling_mean("mean", col="close", window=0)
