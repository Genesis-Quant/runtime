"""unary.consecutive_count 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import TimeSeriesOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryConsecutiveCountParams(StrictModel):
    """unary.consecutive_count 不接收参数。"""


class TimeSeriesUnaryConsecutiveCountOperator(TimeSeriesOperator):
    """计算连续 true 数量。"""

    op: Literal['unary.consecutive_count'] = Field(..., description='计算连续 true 数量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryConsecutiveCountParams = Field(
        default_factory=TimeSeriesUnaryConsecutiveCountParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
