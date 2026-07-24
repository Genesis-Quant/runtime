"""定义 Playground HTTP 接口的响应模型。"""

from typing import Any

from pydantic import BaseModel, Field


class OperatorSpec(BaseModel):
    """描述前端构造和校验 DSL 所需的完整算符模型。"""

    type: str = Field(..., description="算符计算类别。")
    op: str = Field(..., description="DSL 算符名称。")
    description: str = Field(..., description="算符用途说明。")
    output_kind: str = Field(..., description="静态输出类型。")
    fields: dict[str, Any] = Field(..., description="fields 的 JSON Schema。")
    params: dict[str, Any] = Field(..., description="params 的 JSON Schema。")


class ValidationIssue(BaseModel):
    """描述一处可映射回 JSON AST 的请求校验错误。"""

    location: list[str | int] = Field(..., description="错误在请求对象中的路径。")
    message: str = Field(..., description="中文或 Pydantic 校验信息。")
    type: str = Field(..., description="Pydantic 错误类型。")


class ValidationResponse(BaseModel):
    """返回请求是否通过全部 Pydantic 和算符模型校验。"""

    valid: bool = Field(..., description="请求是否有效。")
    errors: list[ValidationIssue] = Field(
        default_factory=list,
        description="请求中的全部校验错误。",
    )


class IndexPreset(BaseModel):
    """描述前端可选的指数股票池预设。"""

    code: str = Field(..., description="Tushare 指数代码。")
    name: str = Field(..., description="指数显示名称。")


class IndexConstituentsResponse(BaseModel):
    """返回指数最近一期的非零权重成分股。"""

    index_code: str = Field(..., description="Tushare 指数代码。")
    trade_date: str = Field(
        ...,
        description="最近成分股快照日期，格式为 YYYY-MM-DD。",
    )
    codes: list[str] = Field(..., description="最近一期非零权重成分股代码。")


__all__ = [
    "IndexConstituentsResponse",
    "IndexPreset",
    "OperatorSpec",
    "ValidationIssue",
    "ValidationResponse",
]
