"""unary.rank_normal 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryRankNormalParams(StrictModel):
    """unary.rank_normal 参数。"""

    ascending: bool = Field(default=True, description="是否按升序排名。")


class CrossSectionUnaryRankNormalOperator(CrossSectionOperator):
    """按交易日执行 rank_normal。"""

    op: Literal['unary.rank_normal'] = Field(..., description='按交易日执行 rank_normal。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryRankNormalParams = Field(
        default_factory=CrossSectionUnaryRankNormalParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_rank_normal(col, ascending) {
            /*
            把截面排名映射为标准正态分布分位数。

            先使用平均并列名次计算概率 (rank + 0.5) / n，再通过标准正态分布的逆累积分布函数映射。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            ascending : bool, default true
                true 时最小值排名最前；false 时最大值排名最前。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            升序映射：
            >>> cs_unary_rank_normal(col, true)
            [-1.28155, -0.253347, -0.253347, 0.524401, 1.28155]

            降序映射：
            >>> cs_unary_rank_normal(col, false)
            [1.28155, 0.253347, 0.253347, -0.524401, -1.28155]
            */
            n = count(col)
            probability = (rank(col, ascending, , true, `average, false) + 0.5) / n
            return invNormal(0, 1, probability)
        }
        """
    )
