from __future__ import annotations

import argparse
import sys

from tutormatch.config import get_default_model, load_runtime_config
from tutormatch.interactive import run_interactive


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_runtime_config()

    parser = argparse.ArgumentParser(
        description="家教兼职机会筛选 Agent MVP1：终端交互式输入并生成筛选结果。"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="展示前 N 个机会。",
    )
    parser.add_argument(
        "--model",
        default=get_default_model(),
        help="LangChain init_chat_model 使用的模型名，默认读取 TUTORMATCH_MODEL、MODEL 或 LLM_MODEL。",
    )
    args = parser.parse_args()

    run_interactive(top=args.top, model=args.model)
