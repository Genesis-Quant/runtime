"""数据形态判断共用的 DolphinDB 函数。"""

from core.dolphindb.function import DolphinDBFunction


IS_SCALAR_FORM = DolphinDBFunction(
    """
def is_scalar_form(value) {
    // 判断 value 是否为标量；通过同形态对象比较，避免依赖 DolphinDB 内部 form 编号。
    return form(value) == form(0)
}
"""
)

IS_VECTOR_FORM = DolphinDBFunction(
    """
def is_vector_form(value) {
    // 判断 value 是否为向量；不把矩阵、字典或表误判为一维操作数。
    return form(value) == form(0 1)
}
"""
)

IS_DICTIONARY_FORM = DolphinDBFunction(
    """
def is_dictionary_form(value) {
    // 判断 value 是否为字典，供 JSON 定义和 DSL 节点的结构校验使用。
    return form(value) == form(dict(STRING, ANY))
}
"""
)

IS_TABLE_FORM = DolphinDBFunction(
    """
def is_table_form(value) {
    // 判断 value 是否为表，供派生因子入口校验 source 使用。
    return form(value) == form(table(0 as value))
}
"""
)


__all__ = [
    "IS_DICTIONARY_FORM",
    "IS_SCALAR_FORM",
    "IS_TABLE_FORM",
    "IS_VECTOR_FORM",
]
