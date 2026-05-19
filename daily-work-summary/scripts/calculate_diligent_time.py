#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
勤奋时间计算工具
================
根据当前系统时间计算勤奋工作的结束时间。

规则：
- 起始时间固定为 17:45
- 从 17:45 起，每 30 分钟为一个计时单位
- 只有完整的 30 分钟才计入，余数丢弃
- 示例：当前时间 20:14 → 从 17:45 到 20:14 共 149 分钟 → 4 个完整块 → 结束时间 19:45

用法:
    python calculate_diligent_time.py
    python calculate_diligent_time.py --time 20:14
"""

import sys
import io
import argparse
from datetime import datetime, timedelta

# 解决 Windows 控制台 GBK 编码问题
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def calculate_diligent_time(now=None):
    if now is None:
        now = datetime.now()

    # 起始时间固定为当天的 17:45
    start = now.replace(hour=17, minute=45, second=0, microsecond=0)

    if now <= start:
        print("当前时间未到 17:45，无需计算勤奋时间。")
        return

    # 从 17:45 到现在的分钟数
    delta_minutes = (now - start).total_seconds() / 60

    # 完整的 30 分钟块数
    full_blocks = int(delta_minutes // 30)

    if full_blocks == 0:
        print("勤奋时间不足 30 分钟，不计入。")
        return

    end = start + timedelta(minutes=full_blocks * 30)
    end_time = end.strftime("%H:%M")

    print(f"[勤奋时间][17:45][{end_time}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="勤奋时间计算工具")
    parser.add_argument("--time", default=None, help="模拟时间，格式 HH:MM（用于测试）")
    args = parser.parse_args()

    if args.time:
        h, m = map(int, args.time.split(":"))
        now = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
        calculate_diligent_time(now)
    else:
        calculate_diligent_time()
