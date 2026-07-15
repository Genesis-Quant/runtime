"""unary.rank_dense 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    CROSS_SECTION_RANK,
)

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryRankDenseParams(StrictModel):
    """unary.rank_dense 参数。"""

    ascending: bool = Field(default=True, description="是否按升序排名。")


class CrossSectionUnaryRankDenseOperator(CrossSectionOperator):
    """按交易日执行 rank_dense。"""

    op: Literal['unary.rank_dense'] = Field(..., description='按交易日执行 rank_dense。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryRankDenseParams = Field(
        default_factory=CrossSectionUnaryRankDenseParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_rank_dense(col, ascending) {
            /*
            计算当前截面的密集排名，并列值使用相同名次且名次不跳号。

            NULL 不参与排名。普通排名从 1 开始；百分位排名位于 (0, 1]；密集排名在并列组之间不跳号。

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

            升序密集排名：
            >>> cs_unary_rank_dense(col, true)
            [1, 2, 2, 3, 4]

            降序密集排名：
            >>> cs_unary_rank_dense(col, false)
            [4, 3, 3, 2, 1]
            */
            return cross_section_rank(col, ascending, "dense", false)
        }
        """,
        dependencies=(CROSS_SECTION_RANK,)
    )
