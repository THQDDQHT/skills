#!/usr/bin/env python3
"""Generate the user's daily overtime, workout, and meal-prep notice."""

from __future__ import annotations

import argparse
import calendar
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_DILIGENCE_API_URL = "http://127.0.0.0:15000/api/external/diligence"
EXTERNAL_API_TOKEN = "xjiahfiahfaidhwadgaufgaudgwaufgvb"
HTTP_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class DayPlan:
    overtime: str
    gym: str
    meals: str
    focus: str


@dataclass(frozen=True)
class DiligenceNotice:
    ok: bool
    source: str | None
    month_text: str
    year_text: str
    error: str | None = None


@dataclass(frozen=True)
class Notice:
    date: str
    month_week: int
    weekday: str
    week_type: str
    week_reason: str
    overtime_saturdays: list[str]
    plan: DayPlan
    diligence: DiligenceNotice
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
    parser.add_argument(
        "--api-url",
        default=DEFAULT_DILIGENCE_API_URL,
        help="Diligence statistics API URL.",
    )
    parser.add_argument(
        "--skip-diligence",
        action="store_true",
        help="Do not call the diligence statistics API.",
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


def format_hours(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0h"
    text = f"{number:.1f}".rstrip("0").rstrip(".")
    return f"{text}h"


def format_delta(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0h"
    if number > 0:
        return f"超出 {format_hours(number)}"
    if number < 0:
        return f"还差 {format_hours(abs(number))}"
    return "刚好达标"


def format_percent(hours: Any, target: Any) -> str:
    try:
        hours_number = float(hours)
        target_number = float(target)
    except (TypeError, ValueError):
        return "0%"
    if target_number <= 0:
        return "0%"
    return f"{hours_number / target_number * 100:.1f}%"


def fetch_diligence_data(api_url: str) -> dict[str, Any]:
    request = Request(
        api_url,
        headers={
            "Authorization": f"Bearer {EXTERNAL_API_TOKEN}",
            "Accept": "application/json",
            "User-Agent": "daily-schedule-notice/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(format_http_error(exc.code, body)) from exc
    except URLError as exc:
        raise RuntimeError(f"网络请求失败：{exc.reason}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("接口返回的不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("接口返回结构不是对象")
    return data


def format_http_error(status_code: int, body: str) -> str:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        message = data.get("error") or data.get("title") or data.get("detail")
        error_name = data.get("error_name") or data.get("error_code")
        if message and error_name:
            return f"HTTP {status_code}: {message}（{error_name}）"
        if message:
            return f"HTTP {status_code}: {message}"

    compact_body = " ".join(body.split())
    if len(compact_body) > 120:
        compact_body = compact_body[:117] + "..."
    return f"HTTP {status_code}: {compact_body}"


def empty_diligence_notice(error: str) -> DiligenceNotice:
    return DiligenceNotice(
        ok=False,
        source=None,
        month_text="当月加班时长：暂未获取到统计数据。",
        year_text="年度目标完成：暂未获取到统计数据。",
        error=error,
    )


def build_diligence_notice(day: date, api_url: str, skip: bool = False) -> DiligenceNotice:
    if skip:
        return empty_diligence_notice("已跳过勤奋统计 API 请求")

    try:
        data = fetch_diligence_data(api_url)
    except RuntimeError as exc:
        return empty_diligence_notice(str(exc))

    if not data.get("ok"):
        return empty_diligence_notice(str(data.get("error") or "接口返回失败"))

    years = data.get("years")
    if not isinstance(years, dict):
        return empty_diligence_notice("接口响应缺少 years 对象")

    year_data = years.get(str(day.year))
    if not isinstance(year_data, dict):
        return empty_diligence_notice(f"接口响应中没有 {day.year} 年统计")

    months = year_data.get("months")
    if not isinstance(months, list):
        return empty_diligence_notice(f"接口响应中没有 {day.year} 年月份列表")

    month_data = next(
        (
            item
            for item in months
            if isinstance(item, dict)
            and item.get("month") == day.month
        ),
        None,
    )
    if not month_data:
        month_data = {
            "hours": 0,
            "target": data.get("target_hours", 36),
            "delta": -float(data.get("target_hours", 36)),
            "entries": 0,
        }

    month_text = (
        f"当月加班时长：{format_hours(month_data.get('hours'))} / "
        f"目标 {format_hours(month_data.get('target'))}，"
        f"完成 {format_percent(month_data.get('hours'), month_data.get('target'))}，"
        f"{format_delta(month_data.get('delta'))}，"
        f"记录 {month_data.get('entries', 0)} 条。"
    )
    yearly_target = 36 * 12
    year_text = (
        f"年度目标完成：{format_hours(year_data.get('total_hours'))} / "
        f"{format_hours(yearly_target)}，"
        f"完成 {format_percent(year_data.get('total_hours'), yearly_target)}，"
        f"{format_delta(year_data.get('total_hours') - yearly_target)}。"
    )

    return DiligenceNotice(
        ok=True,
        source=str(data.get("source") or ""),
        month_text=month_text,
        year_text=year_text,
    )


def build_notice(day: date, api_url: str, skip_diligence: bool = False) -> Notice:
    overtime_week, week_reason = is_overtime_week(day)
    plan = build_plan(day, overtime_week)
    diligence = build_diligence_notice(day, api_url, skip_diligence)
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
            "勤奋统计：",
            f"- {diligence.month_text}",
            f"- {diligence.year_text}",
            *([f"- 获取状态：{diligence.error}"] if diligence.error else []),
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
        diligence=diligence,
        reminder=reminder,
        text=text,
    )


def main() -> None:
    args = parse_args()
    day = parse_date(args.date)
    notice = build_notice(day, args.api_url, args.skip_diligence)
    if args.json:
        print(json.dumps(asdict(notice), ensure_ascii=False, indent=2))
        return
    print(notice.text)


if __name__ == "__main__":
    main()
