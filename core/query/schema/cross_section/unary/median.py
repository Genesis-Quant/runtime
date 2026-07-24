"""unary.median 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import CrossSectionOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryMedianParams(StrictModel):
    """unary.median 不接收参数。"""


class CrossSectionUnaryMedianOperator(CrossSectionOperator):
    """按交易日广播 median 统计量。"""

    op: Literal['unary.median'] = Field(..., description='按交易日广播 median 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryMedianParams = Field(
        default_factory=CrossSectionUnaryMedianParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
