"""unary.rank_pct 算符模型。"""

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


class CrossSectionUnaryRankPctParams(StrictModel):
    """unary.rank_pct 参数。"""

    ascending: bool = Field(default=True, description="是否按升序排名。")
    ties_method: Literal["min", "max", "average", "first", "dense"] = Field(
        default="min", description="并列值处理方式。"
    )


class CrossSectionUnaryRankPctOperator(CrossSectionOperator):
    """按交易日执行 rank_pct。"""

    op: Literal['unary.rank_pct'] = Field(..., description='按交易日执行 rank_pct。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryRankPctParams = Field(
        default_factory=CrossSectionUnaryRankPctParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_rank_pct(col, ascending, ties_method) {
            /*
            计算当前截面的百分位排名。

            NULL 不参与排名。普通排名从 1 开始；百分位排名位于 (0, 1]；密集排名在并列组之间不跳号。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            ascending : bool, default true
                true 时最小值排名最前；false 时最大值排名最前。
            ties_method : {"min", "max", "average", "first", "dense"}, default "min"
                并列值处理方式：
                * "min"：并列组使用该组的最小名次。
                * "max"：并列组使用该组的最大名次。
                * "average"：并列组使用所占名次的平均值。
                * "first"：按输入中的出现顺序为并列值分配不同名次。
                * "dense"：类似 "min"，但下一组名次只增加 1。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Notes
            -----
            NULL 处理：排名忽略 NULL，原输入为 NULL 的位置返回 NULL；百分位分母只包含有效值。

            排名语义：返回 (0, 1] 内百分位；ascending 和 ties_method 控制排名。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            ties_method="min"：
            >>> cs_unary_rank_pct(col, true, "min")
            [0.2, 0.4, 0.4, 0.8, 1]

            ties_method="max"：
            >>> cs_unary_rank_pct(col, true, "max")
            [0.2, 0.6, 0.6, 0.8, 1]

            ties_method="average"：
            >>> cs_unary_rank_pct(col, true, "average")
            [0.2, 0.5, 0.5, 0.8, 1]

            ties_method="first"：
            >>> cs_unary_rank_pct(col, true, "first")
            [0.2, 0.4, 0.6, 0.8, 1]

            ties_method="dense"：
            >>> cs_unary_rank_pct(col, true, "dense")
            [0.25, 0.5, 0.5, 0.75, 1]

            降序排名：
            >>> cs_unary_rank_pct(col, false, "min")
            [1, 0.6, 0.6, 0.4, 0.2]
            */
            return cross_section_rank(col, ascending, ties_method, true)
        }
        """,
        dependencies=(CROSS_SECTION_RANK,)
    )
