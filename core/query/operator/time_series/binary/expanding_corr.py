"""binary.expanding_corr 算符模型。"""

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


class TimeSeriesBinaryExpandingCorrParams(StrictModel):
    """binary.expanding_corr 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")


class TimeSeriesBinaryExpandingCorrOperator(TimeSeriesOperator):
    """按股票执行 expanding_corr。"""

    op: Literal['binary.expanding_corr'] = Field(..., description='按股票执行 expanding_corr。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryExpandingCorrParams = Field(
        default_factory=TimeSeriesBinaryExpandingCorrParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_binary_expanding_corr(left, right, min_periods) {
            /*
            计算截至当前位置两个序列的扩展 Pearson 相关系数。

            第 i 个结果使用从序列首个观测到第 i 个观测的全部历史。累计有效观测数小于 min_periods 时返回 NULL。

            Parameters
            ----------
            left : vector
                第一条按时间升序排列的数值序列。
            right : vector
                与 left 等长的第二条数值序列。
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
            >>> ts_binary_expanding_corr(left, right, 1)
            [NULL, 1, 0.654654, 0.877876, 0.805682, 0.893633, 0.894054, 0.927625]

            min_periods=3：
            >>> ts_binary_expanding_corr(left, right, 3)
            [NULL, NULL, 0.654654, 0.877876, 0.805682, 0.893633, 0.894054, 0.927625]

            min_periods=5：
            >>> ts_binary_expanding_corr(left, right, 5)
            [NULL, NULL, NULL, NULL, 0.805682, 0.893633, 0.894054, 0.927625]
            */
            result = cumcorr(left, right)
            return mask_pair_expanding_result(result, left, right, min_periods)
        }
        """,
        dependencies=(MASK_PAIR_EXPANDING_RESULT,)
    )
