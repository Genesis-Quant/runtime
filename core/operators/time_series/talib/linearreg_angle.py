"""talib.linearreg_angle 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibLinearregAngleParams(StrictModel):
    """talib.linearreg_angle 参数。"""

    time_period: int = Field(..., ge=2, description="技术指标观察周期。")


class TimeSeriesTalibLinearregAngleOperator(TimeSeriesOperator):
    """调用 ta::linearreg_angle。"""

    op: Literal['talib.linearreg_angle'] = Field(..., description='调用 ta::linearreg_angle。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibLinearregAngleParams = Field(
        default_factory=TimeSeriesTalibLinearregAngleParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_linearreg_angle(col, time_period) {
            /*
            计算 TA-Lib LINEARREG_ANGLE（滚动线性回归角度）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：对滚动 OLS 斜率取 atan 并转换为角度，表达拟合趋势的倾斜程度。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            time_period=2：
            >>> tail(ts_talib_linearreg_angle(close, 2), 3)
            [26.5651, 16.6992, -11.3099]

            time_period=3：
            >>> tail(ts_talib_linearreg_angle(close, 3), 3)
            [5.71059, 21.8014, 2.86241]

            time_period=5：
            >>> tail(ts_talib_linearreg_angle(close, 5), 3)
            [12.9528, 11.3099, 7.96961]
            */
            return ta::linearreg_angle(col, int(time_period))
        }
        """
    )
