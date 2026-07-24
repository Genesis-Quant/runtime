"""提供回测执行接口。"""

import json
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException

from .api import run_backtest
from .schema import BacktestRunRequest

router = APIRouter(tags=["backtest"])


def frame_payload(frame: pd.DataFrame) -> dict[str, Any]:
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
            utils=request.utils,
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
        "trade_details": frame_payload(output.trade_details),
        "daily_positions": frame_payload(output.daily_positions),
        "daily_portfolios": frame_payload(output.daily_portfolios),
        "return_summary": frame_payload(output.return_summary),
        "daily_trading_statistics": frame_payload(
            output.daily_trading_statistics
        ),
        "engine_stat": frame_payload(output.engine_stat),
    }


__all__ = ["router"]
