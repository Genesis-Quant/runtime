"""unary.ewm_mean 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryEwmMeanParams(StrictModel):
    """unary.ewm_mean 参数。"""

    com: float | None = Field(default=None, ge=0, allow_inf_nan=False, description="质心衰减参数。")
    span: float | None = Field(default=None, ge=1, allow_inf_nan=False, description="跨度衰减参数。")
    half_life: float | None = Field(default=None, gt=0, allow_inf_nan=False, description="半衰期参数。")
    alpha: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False, description="平滑系数。")
    min_periods: int = Field(default=0, ge=0, description="产生结果所需的最少非空观测数。")
    adjust: bool = Field(default=True, description="是否使用完整权重归一化。")
    ignore_na: bool = Field(default=False, description="计算权重时是否忽略 NULL 位置。")

    @model_validator(mode="after")
    def validate_decay(self) -> "TimeSeriesUnaryEwmMeanParams":
        """确保衰减参数恰好出现一个。"""
        values = [self.com, self.span, self.half_life, self.alpha]
        if sum(value is not None for value in values) != 1:
            raise ValueError("params.com/span/half_life/alpha 必须且只能提供一个")
        return self


class TimeSeriesUnaryEwmMeanOperator(TimeSeriesOperator):
    """按股票执行 ewm_mean。"""

    op: Literal['unary.ewm_mean'] = Field(..., description='按股票执行 ewm_mean。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryEwmMeanParams = Field(
        default_factory=TimeSeriesUnaryEwmMeanParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_ewm_mean(col, com, span, half_life, alpha, min_periods, adjust, ignore_na) {
            /*
            计算指数加权移动平均。

            com、span、half_life 和 alpha 必须且只能提供一个，它们最终确定同一个平滑系数。结果与输入等长，并从序列起点递推或按完整权重计算。

            min_periods 控制首个非 NULL 结果所需的有效观测数；adjust 控制归一化权重形式；ignore_na 控制 NULL 是否占用权重位置。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            com : float or NULL, default NULL
                指数加权衰减参数；四个参数必须且只能提供一个。alpha = 1 / (1 + com)，com >= 0。
            span : float or NULL, default NULL
                指数加权衰减参数；四个参数必须且只能提供一个。alpha = 2 / (span + 1)，span >= 1。
            half_life : float or NULL, default NULL
                指数加权衰减参数；四个参数必须且只能提供一个。alpha = 1 - exp(log(0.5) / half_life)，half_life > 0。
            alpha : float or NULL, default NULL
                指数加权衰减参数；四个参数必须且只能提供一个。直接指定平滑系数，0 < alpha <= 1。
            min_periods : int, default 0
                产生结果所需的累计非 NULL 观测数。未达到该数量的位置返回 NULL。
            adjust : bool, default true
                true 时使用显式衰减权重并除以权重和；false 时使用递归更新形式。
            ignore_na : bool, default false
                false 时权重按绝对位置计算，NULL 仍占用位置；true 时权重只按有效观测的相对位置计算。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Raises
            ------
            DolphinDB exception
                未提供任何 EWM 衰减参数时抛出异常。正常 DSL 构造会在 Python 校验阶段阻止该输入。

            Notes
            -----
            NULL 处理：输入 NULL 不会被填充。ignore_na=false
            时缺失位置仍影响后续权重距离，ignore_na=true 时仅按有效观测的相对位置累计权重；min_periods
            统计非 NULL 观测。

            衰减与边界：com、span、half_life、alpha 必须且只能提供一个。adjust=true
            使用归一化的显式历史权重，adjust=false 使用递推形式；四种衰减参数只是 alpha 的不同表达。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            使用 com 指定衰减：
            >>> ts_unary_ewm_mean(col, 1.0, double(NULL), double(NULL), double(NULL), 1, true, false)
            [1, 1.66667, 3, 3, 4.03226, 5.53968, 5.77165, 6.8902]

            使用 span 指定衰减：
            >>> ts_unary_ewm_mean(col, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false)
            [1, 1.66667, 3, 3, 4.03226, 5.53968, 5.77165, 6.8902]

            使用 half_life 指定衰减：
            >>> ts_unary_ewm_mean(col, double(NULL), double(NULL), 2.0, double(NULL), 1, true, false)
            [1, 1.58579, 2.67962, 2.80474, 3.58579, 4.72864, 5.13712, 6.03154]

            使用 alpha 指定衰减：
            >>> ts_unary_ewm_mean(col, double(NULL), double(NULL), double(NULL), 0.5, 1, true, false)
            [1, 1.66667, 3, 3, 4.03226, 5.53968, 5.77165, 6.8902]

            adjust=false 使用递归形式：
            >>> ts_unary_ewm_mean(col, double(NULL), 3.0, double(NULL), double(NULL), 1, false, false)
            [1, 1.5, 2.75, 2.875, 3.9375, 5.46875, 5.73438, 6.86719]

            min_periods=3 延后首个有效结果：
            >>> ts_unary_ewm_mean(col, double(NULL), 3.0, double(NULL), double(NULL), 3, true, false)
            [NULL, NULL, 3, 3, 4.03226, 5.53968, 5.77165, 6.8902]

            >>> col = 1.0 2.0 3.0 4.0 5.0 6.0
            >>> col[1 3] = NULL

            ignore_na=false 按绝对位置计算权重：
            >>> ts_unary_ewm_mean(col, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false)
            [1, 1, 2.6, 2.6, 4.42857, 5.37736]

            ignore_na=true 按有效观测的相对位置计算权重：
            >>> ts_unary_ewm_mean(col, double(NULL), 3.0, double(NULL), double(NULL), 1, true, true)
            [1, 1, 2.33333, 2.33333, 3.85714, 5]
            */
            if (!isNull(com)) return ewmMean(col, com, , , , int(min_periods), adjust, ignore_na)
            if (!isNull(span)) return ewmMean(col, , span, , , int(min_periods), adjust, ignore_na)
            if (!isNull(half_life)) return ewmMean(col, , , half_life, , int(min_periods), adjust, ignore_na)
            if (!isNull(alpha)) return ewmMean(col, , , , alpha, int(min_periods), adjust, ignore_na)
            throw "EWM 必须提供一个衰减参数"
        }
        """
    )
