"""unary.ewm_std 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryEwmStdParams(StrictModel):
    """unary.ewm_std 参数。"""

    com: float | None = Field(default=None, ge=0, allow_inf_nan=False, description="质心衰减参数。")
    span: float | None = Field(default=None, ge=1, allow_inf_nan=False, description="跨度衰减参数。")
    half_life: float | None = Field(default=None, gt=0, allow_inf_nan=False, description="半衰期参数。")
    alpha: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False, description="平滑系数。")
    min_periods: int = Field(default=0, ge=0, description="产生结果所需的最少非空观测数。")
    adjust: bool = Field(default=True, description="是否使用完整权重归一化。")
    ignore_na: bool = Field(default=False, description="计算权重时是否忽略 NULL 位置。")
    bias: bool = Field(default=False, description="方差、标准差和协方差是否使用有偏估计。")

    @model_validator(mode="after")
    def validate_decay(self) -> "TimeSeriesUnaryEwmStdParams":
        """确保衰减参数恰好出现一个。"""
        values = [self.com, self.span, self.half_life, self.alpha]
        if sum(value is not None for value in values) != 1:
            raise ValueError("params.com/span/half_life/alpha 必须且只能提供一个")
        return self


class TimeSeriesUnaryEwmStdOperator(TimeSeriesOperator):
    """按股票执行 ewm_std。"""

    op: Literal['unary.ewm_std'] = Field(..., description='按股票执行 ewm_std。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryEwmStdParams = Field(
        default_factory=TimeSeriesUnaryEwmStdParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_ewm_std(col, com, span, half_life, alpha, min_periods, adjust, ignore_na, bias) {
            /*
            计算指数加权移动标准差。

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
            bias : bool, default false
                true 使用有偏估计；false 对有限样本进行无偏修正。

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

            衰减与边界：com、span、half_life、alpha 必须且只能提供一个。bias
            控制是否使用有偏估计；有效样本不足以估计尺度时返回 NULL。四种衰减参数只是 alpha 的不同表达。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            使用 com 指定衰减：
            >>> ts_unary_ewm_std(col, 1.0, double(NULL), double(NULL), double(NULL), 1, true, false, false)
            [NULL, 0.707107, 1.58114, 1.0351, 1.43122, 2.0848, 1.48956, 1.72338]

            使用 span 指定衰减：
            >>> ts_unary_ewm_std(col, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false, false)
            [NULL, 0.707107, 1.58114, 1.0351, 1.43122, 2.0848, 1.48956, 1.72338]

            使用 half_life 指定衰减：
            >>> ts_unary_ewm_std(col, double(NULL), double(NULL), 2.0, double(NULL), 1, true, false, false)
            [NULL, 0.707107, 1.5688, 1.17484, 1.51814, 2.19437, 1.90963, 2.15886]

            使用 alpha 指定衰减：
            >>> ts_unary_ewm_std(col, double(NULL), double(NULL), double(NULL), 0.5, 1, true, false, false)
            [NULL, 0.707107, 1.58114, 1.0351, 1.43122, 2.0848, 1.48956, 1.72338]

            adjust=false 使用递归形式：
            >>> ts_unary_ewm_std(col, double(NULL), 3.0, double(NULL), double(NULL), 1, false, false, false)
            [NULL, 0.707107, 1.64317, 1.14434, 1.53201, 2.16578, 1.56507, 1.77469]

            min_periods=3 延后首个有效结果：
            >>> ts_unary_ewm_std(col, double(NULL), 3.0, double(NULL), double(NULL), 3, true, false, false)
            [NULL, NULL, 1.58114, 1.0351, 1.43122, 2.0848, 1.48956, 1.72338]

            bias=false 使用无偏估计：
            >>> ts_unary_ewm_std(col, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false, false)
            [NULL, 0.707107, 1.58114, 1.0351, 1.43122, 2.0848, 1.48956, 1.72338]

            bias=true 使用有偏估计：
            >>> ts_unary_ewm_std(col, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false, true)
            [0, 0.471405, 1.19523, 0.816497, 1.14958, 1.68867, 1.21142, 1.40437]

            >>> col = 1.0 2.0 3.0 4.0 5.0 6.0
            >>> col[1 3] = NULL

            ignore_na=false 按绝对位置计算权重：
            >>> ts_unary_ewm_std(col, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false, false)
            [NULL, NULL, 1.41421, 1.41421, 1.77281, 1.40671]

            ignore_na=true 按有效观测的相对位置计算权重：
            >>> ts_unary_ewm_std(col, double(NULL), 3.0, double(NULL), double(NULL), 1, true, true, false)
            [NULL, NULL, 1.41421, 1.41421, 1.92725, 1.85164]
            */
            if (!isNull(com)) return ewmStd(col, com, , , , int(min_periods), adjust, ignore_na, bias)
            if (!isNull(span)) return ewmStd(col, , span, , , int(min_periods), adjust, ignore_na, bias)
            if (!isNull(half_life)) return ewmStd(col, , , half_life, , int(min_periods), adjust, ignore_na, bias)
            if (!isNull(alpha)) return ewmStd(col, , , , alpha, int(min_periods), adjust, ignore_na, bias)
            throw "EWM 必须提供一个衰减参数"
        }
        """
    )
