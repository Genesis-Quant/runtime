"""允许通过 ``python -m core.manage.apps`` 运行应用命令。"""

from . import main


if __name__ == "__main__":
    raise SystemExit(main())

