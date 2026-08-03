"""talib.atr 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from runtime.apps.query.dsl.base import TimeSeriesOperator
from runtime.apps.query.dsl.fields import OHLCFields
from runtime.apps.query.dsl.types import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibAtrParams(StrictModel):
    """talib.atr 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibAtrOperator(TimeSeriesOperator):
    """调用 ta::atr。"""

    op: Literal['talib.atr'] = Field(..., description='调用 ta::atr。')
    fields: OHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibAtrParams = Field(
        default_factory=TimeSeriesTalibAtrParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
