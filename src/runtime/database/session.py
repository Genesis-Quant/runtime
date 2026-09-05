"""创建 DolphinDB 会话。"""

from threading import Lock, Timer
from time import monotonic
from typing import Any, Literal

import dolphindb

from runtime.config import DolphinSettings
from runtime.utils import logger, validate_dolphindb_identifier


class LoguruSink(dolphindb.logger.Sink):
    """把 DolphinDB session 消息转发到 Loguru。"""

    def __init__(self) -> None:
        super().__init__("loguru")

    def handle(self, msg: Any) -> None:
        logger.log(msg.level.name, msg.log.rstrip("\r\n"))

    def flush(self) -> None:
        return None


class DeadlineSession:
    """在截止时间到达时关闭底层连接，限制整个 Session 的总寿命。"""

    def __init__(self, session: Any, max_time: float) -> None:
        self.raw_session = session
        self.max_time = max_time
        self.deadline = monotonic() + max_time
        self.lock = Lock()
        self.closed = False
        self.expired = False
        self.timer = Timer(max_time, self.expire)
        self.timer.daemon = True
        self.timer.start()

    @property
    def msg_logger(self) -> Any:
        self.ensure_open()
        return self.raw_session.msg_logger

    def ensure_open(self) -> None:
        if self.expired or monotonic() >= self.deadline:
            self.expire()
            raise TimeoutError(
                f"DolphinDB Session 已超过最长使用时间 {self.max_time:g} 秒"
            )
        if self.closed:
            raise RuntimeError("DolphinDB Session 已关闭")

    def run(self, script: str, *args: Any, **kwargs: Any) -> Any:
        self.ensure_open()
        try:
            result = self.raw_session.run(script, *args, **kwargs)
        except Exception as error:
            if self.expired:
                raise TimeoutError(
                    f"DolphinDB Session 已超过最长使用时间 {self.max_time:g} 秒"
                ) from error
            raise
        self.ensure_open()
        return result

    def upload(self, variables: dict[str, Any]) -> Any:
        self.ensure_open()
        try:
            result = self.raw_session.upload(variables)
        except Exception as error:
            if self.expired:
                raise TimeoutError(
                    f"DolphinDB Session 已超过最长使用时间 {self.max_time:g} 秒"
                ) from error
            raise
        self.ensure_open()
        return result

    def expire(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.expired = True
            self.closed = True
        try:
            self.raw_session.close()
        except Exception as error:
            logger.warning(
                "DolphinDB Session 超时后关闭连接失败："
                f"{type(error).__name__}: {error}"
            )

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.timer.cancel()
        self.raw_session.close()

    def __getattr__(self, name: str) -> Any:
        """将未包装的 DolphinDB Session 方法转发给底层连接。"""
        self.ensure_open()
        return getattr(self.raw_session, name)


def redirect_session_output(session: Any) -> None:
    """关闭 DolphinDB stdout sink，并注册一次 Loguru sink。"""
    message_logger = session.msg_logger
    message_logger.disable_stdout_sink()
    if not any(sink.name == "loguru" for sink in message_logger.list_sinks()):
        message_logger.add_sink(LoguruSink())


def disable_session_output(session: Any) -> None:
    """关闭 DolphinDB stdout，并移除 Runtime 注册的 Loguru sink。"""
    message_logger = session.msg_logger
    message_logger.disable_stdout_sink()
    if any(sink.name == "loguru" for sink in message_logger.list_sinks()):
        message_logger.remove_sink("loguru")


def has_session_variable(
        session: Any,
        name: str,
        *,
        log_progress: bool = True,
) -> bool:
    """返回当前 DolphinDB session 中是否存在指定变量。"""
    validate_dolphindb_identifier(name)
    if log_progress:
        logger.info(f"session.run: 检查变量 {name} 是否存在")
    return bool(session.run(f"`{name} in objs(true).name"))


def create_session(
        *,
        role: Literal["runtime", "worker"] = "runtime",
        redirect_output: bool = True,
        max_time: int | None = None,
) -> Any:
    """连接 DolphinDB，并可限制 Session 从连接成功起的总使用时间。"""
    if max_time is not None and (
        isinstance(max_time, bool)
        or not isinstance(max_time, int)
        or max_time <= 0
    ):
        raise ValueError("max_time 必须是正整数秒数或 None")
    username, password = DolphinSettings.credentials(role)
    endpoints = configured_dolphin_endpoints()
    if DolphinSettings.USE_PUBLIC_NAME and len(endpoints) < 2:
        raise RuntimeError(
            "DOLPHIN_USE_PUBLIC_NAME=true 时必须配置至少一个 "
            "DOLPHIN_HIGH_AVAILABILITY_SITES 候选节点"
        )
    if DolphinSettings.USE_PUBLIC_NAME and DolphinSettings.HIGH_AVAILABILITY:
        return connect_public_session(
            username,
            password,
            redirect_output=redirect_output,
            max_time=max_time,
        )

    endpoint = f"{DolphinSettings.HOST}:{DolphinSettings.PORT}"
    logger.info(
        f"DolphinDB: {endpoint}"
        + (
            f"，高可用节点={len(DolphinSettings.HIGH_AVAILABILITY_SITES)}"
            if DolphinSettings.HIGH_AVAILABILITY
            else ""
        )
    )
    session = dolphindb.session(show_output=redirect_output)
    if redirect_output:
        redirect_session_output(session)
    if session.connect(
        DolphinSettings.HOST,
        DolphinSettings.PORT,
        username,
        password,
        highAvailability=DolphinSettings.HIGH_AVAILABILITY,
        highAvailabilitySites=(
            list(DolphinSettings.HIGH_AVAILABILITY_SITES)
            if DolphinSettings.HIGH_AVAILABILITY
            else None
        ),
        readTimeout=max_time,
        writeTimeout=max_time,
    ):
        return session_with_deadline(session, max_time)
    session.close()
    raise ConnectionError(f"无法连接 DolphinDB：{endpoint}")


def connect_public_session(
        username: str,
        password: str,
        *,
        redirect_output: bool,
        max_time: int | None,
) -> Any:
    """从公网映射入口依次连接，避免 Session 用内网 site 校验公网地址。"""
    endpoints = configured_dolphin_endpoints()
    logger.info(f"DolphinDB 公网入口：{len(endpoints)} 个候选节点")
    failures: list[Exception] = []
    for host, port in endpoints:
        session = dolphindb.session(show_output=redirect_output)
        if redirect_output:
            redirect_session_output(session)
        try:
            if session.connect(
                host,
                port,
                username,
                password,
                readTimeout=max_time,
                writeTimeout=max_time,
            ):
                logger.info(f"DolphinDB 已连接：{host}:{port}")
                return session_with_deadline(session, max_time)
        except Exception as error:
            failures.append(error)
            logger.warning(f"DolphinDB 公网入口不可用：{host}:{port}")
        session.close()

    addresses = ", ".join(f"{host}:{port}" for host, port in endpoints)
    error = ConnectionError(f"无法连接任一 DolphinDB 公网入口：{addresses}")
    if failures:
        raise error from failures[-1]
    raise error


def session_with_deadline(session: Any, max_time: int | None) -> Any:
    """仅在配置截止时间时包装已连接的 DolphinDB Session。"""
    return session if max_time is None else DeadlineSession(session, max_time)


def configured_dolphin_endpoints() -> tuple[tuple[str, int], ...]:
    """解析、校验并去重首选 DolphinDB 节点及其候选节点。"""
    configured = (
        f"{DolphinSettings.HOST}:{DolphinSettings.PORT}",
        *DolphinSettings.HIGH_AVAILABILITY_SITES,
    )
    endpoints: list[tuple[str, int]] = []
    for address in configured:
        host, separator, raw_port = address.rpartition(":")
        if not separator or not host:
            raise ValueError(f"DolphinDB 节点地址必须是 HOST:PORT：{address}")
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError(f"DolphinDB 节点端口超出范围：{address}")
        endpoint = (host, port)
        if endpoint not in endpoints:
            endpoints.append(endpoint)
    return tuple(endpoints)
