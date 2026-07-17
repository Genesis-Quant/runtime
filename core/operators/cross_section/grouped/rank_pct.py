"""grouped.rank_pct 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    CROSS_SECTION_RANK,
)

from core.operators.base import CrossSectionOperator
from core.operators.fields import GroupedFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionGroupedRankPctParams(StrictModel):
    """grouped.rank_pct 参数。"""

    ascending: bool = Field(default=True, description="是否按升序排名。")
    ties_method: Literal["min", "max", "average", "first", "dense"] = Field(
        default="min", description="并列值处理方式。"
    )


class CrossSectionGroupedRankPctOperator(CrossSectionOperator):
    """按交易日和分类键执行 rank_pct。"""

    op: Literal['grouped.rank_pct'] = Field(..., description='按交易日和分类键执行 rank_pct。')
    fields: GroupedFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionGroupedRankPctParams = Field(
        default_factory=CrossSectionGroupedRankPctParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_grouped_rank_pct(col, ascending, ties_method) {
            /*
            在当前分类组内计算百分位排名。

            结果位于 (0, 1]；并列值如何分配百分位由 ties_method 决定。NULL 不参与有效样本排名。

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
            NULL 处理：排名忽略 NULL，缺失输入位置的排名仍为 NULL；百分位分母只包含有效值。

            分组内语义：ascending 和 ties_method 在每组独立应用，百分位分母只计有效值。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            ties_method="min"：
            >>> cs_grouped_rank_pct(col, true, "min")
            [0.2, 0.4, 0.4, 0.8, 1]

            ties_method="max"：
            >>> cs_grouped_rank_pct(col, true, "max")
            [0.2, 0.6, 0.6, 0.8, 1]

            ties_method="average"：
            >>> cs_grouped_rank_pct(col, true, "average")
            [0.2, 0.5, 0.5, 0.8, 1]

            ties_method="first"：
            >>> cs_grouped_rank_pct(col, true, "first")
            [0.2, 0.4, 0.6, 0.8, 1]

            ties_method="dense"：
            >>> cs_grouped_rank_pct(col, true, "dense")
            [0.25, 0.5, 0.5, 0.75, 1]

            降序排名：
            >>> cs_grouped_rank_pct(col, false, "min")
            [1, 0.6, 0.6, 0.4, 0.2]
            */
            return cross_section_rank(col, ascending, ties_method, true)
        }
        """,
        dependencies=(CROSS_SECTION_RANK,)
    )
