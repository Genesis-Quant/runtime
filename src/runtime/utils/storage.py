"""S3 兼容对象存储的 Parquet 上传、读取和清理支持。"""

from dataclasses import dataclass
from datetime import datetime
from tempfile import SpooledTemporaryFile
from typing import Any, Self
from urllib.parse import unquote, urlparse

import boto3
from botocore.config import Config
import pandas as pd

from runtime.config import ObjectStorageSettings


PARQUET_CONTENT_TYPE = "application/vnd.apache.parquet"
SPOOL_MAX_SIZE = 64 * 1024 * 1024


@dataclass(frozen=True)
class ObjectInfo:
    """对象存储中文件的必要元信息。"""

    size: int
    modified_at: datetime


class ObjectStorageConfigurationError(ValueError):
    """对象存储环境变量缺失或无效。"""


class ObjectStorage:
    """复用一个 S3 客户端管理工作流结果。"""

    def __init__(
            self,
            client: Any,
            bucket: str,
            root_folder: str = "",
    ) -> None:
        self.client = client
        self.bucket = bucket
        self.root_folder = root_folder

    @classmethod
    def from_env(cls) -> Self:
        """使用已从环境变量或 .env 加载的配置创建客户端。"""
        required = {
            "OBJECT_STORAGE_ENDPOINT_URL": ObjectStorageSettings.ENDPOINT_URL,
            "OBJECT_STORAGE_ACCESS_KEY_ID": ObjectStorageSettings.ACCESS_KEY_ID,
            "OBJECT_STORAGE_SECRET_ACCESS_KEY": (
                ObjectStorageSettings.SECRET_ACCESS_KEY
            ),
            "OBJECT_STORAGE_BUCKET": ObjectStorageSettings.BUCKET,
        }
        missing = [
            name
            for name, value in required.items()
            if not isinstance(value, str) or not value.strip()
        ]
        if missing:
            raise ObjectStorageConfigurationError(
                f"缺少对象存储配置：{missing}"
            )

        bucket = ObjectStorageSettings.BUCKET.strip()
        addressing_style = ObjectStorageSettings.ADDRESSING_STYLE
        if addressing_style not in {"auto", "path", "virtual"}:
            raise ObjectStorageConfigurationError(
                "OBJECT_STORAGE_ADDRESSING_STYLE "
                "必须是 auto、path 或 virtual"
            )

        root_folder = cls.normalize_root_folder(
            ObjectStorageSettings.ROOT_FOLDER
        )
        client = boto3.client(
            "s3",
            endpoint_url=ObjectStorageSettings.ENDPOINT_URL,
            aws_access_key_id=ObjectStorageSettings.ACCESS_KEY_ID,
            aws_secret_access_key=ObjectStorageSettings.SECRET_ACCESS_KEY,
            region_name=ObjectStorageSettings.REGION,
            config=Config(s3={"addressing_style": addressing_style}),
        )
        return cls(
            client,
            bucket,
            root_folder,
        )

    @staticmethod
    def normalize_root_folder(value: Any) -> str:
        """校验并标准化 bucket 内的可选根文件夹。"""
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ObjectStorageConfigurationError(
                "OBJECT_STORAGE_ROOT_FOLDER 必须是字符串"
            )
        normalized = value.strip().replace("\\", "/").strip("/")
        if not normalized:
            return ""
        if (
            (len(normalized) >= 2 and normalized[1] == ":")
            or "://" in normalized
            or any(
                part in {"", ".", ".."}
                for part in normalized.split("/")
            )
        ):
            raise ObjectStorageConfigurationError(
                "OBJECT_STORAGE_ROOT_FOLDER "
                "必须是 bucket 内的相对对象路径"
            )
        return normalized

    def object_key(self, key: str) -> str:
        """在任务对象键前添加统一根文件夹。"""
        if self.root_folder:
            return f"{self.root_folder}/{key}"
        return key

    def key_from_uri(self, uri: str) -> str:
        """解析本客户端 bucket 和根文件夹下的 S3 URI。"""
        parsed = urlparse(uri)
        key = unquote(parsed.path.lstrip("/"))
        if (
            parsed.scheme != "s3"
            or parsed.netloc != self.bucket
            or parsed.params
            or parsed.query
            or parsed.fragment
            or not key
        ):
            raise ObjectStorageConfigurationError(
                "对象存储 URI 必须指向已配置 bucket"
            )
        if self.root_folder and not key.startswith(f"{self.root_folder}/"):
            raise ObjectStorageConfigurationError(
                "对象存储 URI 不在 OBJECT_STORAGE_ROOT_FOLDER 下"
            )
        return key

    def upload_parquet(self, data: pd.DataFrame, key: str) -> str:
        """将 DataFrame 编码为 Parquet 并上传，返回 S3 URI。"""
        object_key = self.object_key(key)
        with SpooledTemporaryFile(
            max_size=SPOOL_MAX_SIZE,
            mode="w+b",
        ) as output:
            data.to_parquet(output, index=False)
            output.seek(0)
            self.client.upload_fileobj(
                output,
                self.bucket,
                object_key,
                ExtraArgs={"ContentType": PARQUET_CONTENT_TYPE},
            )
        return self.uri(object_key)

    def object_info(self, key: str) -> ObjectInfo:
        """读取对象大小和最后修改时间。"""
        response = self.client.head_object(Bucket=self.bucket, Key=key)
        return ObjectInfo(
            size=int(response["ContentLength"]),
            modified_at=response["LastModified"],
        )

    def download_url(self, key: str, expires_in: int = 300) -> str:
        """生成浏览器可直接下载私有对象的短时签名 URL。"""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete_prefix(self, key: str) -> None:
        """删除指定对象目录下的全部对象。"""
        normalized = key.strip("/")
        if not normalized or normalized == self.root_folder:
            raise ObjectStorageConfigurationError("拒绝删除对象存储根目录")
        prefix = f"{normalized}/"
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                if key := item.get("Key"):
                    self.client.delete_object(
                        Bucket=self.bucket,
                        Key=key,
                    )

    def uri(self, key: str) -> str:
        """返回便于日志展示的对象 URI。"""
        return f"s3://{self.bucket}/{key}"

    def close(self) -> None:
        """关闭底层 S3 客户端。"""
        self.client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> bool:
        self.close()
        return False
