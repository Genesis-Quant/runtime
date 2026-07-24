"""unary.quantile 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import CrossSectionOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryQuantileParams(StrictModel):
    """unary.quantile 参数。"""

    q: float = Field(..., ge=0, le=1, allow_inf_nan=False, description="目标分位数。")


class CrossSectionUnaryQuantileOperator(CrossSectionOperator):
    """按交易日广播 quantile 统计量。"""

    op: Literal['unary.quantile'] = Field(..., description='按交易日广播 quantile 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryQuantileParams = Field(
        default_factory=CrossSectionUnaryQuantileParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
