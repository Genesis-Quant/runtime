"""talib.ma 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibMaParams(StrictModel):
    """talib.ma 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")
    ma_type: int = Field(default=0, ge=0, le=8, description="TA-Lib 移动平均类型编号。")


class TimeSeriesTalibMaOperator(TimeSeriesOperator):
    """调用 ta::ma。"""

    op: Literal['talib.ma'] = Field(..., description='调用 ta::ma。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibMaParams = Field(
        default_factory=TimeSeriesTalibMaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_ma(col, time_period, ma_type) {
            /*
            计算 TA-Lib MA（移动平均）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。
            ma_type : int, default 0
                TA-Lib 移动平均类型编号：0=SMA、1=EMA、2=WMA、3=DEMA、4=TEMA、5=TRIMA、6=KAMA、7=MAMA、8=T3。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            SMA，time_period=2：
            >>> tail(ts_talib_ma(close, 2, 0), 3)
            [11.75, 12.15, 12.2]

            SMA，time_period=3：
            >>> tail(ts_talib_ma(close, 3, 0), 3)
            [11.7667, 11.9333, 12.1333]

            SMA，time_period=5：
            >>> tail(ts_talib_ma(close, 5, 0), 3)
            [11.52, 11.8, 11.94]

            EMA，time_period=3：
            >>> tail(ts_talib_ma(close, 3, 1), 3)
            [11.7409, 12.0204, 12.0602]

            WMA，time_period=3：
            >>> tail(ts_talib_ma(close, 3, 2), 3)
            [11.8, 12.0667, 12.15]

            DEMA，time_period=3：
            >>> tail(ts_talib_ma(close, 3, 3), 3)
            [11.9446, 12.2621, 12.2009]

            TEMA，time_period=2：
            >>> tail(ts_talib_ma(close, 2, 4), 3)
            [11.9734, 12.3006, 12.1217]

            TRIMA，time_period=2：
            >>> tail(ts_talib_ma(close, 2, 5), 3)
            [11.75, 12.15, 12.2]

            KAMA，time_period=2：
            >>> tail(ts_talib_ma(close, 2, 6), 3)
            [11.3059, 11.7477, 11.7598]

            T3，time_period=2：
            >>> tail(ts_talib_ma(close, 2, 8), 3)
            [11.9171, 12.2516, 12.23]
            */
            return ta::ma(col, int(time_period), int(ma_type))
        }
        """
    )
