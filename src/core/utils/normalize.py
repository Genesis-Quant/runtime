"""提供数据更新和查询共用的日期标准化。"""

from datetime import date, datetime

import pandas as pd

DateLike = date | datetime | pd.Timestamp | str


def normalize_date(value: DateLike, name: str = "date") -> pd.Timestamp:
    """把日期输入规范为无时区的零点 Timestamp。"""
    try:
        result = pd.Timestamp(value)
    except Exception as error:
        raise ValueError(f"{name} 不是有效日期：{value!r}") from error
    if pd.isna(result):
        raise ValueError(f"{name} 不是有效日期：{value!r}")
    if result.tzinfo is not None:
        result = result.tz_localize(None)
    return result.normalize()


def normalize_date_range(
        start_date: DateLike,
        end_date: DateLike,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """规范闭区间日期并拒绝倒置区间。"""
    start = normalize_date(start_date, "start_date")
    end = normalize_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")
    return start, end


def normalize_str_list(values: list[str], location: str) -> list[str]:
    """清理字符串列表，在保持顺序的同时去重并拒绝空值。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{location} 必须全部是字符串")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{location} 不能包含空值")
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result
