"""talib.beta 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import HighLowFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibBetaParams(StrictModel):
    """talib.beta 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibBetaOperator(TimeSeriesOperator):
    """调用 ta::beta。"""

    op: Literal['talib.beta'] = Field(..., description='调用 ta::beta。')
    fields: HighLowFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibBetaParams = Field(
        default_factory=TimeSeriesTalibBetaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_beta(high, low, time_period) {
            /*
            计算 TA-Lib BETA（滚动 beta）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            high : vector
                第一条按时间升序排列的数值序列；参数名沿用 TA 接口。
            low : vector
                与 high 等长的第二条数值序列；参数名沿用 TA 接口。
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

            计算定义：在滚动窗口内计算 covar(left,right) / var(left)，衡量 right 对
            left 的敏感度。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            time_period=2：
            >>> tail(ts_talib_beta(high, low, 2), 3)
            [1.09902, 1.10591, 1.09469]

            time_period=3：
            >>> tail(ts_talib_beta(high, low, 3), 3)
            [1.09917, 1.09849, 1.09757]

            time_period=5：
            >>> tail(ts_talib_beta(high, low, 5), 3)
            [1.10162, 1.10071, 1.09836]
            */
            return ta::beta(high, low, int(time_period))
        }
        """
    )
