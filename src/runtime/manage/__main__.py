"""支持通过 ``python -m runtime.manage`` 调用管理命令。"""

from . import main


if __name__ == "__main__":
    raise SystemExit(main())
