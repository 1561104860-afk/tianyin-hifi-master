#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键把本 Skill 安装到 WorkBuddy 用户级 skills 目录。

用法:
  python install.py
  python install.py --target "~/my-skills/tianyin-hifi-master"

只复制公开文件；目标目录里已存在的 cookie.txt / config.json 会被原样保留。
"""
import argparse
import os
import shutil
import sys

SKILL_NAME = "tianyin-hifi-master"
FILES = ["SKILL.md", "README.md", "LICENSE", "install.py",
         "config.example.json", "cookie.example.txt"]
DIRS = ["scripts", "references"]
PRIVATE = ["cookie.txt", "config.json"]


def main():
    ap = argparse.ArgumentParser(description="安装 tianyin-hifi-master 到 WorkBuddy 技能目录")
    ap.add_argument("--target", default=os.path.join(
        os.path.expanduser("~"), ".workbuddy", "skills", SKILL_NAME),
        help="安装目标目录（默认 ~/.workbuddy/skills/tianyin-hifi-master）")
    args = ap.parse_args()

    src = os.path.dirname(os.path.abspath(__file__))
    dst = os.path.abspath(os.path.expanduser(args.target))

    missing = [f for f in FILES + DIRS if not os.path.exists(os.path.join(src, f))]
    if missing:
        sys.exit("× 仓库内容不完整，缺少: " + ", ".join(missing))

    kept = [f for f in PRIVATE if os.path.exists(os.path.join(dst, f))]
    os.makedirs(dst, exist_ok=True)
    for f in FILES:
        shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    for d in DIRS:
        shutil.copytree(os.path.join(src, d), os.path.join(dst, d),
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    print(f"√ 已安装到: {dst}")
    if kept:
        print("√ 已保留你的私有文件: " + ", ".join(kept))

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("! 未检测到 ffmpeg/ffprobe —— 运行前请先安装")
        print("  Windows: winget install Gyan.FFmpeg | macOS: brew install ffmpeg")
    else:
        print("√ ffmpeg 已就绪")

    cookie = os.path.join(dst, "cookie.txt")
    if not os.path.exists(cookie):
        print("\n下一步：把天音 Cookie 存为 " + cookie)
        print("        （或设置环境变量 TIANYIN_COOKIE）")
        print("        获取方式见 README.md「放 Cookie」")
    print("\n验证: python \"" + os.path.join(dst, "scripts", "master_pipeline.py") + "\" list")
    print("之后对 WorkBuddy 说「把《XXX》提出来」即可自动触发。")


if __name__ == "__main__":
    main()
