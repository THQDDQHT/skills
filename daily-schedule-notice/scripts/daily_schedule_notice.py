#!/usr/bin/env python3
"""Generate the user's daily overtime, workout, and meal-prep notice."""

from __future__ import annotations

import argparse
import calendar
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DayPlan:
    overtime: str
    gym: str
    meals: str
    focus: str


@dataclass(frozen=True)
class Notice:
    date: str
    month_week: int
    weekday: str
    week_type: str
    week_reason: str
    overtime_saturdays: list[str]
    plan: DayPlan
    reminder: str
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Simplified Chinese daily schedule notice."
    )
    parser.add_argument(
        "--date",
        help="Override date in YYYY-MM-DD, defaults to today in Asia/Shanghai.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON instead of plain text.",
    )
    return parser.parse_args()


def today_in_china() -> date:
    return datetime.now(TZ).date()


def parse_date(value: str | None) -> date:
    if not value:
        return today_in_china()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"--date must use YYYY-MM-DD, got: {value}") from exc


def month_week_number(day: date) -> int:
    """Monday-start calendar week number inside a month.

    Week 1 is the week containing the 1st day of the month. This matches normal
    calendar display and gives stable "本月第几周" wording for daily notices.
    """

    first = day.replace(day=1)
    first_weekday = first.weekday()
    return ((day.day + first_weekday - 1) // 7) + 1


def saturdays_in_month(year: int, month: int) -> list[date]:
    _, days_in_month = calendar.monthrange(year, month)
    return [
        date(year, month, day_num)
        for day_num in range(1, days_in_month + 1)
        if date(year, month, day_num).weekday() == 5
    ]


def overtime_saturdays_for_month(year: int, month: int) -> list[date]:
    saturdays = saturdays_in_month(year, month)
    selected: list[date] = []
    if len(saturdays) >= 2:
        selected.append(saturdays[1])
    if len(saturdays) >= 4:
        selected.append(saturdays[3])
    return selected


def current_week_saturday(day: date) -> date:
    return day + timedelta(days=5 - day.weekday())


def is_overtime_week(day: date) -> tuple[bool, str]:
    saturday = current_week_saturday(day)
    month_ot_saturdays = overtime_saturdays_for_month(saturday.year, saturday.month)
    if saturday in month_ot_saturdays:
        nth = saturdays_in_month(saturday.year, saturday.month).index(saturday) + 1
        return (
            True,
            f"本周六 {saturday.month}月{saturday.day}日 是本月第{nth}个周六，安排加班8h",
        )
    return False, f"本周六 {saturday.month}月{saturday.day}日 不是本月第2/第4个周六"


def format_dates(days: list[date]) -> list[str]:
    return [f"{d.month}月{d.day}日" for d in days]


def build_plan(day: date, overtime_week: bool) -> DayPlan:
    weekday = day.weekday()
    is_overtime_saturday = day in overtime_saturdays_for_month(day.year, day.month)

    if weekday == 0:
        return DayPlan(
            overtime="17:45-18:45，加班1h",
            gym="健身",
            meals="回家吃或加热周日准备好的饭菜，健身后可以加一顿简单易消化的加餐",
            focus="健身日，吃饭正常，不做大批量备餐",
        )
    if weekday == 1:
        return DayPlan(
            overtime="17:45-18:45，加班1h",
            gym="不练",
            meals="吃周日准备好的饭菜；晚上准备周三午餐、晚餐，以及周三晚回家快炒的食材",
            focus="主备餐日，把周三的饭菜安排稳",
        )
    if weekday == 2:
        return DayPlan(
            overtime="17:45-18:45，加班1h",
            gym="健身",
            meals="回家吃或快炒周二准备好的饭菜，健身后按饥饿程度补一顿",
            focus="健身日，正常吃晚饭/加餐，不做重度备餐",
        )
    if weekday == 3:
        saturday_prep = "，同时准备周六加班带饭" if overtime_week else ""
        return DayPlan(
            overtime="17:45-18:45，加班1h",
            gym="不练",
            meals=f"准备周五午餐和晚餐{saturday_prep}",
            focus="主备餐日，给周五和周末留缓冲",
        )
    if weekday == 4:
        return DayPlan(
            overtime="17:45-18:45，加班1h",
            gym="健身",
            meals="回家吃周四准备好的饭菜，最多做简单加餐，尽量早点睡",
            focus="健身日，不安排复杂做饭",
        )
    if weekday == 5 and is_overtime_saturday:
        return DayPlan(
            overtime="加班8h，尽量白天完成",
            gym="不练",
            meals="带周四/周五准备好的饭；晚上放松吃一顿，不硬撑训练",
            focus="本月加班周六，完成8h后恢复体力",
        )
    if weekday == 5:
        return DayPlan(
            overtime="不加班",
            gym="健身",
            meals="正常吃饭，可顺手补一点下周食材",
            focus="普通周六，训练和放松优先",
        )

    if overtime_week:
        return DayPlan(
            overtime="不加班",
            gym="健身",
            meals="训练后吃饭；晚上准备周一晚餐，以及周二午餐和晚餐",
            focus="补周六没练的训练，同时完成下周前两天备餐",
        )
    return DayPlan(
        overtime="不加班",
        gym="不练",
        meals="准备周一晚餐，以及周二午餐和晚餐",
        focus="休息/学习/出门都可以，晚上把周一周二饭菜备好",
    )


def build_notice(day: date) -> Notice:
    overtime_week, week_reason = is_overtime_week(day)
    plan = build_plan(day, overtime_week)
    overtime_saturdays = overtime_saturdays_for_month(day.year, day.month)
    week_type = "加班周" if overtime_week else "普通周"
    weekday = WEEKDAY_CN[day.weekday()]
    month_week = month_week_number(day)
    reminder = "健身日也要吃晚饭或加餐；只是把大批量备餐放到周二、周四、周日。"

    text = "\n".join(
        [
            f"早上好，今天是 {day.year}年{day.month}月{day.day}日，{day.month}月第{month_week}周 {weekday}。",
            f"本周类型：{week_type}（{week_reason}）。",
            "",
            "今日安排：",
            f"- 加班：{plan.overtime}",
            f"- 健身：{plan.gym}",
            f"- 吃饭/备餐：{plan.meals}",
            f"- 晚上重点：{plan.focus}",
            "",
            f"本月加班周六：{'、'.join(format_dates(overtime_saturdays))}",
            "月度加班预估：工作日约20h + 两个周六16h = 36h。",
            "",
            f"提醒：{reminder}",
        ]
    )

    return Notice(
        date=day.isoformat(),
        month_week=month_week,
        weekday=weekday,
        week_type=week_type,
        week_reason=week_reason,
        overtime_saturdays=format_dates(overtime_saturdays),
        plan=plan,
        reminder=reminder,
        text=text,
    )


def main() -> None:
    args = parse_args()
    day = parse_date(args.date)
    notice = build_notice(day)
    if args.json:
        print(json.dumps(asdict(notice), ensure_ascii=False, indent=2))
        return
    print(notice.text)


if __name__ == "__main__":
    main()
