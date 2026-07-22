"""初始化项目唯一的 Tushare 模块和 Pro API。"""

import pandas as pd
import tushare as ts

from config import TUSHARE_TOKEN
from .dates import DateLike, normalize_date_range
from .logging import logger

if not TUSHARE_TOKEN:
    raise RuntimeError("缺少 TUSHARE_TOKEN，无法初始化 Tushare Pro API")

ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api(TUSHARE_TOKEN)
if pro is None:
    raise RuntimeError("Tushare Pro API 初始化失败")

stock_frames: list[pd.DataFrame] = []
for status in ("L", "D", "P"):
    response = pro.stock_basic(
        exchange="",
        list_status=status,
        fields="ts_code",
    )
    if response is None:
        raise RuntimeError(f"stock_basic[{status}] 返回 None")
    if not isinstance(response, pd.DataFrame):
        raise TypeError(f"stock_basic[{status}] 返回值不是 DataFrame")
    if "ts_code" not in response.columns:
        raise ValueError(
            f"stock_basic[{status}] 返回结果缺少列：['ts_code']"
        )
    if not response.empty:
        stock_frames.append(response.loc[:, ["ts_code"]])

if not stock_frames:
    raise RuntimeError("stock_basic 没有返回任何股票")

stock_values = (
    pd.concat(stock_frames, ignore_index=True)["ts_code"]
    .astype("string")
    .str.strip()
    .dropna()
)
CODES = tuple(dict.fromkeys(value for value in stock_values if value))
if not CODES:
    raise RuntimeError("stock_basic 没有返回有效股票代码")

logger.success(f"Tushare Pro 初始化完成，共加载 {len(CODES):,} 只股票")


def get_trading_dates(
        start_date: DateLike,
        end_date: DateLike,
) -> pd.DatetimeIndex:
    """返回上交所在闭区间内的开放交易日。"""
    start, end = normalize_date_range(start_date, end_date)
    response = pro.trade_cal(
        exchange="SSE",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        is_open="1",
        fields="cal_date,is_open",
    )
    if response is None:
        raise RuntimeError("trade_cal 返回 None")
    if not isinstance(response, pd.DataFrame):
        raise TypeError("trade_cal 返回值必须是 DataFrame")
    required = {"cal_date", "is_open"}
    if missing := required - set(response.columns):
        raise ValueError(f"trade_cal 返回结果缺少列：{sorted(missing)}")
    if response.empty:
        return pd.DatetimeIndex([])

    is_open = pd.to_numeric(response["is_open"], errors="coerce")
    if is_open.isna().any():
        raise ValueError("trade_cal 返回了无效 is_open")
    values = response.loc[is_open.eq(1), "cal_date"]
    dates = pd.to_datetime(values, format="%Y%m%d", errors="coerce")
    if dates.isna().any():
        raise ValueError("trade_cal 返回了无效 cal_date")
    return pd.DatetimeIndex(dates.drop_duplicates().sort_values())


__all__ = ["CODES", "get_trading_dates", "pro", "ts"]
