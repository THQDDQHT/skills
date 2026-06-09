---
name: daily-schedule-notice
description: Use when generating the user's daily Chinese schedule notification for overtime, gym, meals, and meal prep. Intended for OpenClaw or another scheduler to run every morning at 08:00 and tell the user the current month/week/day plus today's plan.
---

# Daily Schedule Notice

## Purpose

Generate a concise Simplified Chinese daily reminder for the user's monthly overtime, gym, meal-prep plan, and diligence-time progress.

This skill is meant to be invoked by OpenClaw from a scheduled task every day at 08:00. Prefer the bundled script for deterministic date calculation instead of reasoning from memory.

## Plan Rules

- Monthly overtime target: `36h`.
- Workday baseline: Monday to Friday, `17:45-18:45`, counted as `1h`.
- Overtime Saturdays: the 2nd and 4th Saturday of each calendar month, `8h` each.
- Monthly estimate: workdays `20h` plus two Saturdays `16h` equals about `36h`.
- Normal week workout days: Monday, Wednesday, Friday, Saturday.
- Overtime-Saturday week workout days: Monday, Wednesday, Friday, Sunday.
- Heavy meal prep days: Tuesday, Thursday, Sunday.
- Workout days still include dinner or a post-workout meal. The rule is not "do not eat"; it is "do not do heavy batch meal prep".

## Diligence Statistics

The bundled script calls the external read-only diligence API and includes:

- Current month's actual diligence hours.
- Current month's target progress and delta.
- Current year's target progress and delta.

Default runtime URL:

```text
http://127.0.0.0:15000/api/external/diligence
```

The script uses the fixed Bearer Token configured in the script. Do not put the token in the notification text.

For remote verification, override the URL:

```bash
python <skill-dir>/scripts/daily_schedule_notice.py \
  --api-url https://cetworkovertime.q2qs.top/api/external/diligence
```

If the API fails, still return the daily schedule and add a short failure line under `勤奋统计`.

## Meal Rules

- Sunday prepares Monday dinner plus Tuesday lunch and dinner.
- Monday: work overtime, train, eat or heat Sunday's prepared food, at most add a simple extra meal.
- Tuesday: work overtime, no gym, eat Sunday's prepared food, then prepare Wednesday lunch/dinner and quick-cook ingredients for Wednesday night.
- Wednesday: work overtime, train, eat or quick-cook Tuesday's prepared food, no heavy batch prep.
- Thursday: work overtime, no gym, prepare Friday lunch/dinner. If this week has an overtime Saturday, also prepare Saturday's packed meal.
- Friday: work overtime, train, eat Thursday's prepared food, avoid complex cooking and sleep earlier.
- Normal Saturday: no overtime, train, relax, optionally restock ingredients.
- Overtime Saturday: work `8h`, no gym, bring prepared food, relax at night.
- Sunday: if the previous day was an overtime Saturday, train on Sunday and still prepare next week's Monday/Tuesday meals; otherwise rest, study, go out, and prepare next week's meals.

## How To Generate A Notice

Run:

```bash
python <skill-dir>/scripts/daily_schedule_notice.py
```

For testing a specific date:

```bash
python <skill-dir>/scripts/daily_schedule_notice.py --date 2026-06-09
```

For machine-readable output:

```bash
python <skill-dir>/scripts/daily_schedule_notice.py --json
```

Use the script's plain-text output as the final notification. Do not add unrelated motivational text.

## Notification Style

- Always use Simplified Chinese.
- Keep it practical and direct.
- Include:
  - Gregorian date.
  - Month week number and weekday.
  - Whether this is a normal week or an overtime-Saturday week.
  - Today's overtime, gym, meal, and meal-prep arrangement.
  - Current month's two overtime Saturdays.
  - Diligence statistics for the current month and current year.
- If today is an overtime Saturday, make `8h` overtime the most prominent item.
- If today is a workout day, explicitly remind that the user can and should eat dinner or a simple post-workout meal.
