"""binary.gt 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import DirectOperator
from core.query.schema.fields import BinaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class DirectBinaryGtParams(StrictModel):
    """binary.gt 不接收参数。"""


class DirectBinaryGtOperator(DirectOperator):
    """逐行比较 gt。"""

    op: Literal['binary.gt'] = Field(..., description='逐行比较 gt。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryGtParams = Field(
        default_factory=DirectBinaryGtParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
