"""数值算符共用的 DolphinDB 函数。"""

from core.dolphindb.function import DolphinDBFunction

from .form import IS_SCALAR_FORM, IS_VECTOR_FORM


IS_FINITE_NUMBER = DolphinDBFunction(
    """
def is_finite_number(value) {
    // 逐元素判断有限数值，同时排除 NULL、NaN 和正负无穷。
    return isValid(value) && !isNanInf(value, true)
}
"""
)

DIVIDE_OR_NULL = DolphinDBFunction(
    """
def divide_or_null(left, right) {
    // 执行安全除法；分母为 0 或 NULL 的位置返回 NULL。
    return iif(isNull(right) || right == 0, NULL, left / right)
}
"""
)

CAST_VALUE = DolphinDBFunction(
    """
def cast_value(value, dtype) {
    // 将标量或向量转换为 DSL 支持的目标类型，并显式解析日期时间字符串。
    if (dtype == "bool") return bool(value)
    if (dtype == "int") return int(value)
    if (dtype == "long") return long(value)
    if (dtype == "float") return float(value)
    if (dtype == "double") return double(value)
    if (dtype == "string") return string(value)
    if (dtype == "symbol") {
        text = string(value)
        if (is_scalar_form(text)) return symbol(enlist(text))[0]
        return symbol(text)
    }
    if (dtype == "date") {
        if (type(value) == STRING) return temporalParse(value, "yyyy-MM-dd")
        return date(value)
    }
    if (dtype == "timestamp") {
        if (type(value) == STRING) {
            sample = value
            if (is_vector_form(value)) sample = value[0]
            if (size(split(sample, ".")) > 1) {
                return timestamp(temporalParse(value, "yyyy-MM-ddTHH:mm:ss.SSS"))
            }
            return timestamp(temporalParse(value, "yyyy-MM-ddTHH:mm:ss"))
        }
        return timestamp(value)
    }
    throw "不支持转换为 dtype=" + string(dtype)
}
""",
    dependencies=(IS_SCALAR_FORM, IS_VECTOR_FORM),
)


__all__ = ["CAST_VALUE", "DIVIDE_OR_NULL", "IS_FINITE_NUMBER"]
