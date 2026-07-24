"""multiary.and 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field


from core.query.schema.base import DirectOperator
from core.query.schema.fields import MultiaryFields
from core.query.schema.types import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryAndParams(StrictModel):
    """multiary.and 不接收参数。"""


class DirectMultiaryAndOperator(DirectOperator):
    """多条件逻辑 and。"""

    op: Literal['multiary.and'] = Field(..., description='多条件逻辑 and。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryAndParams = Field(
        default_factory=DirectMultiaryAndParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
