"""unary.round 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryRoundParams(StrictModel):
    """unary.round 参数。"""

    precision: int = Field(default=0, ge=0, le=15, description="保留小数位数。")


class DirectUnaryRoundOperator(DirectOperator):
    """逐行四舍五入。"""

    op: Literal['unary.round'] = Field(..., description='逐行四舍五入。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryRoundParams = Field(
        default_factory=DirectUnaryRoundParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_round(col, precision) {
            /*
            逐元素按指定小数位数四舍五入。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。
            precision : int, default 0
                保留的小数位数；0 表示取整。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：NULL 位置保持 NULL。

            数值边界：digits 控制小数位数并使用 DolphinDB round
            的舍入规则；舍入改变数值而不改变向量长度，浮点表示仍可能包含机器精度误差。

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2

            保留 0 位小数：
            >>> direct_unary_round(col, 0)
            [-3, -1, 0, 2, 3]

            保留 1 位小数：
            >>> direct_unary_round(col, 1)
            [-2.5, -1, 0, 1.5, 3.2]

            保留 2 位小数：
            >>> direct_unary_round(col, 2)
            [-2.5, -1, 0, 1.5, 3.2]
            */
            return round(col, int(precision))
        }
        """
    )
