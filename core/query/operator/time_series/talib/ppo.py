"""talib.ppo 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import TALIB_MOVING_AVERAGE

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibPpoParams(StrictModel):
    """talib.ppo 参数。"""

    fast_period: int = Field(default=12, ge=2, description="快线周期。")
    slow_period: int = Field(default=26, ge=2, description="慢线周期。")
    ma_type: Literal[0, 1, 2, 3, 4, 5, 6, 8] = Field(
        default=0,
        description="TA-Lib 移动平均类型编号；当前 DolphinDB 不支持 MAMA(7)。",
    )

    @model_validator(mode="after")
    def validate_periods(self) -> "TimeSeriesTalibPpoParams":
        """要求快线周期小于慢线周期。"""
        if self.fast_period >= self.slow_period:
            raise ValueError("params.fast_period 必须小于 params.slow_period")
        return self


class TimeSeriesTalibPpoOperator(TimeSeriesOperator):
    """调用 ta::ppo。"""

    op: Literal['talib.ppo'] = Field(..., description='调用 ta::ppo。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibPpoParams = Field(
        default_factory=TimeSeriesTalibPpoParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_ppo(col, fast_period, slow_period, ma_type) {
            /*
            计算 TA-Lib PPO（百分比价格振荡器）。

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
                TA-Lib 移动平均类型编号：0=SMA、1=EMA、2=WMA、3=DEMA、4=TEMA、5=TRIMA、6=KAMA、8=T3。
                当前 DolphinDB 后端不支持 7=MAMA，模型会在构造阶段拒绝；T3 使用 TA-Lib 标准的 0.7 成交量因子。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：计算 100 * (fastMA - slowMA) / slowMA，以百分比表达快慢均线差。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            2/4 周期的简单移动平均：
            >>> tail(ts_talib_ppo(close, 2, 4, 0), 3)
            [0.642398, 2.10084, 1.87891]

            3/6 周期的简单移动平均：
            >>> tail(ts_talib_ppo(close, 3, 6, 0), 3)
            [2.76565, 2.43205, 2.391]

            2/4 周期的指数移动平均：
            >>> tail(ts_talib_ppo(close, 2, 4, 1), 3)
            [1.78113, 2.06242, 1.12114]

            2/4 周期的加权移动平均：
            >>> tail(ts_talib_ppo(close, 2, 4, 2), 3)
            [0.70922, 1.66667, 0.717439]
            */
            fast = talib_moving_average(col, fast_period, ma_type)
            slow = talib_moving_average(col, slow_period, ma_type)
            return (fast - slow) / slow * 100
        }
        """,
        dependencies=(TALIB_MOVING_AVERAGE,),
    )
