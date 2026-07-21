"""把指数权重快照增量展开为成分股日频权重特征。"""

from collections.abc import Iterable
from typing import ClassVar

import numpy as np
import pandas as pd

from config import DATA_START_DATE, INDEX_CODES
from core.database import index_weight_factor
from core.utils import DateLike, normalize_date, pro

from .base import DateWorker


class IndexWeightWorker(DateWorker):
    """抓取指数快照并为每个自然日生成非零成分股权重。"""

    SOURCE_COLUMNS: ClassVar[set[str]] = {
        "trade_date",
        "index_code",
        "con_code",
        "weight",
    }
    def __init__(
        self,
        index_codes: Iterable[str] = INDEX_CODES,
        *,
        start_date: DateLike = DATA_START_DATE,
        throttle: int = 1,
        max_retries: int = 3,
        retry_interval: float = 1.0,
        batch_size: int = 200_000,
    ) -> None:
        """规范指数集合并初始化逐日更新配置。"""
        normalized: list[str] = []
        for value in index_codes:
            code = str(value).strip().upper()
            index_weight_factor(code)
            if code not in normalized:
                normalized.append(code)
        if not normalized:
            raise ValueError("index_codes 不能为空")
        self.index_codes = tuple(normalized)
        super().__init__(
            start_date=start_date,
            throttle=throttle,
            max_retries=max_retries,
            retry_interval=retry_interval,
            batch_size=batch_size,
        )

    @property
    def factors(self) -> tuple[str, ...]:
        """返回配置指数对应的权重因子名。"""
        return tuple(index_weight_factor(code) for code in self.index_codes)

    @classmethod
    def normalize_page(
        cls,
        index_code: str,
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """校验一页指数权重并规范快照日期、指数、股票和权重。"""
        if not isinstance(data, pd.DataFrame):
            raise TypeError(f"index_weight[{index_code}] 返回值不是 DataFrame")
        if data.empty:
            return pd.DataFrame(columns=["time", "index", "code", "weight"])
        if missing := cls.SOURCE_COLUMNS - set(data.columns):
            raise ValueError(
                f"index_weight[{index_code}] 返回结果缺少列：{sorted(missing)}"
            )
        result = data.loc[
            :, ["trade_date", "index_code", "con_code", "weight"]
        ].rename(
            columns={
                "trade_date": "time",
                "index_code": "index",
                "con_code": "code",
            }
        )
        result["time"] = pd.to_datetime(
            result["time"],
            errors="coerce",
        ).dt.normalize()
        result["index"] = (
            result["index"].astype("string").str.strip().str.upper()
        )
        result["code"] = result["code"].astype("string").str.strip()
        result["weight"] = pd.to_numeric(result["weight"], errors="coerce")
        invalid = result.isna().any(axis=1)
        invalid |= result["index"].eq("") | result["code"].eq("")
        invalid |= ~np.isfinite(result["weight"].to_numpy(dtype=float))
        invalid |= result["weight"].lt(0)
        if invalid.any():
            raise ValueError(
                f"index_weight[{index_code}] 返回了 "
                f"{int(invalid.sum())} 行无效数据"
            )
        unexpected = set(result["index"].unique()) - {index_code}
        if unexpected:
            raise ValueError(
                f"index_weight[{index_code}] 返回了其他指数：{sorted(unexpected)}"
            )
        return (
            result.drop_duplicates(["time", "index", "code"], keep="last")
            .sort_values(["time", "code"])
            .reset_index(drop=True)
        )

    def fetch_page(
        self,
        index_code: str,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """请求并校验截止指定日期的一页指数权重快照。"""
        response = pro.index_weight(
            index_code=index_code,
            end_date=end_date.strftime("%Y%m%d"),
        )
        if response is None:
            raise ValueError("index_weight 返回 None")
        return self.normalize_page(index_code, response)

    @classmethod
    def expand_date(
        cls,
        index_code: str,
        current_date: DateLike,
        snapshots: pd.DataFrame,
    ) -> pd.DataFrame:
        """使用当日最近快照生成非零成分股权重。"""
        current = normalize_date(current_date, "current_date")
        available = snapshots[snapshots["time"].le(current)]
        if available.empty:
            return pd.DataFrame(columns=cls.COLUMNS)
        snapshot_date = available["time"].max()
        members = available[
            available["time"].eq(snapshot_date) & available["weight"].gt(0)
        ]
        if members.empty:
            return pd.DataFrame(columns=cls.COLUMNS)
        result = members.loc[:, ["code", "weight"]].copy()
        result["time"] = current
        result["factor"] = index_weight_factor(index_code)
        return (
            result.rename(columns={"weight": "value"})
            .loc[:, list(cls.COLUMNS)]
            .sort_values("code")
            .reset_index(drop=True)
        )

    @classmethod
    def prepare_insert(cls, data: pd.DataFrame) -> pd.DataFrame:
        """校验统一四列表中的指数权重因子和值。"""
        result = super().prepare_insert(data)
        if not result["factor"].astype(str).str.startswith("weight_").all():
            raise ValueError("指数权重 factor 必须以 weight_ 开头")
        result["value"] = pd.to_numeric(result["value"], errors="coerce")
        finite = np.isfinite(result["value"].to_numpy(dtype=float))
        if not finite.all() or result["value"].lt(0).any():
            raise ValueError("指数权重 value 必须是非负有限数")
        return result

    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """获取一个自然日内全部配置指数的非零成分股权重。"""
        current = normalize_date(current_date, "current_date")
        frames: list[pd.DataFrame] = []
        for index_code in self.index_codes:
            snapshots = self.fetch_page(index_code, current)
            if snapshots.empty:
                continue
            if snapshots["time"].gt(current).any():
                raise ValueError(
                    f"index_weight[{index_code}] 返回了 end_date 之后的数据"
                )
            frame = self.expand_date(
                index_code,
                current,
                snapshots,
            )
            if not frame.empty:
                frames.append(frame)
        if not frames:
            return pd.DataFrame(columns=self.COLUMNS)
        return pd.concat(frames, ignore_index=True)


index_weight_worker = IndexWeightWorker()
