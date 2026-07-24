"""talib.linearreg_intercept 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import TimeSeriesOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibLinearregInterceptParams(StrictModel):
    """talib.linearreg_intercept 参数。"""

    time_period: int = Field(..., ge=2, description="技术指标观察周期。")


class TimeSeriesTalibLinearregInterceptOperator(TimeSeriesOperator):
    """调用 ta::linearreg_intercept。"""

    op: Literal['talib.linearreg_intercept'] = Field(..., description='调用 ta::linearreg_intercept。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibLinearregInterceptParams = Field(
        default_factory=TimeSeriesTalibLinearregInterceptParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
