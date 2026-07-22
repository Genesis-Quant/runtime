"""binary.ewm_corr 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesBinaryEwmCorrParams(StrictModel):
    """binary.ewm_corr 参数。"""

    com: float | None = Field(default=None, ge=0, allow_inf_nan=False, description="质心衰减参数。")
    span: float | None = Field(default=None, ge=1, allow_inf_nan=False, description="跨度衰减参数。")
    half_life: float | None = Field(default=None, gt=0, allow_inf_nan=False, description="半衰期参数。")
    alpha: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False, description="平滑系数。")
    min_periods: int = Field(default=0, ge=0, description="产生结果所需的最少非空观测数。")
    adjust: bool = Field(default=True, description="是否使用完整权重归一化。")
    ignore_na: bool = Field(default=False, description="计算权重时是否忽略 NULL 位置。")
    bias: bool = Field(default=False, description="方差、标准差和协方差是否使用有偏估计。")

    @model_validator(mode="after")
    def validate_decay(self) -> "TimeSeriesBinaryEwmCorrParams":
        """确保衰减参数恰好出现一个。"""
        values = [self.com, self.span, self.half_life, self.alpha]
        if sum(value is not None for value in values) != 1:
            raise ValueError("params.com/span/half_life/alpha 必须且只能提供一个")
        return self


class TimeSeriesBinaryEwmCorrOperator(TimeSeriesOperator):
    """按股票执行 ewm_corr。"""

    op: Literal['binary.ewm_corr'] = Field(..., description='按股票执行 ewm_corr。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryEwmCorrParams = Field(
        default_factory=TimeSeriesBinaryEwmCorrParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_binary_ewm_corr(left, right, com, span, half_life, alpha, min_periods, adjust, ignore_na, bias) {
            /*
            计算两个序列的指数加权移动相关系数。

            com、span、half_life 和 alpha 必须且只能提供一个，它们最终确定同一个平滑系数。结果与输入等长，并从序列起点递推或按完整权重计算。

            min_periods 控制首个非 NULL 结果所需的有效观测数；adjust 控制归一化权重形式；ignore_na 控制 NULL 是否占用权重位置。

            Parameters
            ----------
            left : vector
                第一条按时间升序排列的数值序列。
            right : vector
                与 left 等长的第二条数值序列。
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

            衰减与边界：com、span、half_life、alpha 必须且只能提供一个。只使用 left 与 right
            同时有效的配对观测；bias 控制协方差估计口径，有效配对不足或尺度为 0 时返回 NULL。

            Examples
            --------
            >>> left = 1.0 2.5 2.0 4.0 3.5 5.0 4.5 6.0
            >>> right = 1.5 2.0 2.5 3.0 4.0 4.5 5.0 5.5

            使用 com 指定衰减：
            >>> ts_binary_ewm_corr(left, right, 1.0, double(NULL), double(NULL), double(NULL), 1, true, false, false)
            [NULL, 1, 0.423659, 0.873422, 0.615603, 0.846314, 0.753962, 0.872929]

            使用 span 指定衰减：
            >>> ts_binary_ewm_corr(left, right, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false, false)
            [NULL, 1, 0.423659, 0.873422, 0.615603, 0.846314, 0.753962, 0.872929]

            使用 half_life 指定衰减：
            >>> ts_binary_ewm_corr(left, right, double(NULL), double(NULL), 2.0, double(NULL), 1, true, false, false)
            [NULL, 1, 0.554361, 0.874701, 0.735609, 0.877794, 0.855495, 0.911043]

            使用 alpha 指定衰减：
            >>> ts_binary_ewm_corr(left, right, double(NULL), double(NULL), double(NULL), 0.5, 1, true, false, false)
            [NULL, 1, 0.423659, 0.873422, 0.615603, 0.846314, 0.753962, 0.872929]

            adjust=false 使用递归形式：
            >>> ts_binary_ewm_corr(left, right, double(NULL), 3.0, double(NULL), double(NULL), 1, false, false, false)
            [NULL, 1, 0.622543, 0.89912, 0.68492, 0.86651, 0.782492, 0.881802]

            min_periods=3 延后首个有效结果：
            >>> ts_binary_ewm_corr(left, right, double(NULL), 3.0, double(NULL), double(NULL), 3, true, false, false)
            [NULL, NULL, 0.423659, 0.873422, 0.615603, 0.846314, 0.753962, 0.872929]

            bias=false 使用无偏估计：
            >>> ts_binary_ewm_corr(left, right, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false, false)
            [NULL, 1, 0.423659, 0.873422, 0.615603, 0.846314, 0.753962, 0.872929]

            bias=true 使用有偏估计：
            >>> ts_binary_ewm_corr(left, right, double(NULL), 3.0, double(NULL), double(NULL), 1, true, false, true)
            [NULL, 1, 0.423659, 0.873422, 0.615603, 0.846314, 0.753962, 0.872929]
            */
            if (!isNull(com)) return ewmCorr(left, com, , , , int(min_periods), adjust, ignore_na, right, bias)
            if (!isNull(span)) return ewmCorr(left, , span, , , int(min_periods), adjust, ignore_na, right, bias)
            if (!isNull(half_life)) return ewmCorr(left, , , half_life, , int(min_periods), adjust, ignore_na, right, bias)
            if (!isNull(alpha)) return ewmCorr(left, , , , alpha, int(min_periods), adjust, ignore_na, right, bias)
            throw "EWM 必须提供一个衰减参数"
        }
        """
    )
