#!/usr/bin/env python3
import sys
import argparse
from pipeline import run_pipeline

BANNER = """
╔══════════════════════════════════════════════════════════╗
║          AI 软件工厂  —  多 Agent 代码生产流水线          ║
║  CEO → PM → CTO → Backend → Frontend → Code → QA → 验收  ║
╚══════════════════════════════════════════════════════════╝
"""


def main():
    parser = argparse.ArgumentParser(description="AI 软件工厂 — 多 Agent 代码生产流水线")
    parser.add_argument("requirement", nargs="?", help="用户需求（可以是一段描述）")
    parser.add_argument("--auto", action="store_true", help="自动模式，不等待确认直接运行所有阶段")
    parser.add_argument("--file", "-f", help="从文件读取需求")
    args = parser.parse_args()

    print(BANNER)

    if args.file:
        requirement = open(args.file, encoding="utf-8").read().strip()
    elif args.requirement:
        requirement = args.requirement
    else:
        print("请输入你的产品需求（多行输入，输入空行结束）：\n")
        lines = []
        while True:
            try:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            except EOFError:
                break
        requirement = "\n".join(lines).strip()

    if not requirement:
        print("需求不能为空。")
        sys.exit(1)

    print(f"\n需求已接收（{len(requirement)} 字）")
    if not args.auto:
        print("交互模式：每个阶段完成后可输入 Y 继续、N 退出、R 重跑当前步")
    else:
        print("自动模式：将自动运行所有阶段")

    run_pipeline(requirement, auto=args.auto)


if __name__ == "__main__":
    main()
