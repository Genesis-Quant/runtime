"""binary.expanding_cov 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    MASK_PAIR_EXPANDING_RESULT,
)

from core.operators.base import TimeSeriesOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesBinaryExpandingCovParams(StrictModel):
    """binary.expanding_cov 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")


class TimeSeriesBinaryExpandingCovOperator(TimeSeriesOperator):
    """按股票执行 expanding_cov。"""

    op: Literal['binary.expanding_cov'] = Field(..., description='按股票执行 expanding_cov。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryExpandingCovParams = Field(
        default_factory=TimeSeriesBinaryExpandingCovParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_binary_expanding_cov(left, right, min_periods) {
            /*
            计算截至当前位置两个序列的扩展样本协方差。

            第 i 个结果使用从序列首个观测到第 i 个观测的全部历史。累计有效观测数小于 min_periods 时返回 NULL。

            Parameters
            ----------
            left : vector
                左操作数。
            right : vector
                右操作数。
            min_periods : int, default 1
                产生结果所需的累计非 NULL 观测数。未达到该数量的位置返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> left = 1.0 2.5 2.0 4.0 3.5 5.0 4.5 6.0
            >>> right = 1.5 2.0 2.5 3.0 4.0 4.5 5.0 5.5

            min_periods=1：
            >>> ts_binary_expanding_cov(left, right, 1)
            [NULL, 0.375, 0.25, 0.708333, 0.925, 1.5, 1.69643, 2.25]

            min_periods=3：
            >>> ts_binary_expanding_cov(left, right, 3)
            [NULL, NULL, 0.25, 0.708333, 0.925, 1.5, 1.69643, 2.25]

            min_periods=5：
            >>> ts_binary_expanding_cov(left, right, 5)
            [NULL, NULL, NULL, NULL, 0.925, 1.5, 1.69643, 2.25]
            */
            result = cumcovar(left, right)
            return mask_pair_expanding_result(result, left, right, min_periods)
        }
        """,
        dependencies=(MASK_PAIR_EXPANDING_RESULT,)
    )
