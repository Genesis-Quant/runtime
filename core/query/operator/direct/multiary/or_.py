"""multiary.or 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import MultiaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryOrParams(StrictModel):
    """multiary.or 不接收参数。"""


class DirectMultiaryOrOperator(DirectOperator):
    """多条件逻辑 or。"""

    op: Literal['multiary.or'] = Field(..., description='多条件逻辑 or。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryOrParams = Field(
        default_factory=DirectMultiaryOrParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_multiary_or(cols) {
            /*
            按位置计算所有布尔操作数的逻辑或。

            计算在每个位置独立进行。数值归约忽略 NULL；某位置没有有效操作数时返回 NULL。

            Parameters
            ----------
            cols : ANY vector
                按位置参与归约的操作数集合；其中的向量长度必须一致。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：逐行逻辑聚合会跳过 NULL；只要存在有效 BOOL 就由有效值决定结果，整行全部为 NULL
            时返回 NULL。

            逻辑边界：非空行使用 false 作为归约初始值。所有输入必须具有 BOOL 语义并在广播后等长。

            Examples
            --------
            >>> first = true true false false
            >>> second = true false true false
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)
            >>> direct_multiary_or(cols)
            [true, true, true, false]

            逐行跳过 NULL，整行缺失才返回 NULL：
            >>> a = bool([true, false]); b = take(bool(NULL), 2)
            >>> direct_multiary_or([a, b])
            [true, false]
            */
            return unifiedCall(rowOr, cols)
        }
        """
    )
