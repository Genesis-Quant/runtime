"""binary.cross_above 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import TimeSeriesOperator
from core.query.schema.fields import BinaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class TimeSeriesBinaryCrossAboveParams(StrictModel):
    """binary.cross_above 不接收参数。"""


class TimeSeriesBinaryCrossAboveOperator(TimeSeriesOperator):
    """按股票判断 cross_above。"""

    op: Literal['binary.cross_above'] = Field(..., description='按股票判断 cross_above。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryCrossAboveParams = Field(
        default_factory=TimeSeriesBinaryCrossAboveParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
