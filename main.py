"""CLI 入口：``python main.py``（等价于 ``python -m src.cli``）。

运行于项目根目录时 ``src`` 包可直接 import。
"""

from src.cli import main

if __name__ == "__main__":
    main()
