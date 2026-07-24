"""talib.medPrice 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import TimeSeriesOperator
from core.query.schema.fields import HighLowFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibMedPriceParams(StrictModel):
    """talib.medPrice 不接收参数。"""


class TimeSeriesTalibMedPriceOperator(TimeSeriesOperator):
    """计算中间价。"""

    op: Literal['talib.medPrice'] = Field(..., description='计算中间价。')
    fields: HighLowFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibMedPriceParams = Field(
        default_factory=TimeSeriesTalibMedPriceParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
