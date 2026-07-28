"""在源码仓库中调用已安装的 Core 管理命令。"""

from core.manage import main

if __name__ == "__main__":
    raise SystemExit(main())
