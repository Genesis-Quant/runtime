"""unary.rank_dense 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import CrossSectionOperator
from core.query.schema.fields import UnaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryRankDenseParams(StrictModel):
    """unary.rank_dense 参数。"""

    ascending: bool = Field(default=True, description="是否按升序排名。")


class CrossSectionUnaryRankDenseOperator(CrossSectionOperator):
    """按交易日执行 rank_dense。"""

    op: Literal['unary.rank_dense'] = Field(..., description='按交易日执行 rank_dense。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryRankDenseParams = Field(
        default_factory=CrossSectionUnaryRankDenseParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
