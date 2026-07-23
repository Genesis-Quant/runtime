"""提供查询 Playground 页面及其辅助 HTTP 路由。"""

from datetime import date
import json
from pathlib import Path
from typing import Any, cast, get_args

import pandas as pd
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from config import INDEX_CODES
from core.backtest import run_backtest
from core.query.operator import Derivative
from core.query.schema import FactorQuery
from core.utils import pro
from core.workers import available_factors

from .schema import (
    BacktestRunRequest,
    IndexConstituentsResponse,
    IndexPreset,
    OperatorSpec,
    ValidationIssue,
    ValidationResponse,
)


INDEX_FILE = Path(__file__).with_name("index.html")
BACKTEST_FILE = Path(__file__).with_name("backtest.html")
SUPPORTED_INDEX_CODES: tuple[str, ...] = tuple(
    str(index_code) for index_code in INDEX_CODES
)
INDEX_NAMES = {
    "000016.SH": "上证50",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
}

router = APIRouter(tags=["playground"])


@router.get("/", include_in_schema=False)
def query_console() -> FileResponse:
    """返回统一因子查询前端。"""
    return FileResponse(INDEX_FILE, media_type="text/html")


@router.get("/backtest", include_in_schema=False)
def backtest_console() -> FileResponse:
    """返回日频策略回测前端。"""
    return FileResponse(BACKTEST_FILE, media_type="text/html")


@router.get("/operators", response_model=list[OperatorSpec])
def list_operators() -> list[OperatorSpec]:
    """返回当前注册的全部 DSL 算符及其严格字段模型。"""
    result: list[OperatorSpec] = []
    for operation, model in sorted(Derivative.operators.items()):
        fields_model = cast(
            type[BaseModel],
            model.model_fields["fields"].annotation,
        )
        params_model = cast(
            type[BaseModel],
            model.model_fields["params"].annotation,
        )
        result.append(
            OperatorSpec(
                type=str(get_args(model.model_fields["type"].annotation)[0]),
                op=operation,
                description=(model.__doc__ or operation).strip(),
                output_kind=model.output_kind,
                fields=fields_model.model_json_schema(),
                params=params_model.model_json_schema(),
            )
        )
    return result


@router.get("/factors", response_model=list[str])
def list_factors() -> list[str]:
    """汇总当前全部 Worker 声明的可查询 factor。"""
    return list(available_factors())


@router.get("/indices", response_model=list[IndexPreset])
def list_indices() -> list[IndexPreset]:
    """返回当前配置允许查询的指数股票池预设。"""
    return [
        IndexPreset(code=code, name=INDEX_NAMES.get(code, code))
        for code in SUPPORTED_INDEX_CODES
    ]


@router.get(
    "/indices/{index_code}/constituents",
    response_model=IndexConstituentsResponse,
)
def index_constituents(index_code: str) -> IndexConstituentsResponse:
    """从 Tushare 返回指定指数最近一期的非零权重成分股。"""
    normalized = index_code.strip().upper()
    if normalized not in SUPPORTED_INDEX_CODES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"不支持指数 {normalized!r}，可选值：{list(SUPPORTED_INDEX_CODES)}"
            ),
        )

    try:
        response = pro.index_weight(
            index_code=normalized,
            end_date=date.today().strftime("%Y%m%d"),
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Tushare index_weight 请求失败：{error}",
        ) from error

    if response is None or not isinstance(response, pd.DataFrame):
        raise HTTPException(
            status_code=502,
            detail="Tushare index_weight 返回值不是 DataFrame",
        )
    required = {"trade_date", "con_code", "weight"}
    if missing := required - set(response.columns):
        raise HTTPException(
            status_code=502,
            detail=f"Tushare index_weight 返回结果缺少列：{sorted(missing)}",
        )
    if response.empty:
        raise HTTPException(
            status_code=404,
            detail=f"指数 {normalized} 没有成分股数据",
        )

    trade_dates = pd.to_datetime(
        response["trade_date"],
        format="%Y%m%d",
        errors="coerce",
    )
    weights = pd.to_numeric(response["weight"], errors="coerce")
    if trade_dates.isna().all():
        raise HTTPException(
            status_code=502,
            detail="Tushare index_weight 返回了无效 trade_date",
        )
    latest = trade_dates.max()
    codes = (
        response.loc[
            trade_dates.eq(latest) & weights.notna() & weights.ne(0),
            "con_code",
        ]
        .astype("string")
        .str.strip()
        .dropna()
    )
    normalized_codes = list(dict.fromkeys(code for code in codes if code))
    if not normalized_codes:
        raise HTTPException(
            status_code=404,
            detail=f"指数 {normalized} 最近一期没有非零权重成分股",
        )
    return IndexConstituentsResponse(
        index_code=normalized,
        trade_date=latest.strftime("%Y-%m-%d"),
        codes=normalized_codes,
    )


@router.post("/validate", response_model=ValidationResponse)
def validate_query(
    payload: dict[str, Any] = Body(
        ...,
        description="待校验的完整查询 JSON。",
    ),
) -> ValidationResponse:
    """执行与查询入口相同的完整模型校验，但不访问数据库。"""
    try:
        FactorQuery.model_validate(payload)
    except ValidationError as error:
        return ValidationResponse(
            valid=False,
            errors=[
                ValidationIssue(
                    location=[
                        item for item in issue["loc"] if isinstance(item, (str, int))
                    ],
                    message=issue["msg"],
                    type=issue["type"],
                )
                for issue in error.errors(include_url=False)
            ],
        )
    return ValidationResponse(valid=True)


def _frame_payload(frame: pd.DataFrame) -> dict[str, Any]:
    """把插件表转换为保留列顺序且兼容浏览器的 JSON 数据。"""
    return {
        "columns": list(frame.columns),
        "rows": json.loads(
            frame.to_json(
                orient="records",
                date_format="iso",
                date_unit="ms",
            )
        ),
    }


@router.post("/backtest/run", response_model=None)
def execute_backtest(request: BacktestRunRequest) -> dict[str, Any]:
    """执行 DSL 日频回测并返回可视化所需的全部标准结果。"""
    try:
        output = run_backtest(
            request.query,
            request.callbacks,
            codes_query=request.codes_query,
            name=request.name,
            config=request.config,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    context = json.loads(
        pd.DataFrame([{"context": output.context}]).to_json(
            orient="records",
            date_format="iso",
            date_unit="ms",
        )
    )[0]["context"]
    return {
        "name": output.name,
        "message_rows": output.message_rows,
        "context": context,
        "trade_details": _frame_payload(output.trade_details),
        "daily_positions": _frame_payload(output.daily_positions),
        "daily_portfolios": _frame_payload(output.daily_portfolios),
        "return_summary": _frame_payload(output.return_summary),
        "daily_trading_statistics": _frame_payload(output.daily_trading_statistics),
        "engine_stat": _frame_payload(output.engine_stat),
    }


__all__ = ["router"]
