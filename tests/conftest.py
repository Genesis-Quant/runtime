"""连接现有 DolphinDB，并为随机差分测试提供确定性配置。"""

from pathlib import Path

import dolphindb as ddb
from hypothesis import HealthCheck, settings
import pytest

from core.dolphindb.script import build_script


settings.register_profile(
    "ci",
    max_examples=40,
    deadline=None,
    derandomize=True,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
settings.load_profile("ci")


def _environment() -> dict[str, str]:
    """读取 Seminar 根目录的 DolphinDB 连接配置。"""
    path = Path(__file__).parents[2] / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


@pytest.fixture(scope="session")
def ddb_session():
    """连接已经运行的 DolphinDB 服务，并加载当前项目生成的完整脚本。"""
    environment = _environment()
    session = ddb.session()
    connected = session.connect(
        environment.get("DOLPHIN_HOST", "127.0.0.1"),
        int(environment.get("DOLPHIN_PORT", "8848")),
        environment.get("DOLPHIN_USERNAME", "admin"),
        environment.get("DOLPHIN_PASSWORD", "123456"),
    )
    if not connected:
        pytest.fail("无法连接现有 DolphinDB 服务")
    session.run(build_script())
    yield session
    session.close()
