"""binary.expanding_beta 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    MASK_PAIR_EXPANDING_RESULT,
)

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesBinaryExpandingBetaParams(StrictModel):
    """binary.expanding_beta 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")


class TimeSeriesBinaryExpandingBetaOperator(TimeSeriesOperator):
    """按股票执行 expanding_beta。"""

    op: Literal['binary.expanding_beta'] = Field(..., description='按股票执行 expanding_beta。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryExpandingBetaParams = Field(
        default_factory=TimeSeriesBinaryExpandingBetaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_binary_expanding_beta(left, right, min_periods) {
            /*
            计算截至当前位置以 left 解释 right 的扩展回归斜率。

            第 i 个结果使用从序列首个观测到第 i 个观测的全部历史。累计有效观测数小于 min_periods 时返回 NULL。

            Parameters
            ----------
            left : vector
                回归中的解释变量向量。
            right : vector
                回归中的因变量向量。
            min_periods : int, default 1
                产生结果所需的累计非 NULL 观测数。未达到该数量的位置返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：协方差、相关系数和 beta 只使用两侧同时有效的观测；有效配对不足时结果为 NULL。

            扩展窗口：二元统计始终使用截至当前位置的累计有效配对，不单独填充任一侧。

            Examples
            --------
            >>> left = 1.0 2.5 2.0 4.0 3.5 5.0 4.5 6.0
            >>> right = 1.5 2.0 2.5 3.0 4.0 4.5 5.0 5.5

            min_periods=1：
            >>> ts_binary_expanding_beta(left, right, 1)
            [NULL, 0.333333, 0.428571, 0.453333, 0.649123, 0.714286, 0.818966, 0.819512]

            min_periods=3：
            >>> ts_binary_expanding_beta(left, right, 3)
            [NULL, NULL, 0.428571, 0.453333, 0.649123, 0.714286, 0.818966, 0.819512]

            min_periods=5：
            >>> ts_binary_expanding_beta(left, right, 5)
            [NULL, NULL, NULL, NULL, 0.649123, 0.714286, 0.818966, 0.819512]
            */
            result = cumbeta(right, left)
            return mask_pair_expanding_result(result, left, right, min_periods)
        }
        """,
        dependencies=(MASK_PAIR_EXPANDING_RESULT,)
    )
