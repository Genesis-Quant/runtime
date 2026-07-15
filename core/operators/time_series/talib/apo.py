"""talib.apo 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibApoParams(StrictModel):
    """talib.apo 参数。"""

    fast_period: int = Field(default=12, ge=1, description="快线周期。")
    slow_period: int = Field(default=26, ge=2, description="慢线周期。")
    ma_type: int = Field(default=0, ge=0, le=8, description="TA-Lib 移动平均类型编号。")

    @model_validator(mode="after")
    def validate_periods(self) -> "TimeSeriesTalibApoParams":
        """要求快线周期小于慢线周期。"""
        if self.fast_period >= self.slow_period:
            raise ValueError("params.fast_period 必须小于 params.slow_period")
        return self


class TimeSeriesTalibApoOperator(TimeSeriesOperator):
    """调用 ta::apo。"""

    op: Literal['talib.apo'] = Field(..., description='调用 ta::apo。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibApoParams = Field(
        default_factory=TimeSeriesTalibApoParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_apo(col, fast_period, slow_period, ma_type) {
            /*
            计算 TA-Lib APO（绝对价格振荡器）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            fast_period : int, default 12
                快线周期，必须小于 slow_period。
            slow_period : int, default 26
                慢线周期，必须大于 fast_period。
            ma_type : int, default 0
                TA-Lib 移动平均类型编号：0=SMA、1=EMA、2=WMA、3=DEMA、4=TEMA、5=TRIMA、6=KAMA、7=MAMA、8=T3。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            2/4 周期的简单移动平均：
            >>> tail(ts_talib_apo(close, 2, 4, 0), 3)
            [0.075, 0.25, 0.225]

            3/6 周期的简单移动平均：
            >>> tail(ts_talib_apo(close, 3, 6, 0), 3)
            [0.316667, 0.283333, 0.283333]

            2/4 周期的指数移动平均：
            >>> tail(ts_talib_apo(close, 2, 4, 1), 3)
            [0.207297, 0.245492, 0.134333]

            2/4 周期的加权移动平均：
            >>> tail(ts_talib_apo(close, 2, 4, 2), 3)
            [0.0833333, 0.2, 0.0866667]
            */
            return ta::apo(col, int(fast_period), int(slow_period), int(ma_type))
        }
        """
    )
