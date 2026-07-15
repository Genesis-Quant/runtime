"""unary.expanding_rank_pct 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    MASK_EXPANDING_RESULT,
)

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryExpandingRankPctParams(StrictModel):
    """unary.expanding_rank_pct 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")
    ascending: bool = Field(default=True, description="是否按升序排名。")
    ties_method: Literal["min", "max", "average", "dense"] = Field(
        default="min", description="并列值处理方式。"
    )


class TimeSeriesUnaryExpandingRankPctOperator(TimeSeriesOperator):
    """按股票执行 expanding_rank_pct。"""

    op: Literal['unary.expanding_rank_pct'] = Field(..., description='按股票执行 expanding_rank_pct。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryExpandingRankPctParams = Field(
        default_factory=TimeSeriesUnaryExpandingRankPctParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_expanding_rank_pct(col, min_periods, ascending, ties_method) {
            /*
            计算当前值在截至当前位置样本中的扩展百分位排名。

            第 i 个结果使用从序列首个观测到第 i 个观测的全部历史。累计有效观测数小于 min_periods 时返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            min_periods : int, default 1
                产生结果所需的累计非 NULL 观测数。未达到该数量的位置返回 NULL。
            ascending : bool, default true
                true 时最小值排名最前；false 时最大值排名最前。
            ties_method : {"min", "max", "average", "dense"}, default "min"
                并列值处理方式：
                * "min"：并列组使用该组的最小名次。
                * "max"：并列组使用该组的最大名次。
                * "average"：并列组使用所占名次的平均值。
                * "dense"：类似 "min"，但下一组名次只增加 1。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            ties_method="min"：
            >>> ts_unary_expanding_rank_pct(col, 1, true, "min")
            [1, 1, 1, 0.75, 1, 1, 0.857143, 1]

            ties_method="max"：
            >>> ts_unary_expanding_rank_pct(col, 1, true, "max")
            [1, 1, 1, 0.75, 1, 1, 0.857143, 1]

            ties_method="average"：
            >>> ts_unary_expanding_rank_pct(col, 1, true, "average")
            [1, 1, 1, 0.75, 1, 1, 0.857143, 1]

            ties_method="dense"：
            >>> ts_unary_expanding_rank_pct(col, 1, true, "dense")
            [1, 1, 1, 0.75, 1, 1, 0.857143, 1]

            降序排名：
            >>> ts_unary_expanding_rank_pct(col, 1, false, "min")
            [1, 0.5, 0.333333, 0.5, 0.2, 0.166667, 0.285714, 0.125]
            */
            if (ties_method == "dense") {
                result = cumdenseRank(col, ascending, true, true)
            } else {
                result = cumrank(col, ascending, true, ties_method, true)
            }
            if (!true) result = result + 1
            return mask_expanding_result(result, col, min_periods)
        }
        """,
        dependencies=(MASK_EXPANDING_RESULT,)
    )
