"""独立滚动选池方法的统一 Python 入口。"""

from pathlib import Path
from typing import Any

from core.database import create_session
from research.rolling_common import (
    END_DATE,
    EVALUATION_COUNT,
    RANDOM_SEED,
    START_DATE,
    UNIVERSE_CODES,
    RollingResult,
    Selector,
    run_rolling_method,
    save_result,
)


def run_method(
    session: Any,
    method: str,
    selector: Selector,
    *,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
    load_data: bool = True,
) -> RollingResult:
    """用统一参数运行指定选池方法。"""
    return run_rolling_method(
        session,
        method,
        selector,
        start_date=start_date,
        end_date=end_date,
        evaluation_count=evaluation_count,
        random_seed=random_seed,
        universe_codes=UNIVERSE_CODES,
        load_data=load_data,
    )


def run_and_save(
    method: str,
    selector: Selector,
    output_directory: Path,
) -> None:
    """建立会话，运行指定方法并保存默认结果。"""
    session = create_session()
    try:
        result = run_method(session, method, selector)
    finally:
        session.close()
    save_result(result, output_directory)
    print("overall_performance:", result.performance)


__all__ = ["run_and_save", "run_method"]
