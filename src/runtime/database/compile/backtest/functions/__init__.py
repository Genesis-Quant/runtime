"""导出 backtest DolphinDB 模块函数。"""

from .build_backtest_message import BUILD_BACKTEST_MESSAGE
from .data import GET_HISTORY_DATA, GET_LAST_DATA
from .orders import ORDER_TARGET, ORDER_TARGET_VALUE
from .params import GET_PARAMS
from .return_summary import STANDARDIZE_RETURN_SUMMARY
from .run_backtest import RUN_BACKTEST

BACKTEST_FUNCTIONS = (
    GET_PARAMS,
    GET_HISTORY_DATA,
    GET_LAST_DATA,
    ORDER_TARGET,
    ORDER_TARGET_VALUE,
    BUILD_BACKTEST_MESSAGE,
    RUN_BACKTEST,
    STANDARDIZE_RETURN_SUMMARY,
)
