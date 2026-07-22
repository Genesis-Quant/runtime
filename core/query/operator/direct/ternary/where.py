"""ternary.where 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import TernaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectTernaryWhereParams(StrictModel):
    """ternary.where 不接收参数。"""


class DirectTernaryWhereOperator(DirectOperator):
    """根据 BOOL 条件逐行选择值。"""

    op: Literal['ternary.where'] = Field(..., description='根据 BOOL 条件逐行选择值。')
    fields: TernaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectTernaryWhereParams = Field(
        default_factory=DirectTernaryWhereParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_ternary_where(condition, if_true, if_false) {
            /*
            根据 condition 逐元素选择 if_true 或 if_false。

            condition、if_true 和 if_false 按 DolphinDB 广播规则对齐；向量输入必须具有兼容长度。

            Parameters
            ----------
            condition : scalar or vector[BOOL]
                决定逐元素选择分支的布尔条件。
            if_true : scalar or vector
                条件为 true 时使用的值。
            if_false : scalar or vector
                条件为 false 时使用的值。

            Returns
            -------
            result : scalar or vector
                真值和假值分支的公共类型；形状由三个输入广播后确定。

            Notes
            -----
            NULL 处理：condition 为 NULL 时结果为 NULL；condition
            有效时只返回被选中分支的值，被选中分支为 NULL 则结果为 NULL。

            广播与类型：condition、if_true 和 if_false 可按 DolphinDB iif
            规则进行标量广播，两分支会转换到公共结果类型。

            Examples
            --------
            >>> condition = true false true false
            >>> if_true = 1 2 3 4
            >>> if_false = 10 20 30 40
            >>> direct_ternary_where(condition, if_true, if_false)
            [1, 20, 3, 40]

            >>> values = 1 2 3 4

            标量 true 选择完整真分支：
            >>> direct_ternary_where(true, values, 0)
            [1, 2, 3, 4]

            标量 false 选择完整假分支：
            >>> direct_ternary_where(false, values, 0)
            0
            */
            return iif(condition, if_true, if_false)
        }
        """
    )
