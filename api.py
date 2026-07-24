"""创建 Core Factor API 并挂载查询与 Playground 路由。"""

from fastapi import FastAPI

from core.backtest import backtest_router
from core.playground import playground_router
from core.query import query_router

app = FastAPI(
    title="Core Factor API",
    description="查询统一因子数据，并以 Parquet 文件返回结果。",
    version="0.1.0",
)
app.include_router(query_router)
app.include_router(backtest_router)
app.include_router(playground_router)

__all__ = ["app"]
