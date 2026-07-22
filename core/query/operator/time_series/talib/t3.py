"""talib.t3 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibT3Params(StrictModel):
    """talib.t3 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")
    vfactor: float = Field(default=0.7, gt=0, le=1, allow_inf_nan=False, description="T3 成交量因子。")


class TimeSeriesTalibT3Operator(TimeSeriesOperator):
    """计算 T3 指标。"""

    op: Literal['talib.t3'] = Field(..., description='计算 T3 指标。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibT3Params = Field(
        default_factory=TimeSeriesTalibT3Params,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_t3(col, time_period, vfactor) {
            /*
            计算 TA-Lib T3（T3 移动平均）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。
            vfactor : float, default 0.7
                T3 平滑因子，取值范围为 [0, 1]；数值越大，对近期观测的响应通常越强。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：对多层 EMA 使用 vfactor 组合，形成低滞后的 Tillson T3 平滑结果。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            vfactor=0.3：
            >>> tail(ts_talib_t3(close, 2, 0.3), 3)
            [11.7202, 11.9904, 12.0867]

            vfactor=0.7：
            >>> tail(ts_talib_t3(close, 2, 0.7), 3)
            [11.8331, 12.1368, 12.1728]

            vfactor=0.9：
            >>> tail(ts_talib_t3(close, 2, 0.9), 3)
            [11.8891, 12.2128, 12.2117]
            */
            return ta::t3(col, int(time_period), vfactor)
        }
        """
    )
