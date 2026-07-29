"""按股票增量维护 Backtest 分红送股宽表。"""

from typing import Any

import pandas as pd

from core.database import (
    STOCK_DIVIDEND_COLUMNS,
    STOCK_DIVIDEND_EMPTY,
    STOCK_DIVIDEND_TABLE,
    ensure_stock_dividend_table,
    normalize_stock_dividends,
)
from core.utils import logger, pro

from .base import WideWorker


class StockDividendWorker(WideWorker):
    """通过 dividend 接口更新已实施的股票分红送股记录。"""

    SOURCE_COLUMNS = (
        "ts_code",
        "end_date",
        "ann_date",
        "div_proc",
        "stk_bo_rate",
        "stk_co_rate",
        "cash_div",
        "cash_div_tax",
        "record_date",
        "ex_date",
        "pay_date",
        "div_listdate",
        "imp_ann_date",
    )
    COLUMNS = STOCK_DIVIDEND_COLUMNS
    EMPTY = STOCK_DIVIDEND_EMPTY
    KEY_COLUMN = "symbol"
    DATE_COLUMN = "recordDate"
    TABLE = STOCK_DIVIDEND_TABLE

    def __str__(self) -> str:
        """返回股票分红 Worker 标识。"""
        return "<StockDividendWorker>"

    def ensure_table(self, session: Any) -> None:
        """确保 Backtest 股票分红维度表存在。"""
        ensure_stock_dividend_table(session)

    def fetch_one(
            self,
            code: str,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取并清洗一只股票在股权登记日区间内的已实施分红。"""
        response = self.retry(
            lambda: pro.dividend(
                ts_code=code,
                fields=",".join(self.SOURCE_COLUMNS),
            ),
            context=f"{self}[{code}]",
        )
        if response is None or response.empty:
            return self.EMPTY
        if not isinstance(response, pd.DataFrame):
            raise TypeError(f"{self}[{code}] 返回值不是 DataFrame")

        if missing := set(self.SOURCE_COLUMNS) - set(response.columns):
            raise ValueError(
                f"{self}[{code}] 返回结果缺少列：{sorted(missing)}"
            )

        data = response.loc[
            response["div_proc"].eq("实施"),
            [
                column
                for column in self.SOURCE_COLUMNS
                if column != "div_proc"
            ],
        ].copy()
        if data.empty:
            return self.EMPTY

        required_dates = data[
            ["end_date", "record_date", "ex_date"]
        ].apply(pd.to_datetime, errors="coerce")
        valid = required_dates.notna().all(axis=1)
        if ignored := int((~valid).sum()):
            logger.warning(f"{self}[{code}] 忽略 {ignored} 条日期不完整的分红记录")
            data = data.loc[valid].copy()
        if data.empty:
            return self.EMPTY

        bonus = pd.to_numeric(data["stk_bo_rate"], errors="coerce").fillna(0)
        conversion = pd.to_numeric(
            data["stk_co_rate"],
            errors="coerce",
        ).fillna(0)
        before_tax = pd.to_numeric(
            data["cash_div_tax"],
            errors="coerce",
        )
        reported_after_tax = pd.to_numeric(
            data["cash_div"],
            errors="coerce",
        )
        after_tax = before_tax.mul(0.8).where(
            before_tax.notna(),
            reported_after_tax.fillna(0),
        )
        data = data.rename(
            columns={
                "ts_code": "symbol",
                "end_date": "endDate",
                "ann_date": "annDate",
                "record_date": "recordDate",
                "ex_date": "exDate",
                "pay_date": "payDate",
                "div_listdate": "divListDate",
                "imp_ann_date": "impAnnDate",
            }
        )
        data["bonusRatio"] = bonus
        data["capitalConversion"] = conversion
        data["afterTaxCashDiv"] = after_tax
        data["allotPrice"] = 0.0
        data["allotRatio"] = 0.0
        if data[
            [
                "bonusRatio",
                "capitalConversion",
                "afterTaxCashDiv",
            ]
        ].lt(0).any().any():
            raise ValueError(f"{self}[{code}] 返回了负数分红或送转比例")

        result = normalize_stock_dividends(
            data.loc[:, list(self.COLUMNS)]
        )
        result = result[
            result["recordDate"].between(start_date, end_date)
        ]
        result = result[
            result[
                [
                    "bonusRatio",
                    "capitalConversion",
                    "afterTaxCashDiv",
                ]
            ].ne(0).any(axis=1)
        ]
        return result.reset_index(drop=True)
