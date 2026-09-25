"""Windows 桌面宿主。

复用现有 Flask 应用作为本地业务内核，
通过 pywebview 在独立 Windows 窗口中显示系统。
"""

from __future__ import annotations

import os
import socket
import threading
import time

from dataclasses import dataclass
from pathlib import Path

from werkzeug.serving import (
    BaseWSGIServer,
    make_server,
)

from fire_monitor.app import (
    create_app,
)


APP_TITLE = (
    "黑龙江省火点数据检测与风险评估平台"
)

APP_DATA_FOLDER = (
    "HeilongjiangFireMonitor"
)

DEFAULT_HOST = (
    "127.0.0.1"
)

DEFAULT_WIDTH = 1440
DEFAULT_HEIGHT = 900

MIN_WIDTH = 1100
MIN_HEIGHT = 700


def user_data_root() -> Path:
    """返回当前 Windows 用户的可写软件数据目录。"""

    local_app_data = (
        os.environ.get(
            "LOCALAPPDATA"
        )
    )

    if local_app_data:

        root = (
            Path(local_app_data)
            / APP_DATA_FOLDER
        )

    else:

        root = (
            Path.home()
            / ".heilongjiang_fire_monitor"
        )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    return root


def _find_free_port(
    host: str = DEFAULT_HOST,
) -> int:
    """选择一个空闲本地端口。"""

    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as sock:

        sock.bind(
            (
                host,
                0,
            )
        )

        return int(
            sock
            .getsockname()[1]
        )


@dataclass
class DesktopServer:
    """桌面模式使用的本地 WSGI 服务。"""

    host: str = DEFAULT_HOST
    port: int | None = None

    def __post_init__(
        self,
    ) -> None:

        if self.port is None:

            self.port = (
                _find_free_port(
                    self.host
                )
            )

        data_root = (
            user_data_root()
        )

        runtime_root = (
            data_root
            / "runtime"
        )

        uploads_root = (
            data_root
            / "uploads"
        )

        runtime_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        uploads_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        os.environ[
            "FIRE_MONITOR_RUNTIME_DIR"
        ] = str(
            runtime_root
        )

        database_path = (
            runtime_root
            / "fire_monitor.sqlite"
        )

        self.app = create_app(
            database_path=(
                database_path
            ),
            uploads_root=(
                uploads_root
            ),
        )

        self._server: (
            BaseWSGIServer
            | None
        ) = None

        self._thread: (
            threading.Thread
            | None
        ) = None

    @property
    def url(
        self,
    ) -> str:

        assert (
            self.port
            is not None
        )

        return (
            f"http://"
            f"{self.host}:"
            f"{self.port}"
        )

    def start(
        self,
    ) -> None:
        """启动本地 Flask/Werkzeug 服务。"""

        if (
            self._server
            is not None
        ):
            return

        assert (
            self.port
            is not None
        )

        self._server = (
            make_server(
                self.host,
                self.port,
                self.app,
                threaded=True,
            )
        )

        self._thread = (
            threading.Thread(
                target=(
                    self
                    ._server
                    .serve_forever
                ),
                name=(
                    "fire-monitor-"
                    "desktop-server"
                ),
                daemon=True,
            )
        )

        self._thread.start()

        self._wait_until_ready()

    def _wait_until_ready(
        self,
        timeout_seconds: float = 5.0,
    ) -> None:
        """等待本地服务真正进入监听状态。"""

        assert (
            self.port
            is not None
        )

        deadline = (
            time.monotonic()
            + timeout_seconds
        )

        while (
            time.monotonic()
            < deadline
        ):

            try:

                with (
                    socket
                    .create_connection(
                        (
                            self.host,
                            self.port,
                        ),
                        timeout=0.2,
                    )
                ):
                    return

            except OSError:

                time.sleep(
                    0.05
                )

        raise RuntimeError(
            "桌面内置服务启动超时。"
        )

    def stop(
        self,
    ) -> None:
        """关闭桌面内置服务。"""

        server = (
            self._server
        )

        if server is None:
            return

        server.shutdown()

        self._server = None

        thread = (
            self._thread
        )

        if (
            thread is not None
            and thread.is_alive()
        ):

            thread.join(
                timeout=2.0
            )

        self._thread = None


def run_desktop() -> None:
    """启动桌面应用窗口。"""

    try:

        import webview

        # Flask attachment exports need downloads enabled in pywebview.
        webview.settings["ALLOW_DOWNLOADS"] = True

    except ImportError as exc:

        raise RuntimeError(
            "桌面模式需要 pywebview。"
        ) from exc

    server = (
        DesktopServer()
    )

    webview_storage = (
        user_data_root()
        / "webview"
    )

    webview_storage.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:

        server.start()

        webview.create_window(
            APP_TITLE,
            server.url,
            width=(
                DEFAULT_WIDTH
            ),
            height=(
                DEFAULT_HEIGHT
            ),
            min_size=(
                MIN_WIDTH,
                MIN_HEIGHT,
            ),
            resizable=True,
            background_color=(
                "#EEF3F7"
            ),
        )

        webview.start(
            debug=False,
            private_mode=False,
            storage_path=str(
                webview_storage
            ),
        )

    finally:

        server.stop()


if __name__ == "__main__":
    run_desktop()