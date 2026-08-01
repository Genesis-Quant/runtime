"""纯规范化工具，以及按需加载的运行期工具。"""

from importlib import import_module
from typing import Any

from .normalize import DateLike, normalize_date, normalize_date_range, normalize_str, normalize_str_list, validate_iso_date
from .schema import CODE_COLUMN, CORE_COLUMNS, FACTOR_COLUMN, IS_ST_FACTOR, TIME_COLUMN, VALUE_COLUMN, WEIGHT_PREFIX, index_weight_factor, normalize_factors
from .validation import normalize_dolphindb_functions, validate_dolphindb_callback_signature, validate_dolphindb_identifier, validate_dolphindb_references

LAZY_EXPORTS = {
    "logger": ("core.utils.logging", "logger"),
    "Paginator": ("core.utils.paginate", "Paginator"),
    "SessionResult": ("core.utils.result", "SessionResult"),
    "RateLimiter": ("core.utils.throttle", "RateLimiter"),
    "Retry": ("core.utils.retry", "Retry"),
    "INDUSTRY_TO_SECTOR": ("core.utils.ts_api", "INDUSTRY_TO_SECTOR"),
    "get_codes": ("core.utils.ts_api", "get_codes"),
    "get_pro": ("core.utils.ts_api", "get_pro"),
    "get_stock_metadata": ("core.utils.ts_api", "get_stock_metadata"),
    "get_trading_dates": ("core.utils.ts_api", "get_trading_dates"),
    "pro": ("core.utils.ts_api", "pro"),
    "ts": ("core.utils.ts_api", "ts"),
    "CODES": ("core.utils.ts_api", "CODES"),
    "CODE_TO_INDUSTRY": ("core.utils.ts_api", "CODE_TO_INDUSTRY"),
    "STOCK_INDUSTRIES": ("core.utils.ts_api", "STOCK_INDUSTRIES"),
}


def __getattr__(name: str) -> Any:
    if name not in LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
