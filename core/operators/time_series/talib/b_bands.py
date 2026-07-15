"""talib.bBands 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibBBandsParams(StrictModel):
    """talib.bBands 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")
    nbdev_up: float = Field(default=2.0, gt=0, allow_inf_nan=False, description="上轨标准差倍数。")
    nbdev_down: float = Field(default=2.0, gt=0, allow_inf_nan=False, description="下轨标准差倍数。")
    ma_type: int = Field(default=0, ge=0, le=8, description="TA-Lib 移动平均类型编号。")
    output: Literal["upper", "middle", "lower"] = Field(default="middle", description="需要返回的单个输出。")


class TimeSeriesTalibBBandsOperator(TimeSeriesOperator):
    """计算布林带并选择单个输出。"""

    op: Literal['talib.bBands'] = Field(..., description='计算布林带并选择单个输出。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibBBandsParams = Field(
        default_factory=TimeSeriesTalibBBandsParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_bBands(col, time_period, nbdev_up, nbdev_down, ma_type, output) {
            /*
            计算 TA-Lib BBANDS（布林带）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            底层指标产生多个向量，output 只选择其中一个返回。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。
            nbdev_up : float, default 2.0
                布林带上轨相对中轨的标准差倍数。
            nbdev_down : float, default 2.0
                布林带下轨相对中轨的标准差倍数。
            ma_type : int, default 0
                TA-Lib 移动平均类型编号：0=SMA、1=EMA、2=WMA、3=DEMA、4=TEMA、5=TRIMA、6=KAMA、7=MAMA、8=T3。
            output : {"upper", "middle", "lower"}, default "middle"
                每次调用只返回一个输出向量：
                * "upper"：上轨。
                * "middle"：中轨移动平均。
                * "lower"：下轨。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            返回 output="upper"：
            >>> tail(ts_talib_bBands(close, 3, 2.0, 2.0, 0, "upper"), 3)
            [12.1776, 12.5933, 12.3828]

            返回 output="middle"：
            >>> tail(ts_talib_bBands(close, 3, 2.0, 2.0, 0, "middle"), 3)
            [11.7667, 11.9333, 12.1333]

            返回 output="lower"：
            >>> tail(ts_talib_bBands(close, 3, 2.0, 2.0, 0, "lower"), 3)
            [11.3557, 11.2734, 11.8839]

            使用 1 倍标准差的上轨：
            >>> tail(ts_talib_bBands(close, 3, 1.0, 1.0, 0, "upper"), 3)
            [11.9721, 12.2633, 12.2581]

            使用 3 倍标准差的下轨：
            >>> tail(ts_talib_bBands(close, 3, 3.0, 3.0, 0, "lower"), 3)
            [11.1502, 10.9434, 11.7592]

            中轨改用 EMA 后返回上轨：
            >>> tail(ts_talib_bBands(close, 3, 2.0, 2.0, 1, "upper"), 3)
            [12.1518, 12.6804, 12.3097]

            中轨改用 WMA：
            >>> tail(ts_talib_bBands(close, 3, 2.0, 2.0, 2, "middle"), 3)
            [11.8, 12.0667, 12.15]
            */
            values = ta::bBands(col, int(time_period), nbdev_up, nbdev_down, int(ma_type))
            if (output == "upper") return values[0]
            if (output == "middle") return values[1]
            return values[2]
        }
        """
    )
