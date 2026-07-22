"""binary.gt 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryGtParams(StrictModel):
    """binary.gt 不接收参数。"""


class DirectBinaryGtOperator(DirectOperator):
    """逐行比较 gt。"""

    op: Literal['binary.gt'] = Field(..., description='逐行比较 gt。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryGtParams = Field(
        default_factory=DirectBinaryGtParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_gt(left, right) {
            /*
            逐元素判断 left 是否大于 right。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            Parameters
            ----------
            left : scalar or vector
                大于比较的左侧操作数。
            right : scalar or vector
                大于比较的右侧操作数。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：任一操作数为 NULL 时结果为 BOOL NULL。需要判断缺失值时请显式使用
            unary.is_null 或 unary.not_null；该规则不会让 NULL 按 DolphinDB 排序最小值参与筛选。

            广播与类型：标量可与向量广播，两个向量必须等长；比较前的类型兼容性由 DolphinDB 判断。

            Examples
            --------
            >>> left = 1.0 2.0 4.0
            >>> right = 3.0 2.0 1.0
            >>> direct_binary_gt(left, right)
            [false, false, true]

            NULL 不参与有序比较：
            >>> direct_binary_gt(int([1, NULL, NULL]), int([0, 1, NULL]))
            [true, NULL, NULL]
            */
            return iif(isNull(left) || isNull(right), bool(NULL), left > right)
        }
        """
    )
