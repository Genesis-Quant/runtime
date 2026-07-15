"""unary.log_return 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryLogReturnParams(StrictModel):
    """unary.log_return 参数。"""

    periods: int = Field(default=1, ge=1, description="在 on=true 序列中的位移期数。")


class TimeSeriesUnaryLogReturnOperator(TimeSeriesOperator):
    """按股票执行 log_return。"""

    op: Literal['unary.log_return'] = Field(..., description='按股票执行 log_return。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryLogReturnParams = Field(
        default_factory=TimeSeriesUnaryLogReturnParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_log_return(col, periods) {
            /*
            计算指定期数的对数收益率。

            periods 按观测条数而不是自然日计数。没有足够历史观测的位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            periods : int, default 1
                向后比较或位移的观测期数，必须至少为 1。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> col = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8

            periods=1：
            >>> ts_unary_log_return(col, 1)
            [NULL, 0.0487902, -0.0289875, 0.0571584, 0.027399, -0.0181823, 0.0448506, 0.0344862]

            periods=2：
            >>> ts_unary_log_return(col, 2)
            [NULL, NULL, 0.0198026, 0.0281709, 0.0845574, 0.00921666, 0.0266682, 0.0793367]

            periods=3：
            >>> ts_unary_log_return(col, 3)
            [NULL, NULL, NULL, 0.076961, 0.0555699, 0.0663751, 0.0540672, 0.0611544]
            */
            return log(col) - move(log(col), int(periods))
        }
        """
    )
