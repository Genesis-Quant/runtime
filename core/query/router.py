"""提供统一因子查询的 HTTP 路由。"""

from collections.abc import Iterator
from io import BytesIO

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

from .api import execute_query
from .schema import FactorQuery


PARQUET_MEDIA_TYPE = "application/vnd.apache.parquet"
STREAM_CHUNK_SIZE = 1024 * 1024

router = APIRouter(tags=["query"])


def stream_buffer(buffer: BytesIO) -> Iterator[bytes]:
    """分块读取缓冲区，并在响应结束或中断后释放内存。"""
    try:
        while chunk := buffer.read(STREAM_CHUNK_SIZE):
            yield chunk
    finally:
        buffer.close()


@router.post(
    "/query",
    response_class=Response,
    response_model=None,
    responses={
        200: {
            "description": "查询结果 Parquet 文件。",
            "content": {
                PARQUET_MEDIA_TYPE: {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
def query_factors(request: FactorQuery) -> StreamingResponse:
    """执行因子查询，并以附件形式返回压缩后的 Parquet 文件。"""
    result = execute_query(request)
    buffer = BytesIO()
    result.to_parquet(
        buffer,
        engine="pyarrow",
        compression="zstd",
        index=False,
    )
    content_length = buffer.tell()
    buffer.seek(0)

    return StreamingResponse(
        stream_buffer(buffer),
        media_type=PARQUET_MEDIA_TYPE,
        headers={
            "Content-Disposition": 'attachment; filename="factors.parquet"',
            "Content-Length": str(content_length),
            "X-Result-Rows": str(len(result)),
        },
    )


__all__ = ["router"]
