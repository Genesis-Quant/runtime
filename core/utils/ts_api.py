"""初始化项目唯一的 Tushare 模块和 Pro API。"""

import pandas as pd
import tushare as ts

from config import TUSHARE_TOKEN


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
codes = tuple(dict.fromkeys(value for value in stock_values if value))
if not codes:
    raise RuntimeError("stock_basic 没有返回有效股票代码")
