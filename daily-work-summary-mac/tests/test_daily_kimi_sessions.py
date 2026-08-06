#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from daily_kimi_sessions import (  # noqa: E402
    iter_in_scope_main_wires,
    iter_main_wire_paths,
    resolve_session_workdir,
    scan_wire_file,
)


def ms_at(day, hour=12, minute=0):
    """生成指定 UTC 日期的 epoch 毫秒时间戳，用于构造测试记录。"""
    dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


class KimiSessionExtractorTest(unittest.TestCase):
    def write_jsonl(self, path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )

    def test_iter_main_wire_paths_skips_subagent_wires(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / ".kimi-code"
            main_path = home / "sessions" / "wd_project_x" / "session_abc" / "agents" / "main" / "wire.jsonl"
            subagent_paths = [
                home / "sessions" / "wd_project_x" / "session_abc" / "agents" / "agent-0" / "wire.jsonl",
                home / "sessions" / "wd_project_x" / "session_abc" / "agents" / "agent-1" / "wire.jsonl",
            ]
            self.write_jsonl(main_path, [{"type": "metadata"}])
            for path in subagent_paths:
                self.write_jsonl(path, [{"type": "metadata"}])

            self.assertEqual(list(iter_main_wire_paths(home)), [main_path])

    def test_scan_wire_file_extracts_user_and_assistant_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / ".kimi-code"
            wire = home / "sessions" / "wd_project_x" / "session_abc" / "agents" / "main" / "wire.jsonl"
            day = date(2026, 8, 5)
            records = [
                {"type": "metadata"},
                {
                    "type": "turn.prompt",
                    "input": [{"type": "text", "text": "你好，帮我看看这个项目"}],
                    "origin": {"kind": "user"},
                    "time": ms_at(day, 9),
                },
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "content.part",
                        "stepUuid": "step-1",
                        "turnId": "0",
                        "part": {"type": "think", "think": "内部推理不输出"},
                    },
                    "time": ms_at(day, 9, 1),
                },
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "content.part",
                        "stepUuid": "step-1",
                        "turnId": "0",
                        "part": {"type": "text", "text": "好的，我来分析。"},
                    },
                    "time": ms_at(day, 9, 2),
                },
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "tool.call",
                        "name": "Read",
                        "args": {"path": "README.md"},
                    },
                    "time": ms_at(day, 9, 3),
                },
                {
                    "type": "context.append_message",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "<system-reminder>忽略我</system-reminder>"}],
                        "origin": {"kind": "injection"},
                    },
                    "time": ms_at(day, 9, 4),
                },
                {
                    "type": "turn.steer",
                    "input": [{"type": "text", "text": "<notification>后台任务完成</notification>"}],
                    "origin": {"kind": "background_task"},
                    "time": ms_at(day, 9, 5),
                },
            ]
            self.write_jsonl(wire, records)

            events = scan_wire_file(
                wire,
                day,
                day,
                "/Users/torchz/CetWorkspace/SodaLowCode/LowCode-Agent-Service",
            )

            self.assertEqual(
                [(ev["role"], ev["text"]) for ev in events],
                [("user", "你好，帮我看看这个项目"), ("assistant", "好的，我来分析。")],
            )
            self.assertTrue(all(ev["project"] == "/Users/torchz/CetWorkspace/SodaLowCode/LowCode-Agent-Service" for ev in events))

    def test_scan_merges_text_parts_of_same_step(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wire = Path(temp_dir) / "wire.jsonl"
            day = date(2026, 8, 5)
            records = [
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "content.part",
                        "stepUuid": "step-1",
                        "turnId": "0",
                        "part": {"type": "text", "text": "第一部分"},
                    },
                    "time": ms_at(day, 10),
                },
                {
                    "type": "context.append_loop_event",
                    "event": {
                        "type": "content.part",
                        "stepUuid": "step-1",
                        "turnId": "0",
                        "part": {"type": "text", "text": "第二部分"},
                    },
                    "time": ms_at(day, 10, 1),
                },
            ]
            self.write_jsonl(wire, records)

            events = scan_wire_file(
                wire,
                day,
                day,
                "/Users/torchz/CetWorkspace/project",
            )

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["text"], "第一部分\n\n第二部分")

    def test_iter_in_scope_main_wires_filters_by_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / ".kimi-code"
            in_scope = home / "sessions" / "wd_in_scope" / "session_aaa" / "agents" / "main" / "wire.jsonl"
            out_scope = home / "sessions" / "wd_out_scope" / "session_bbb" / "agents" / "main" / "wire.jsonl"
            self.write_jsonl(in_scope, [{"type": "metadata"}])
            self.write_jsonl(out_scope, [{"type": "metadata"}])
            workspace_roots = {
                "wd_in_scope": "/Users/torchz/CetWorkspace/project",
                "wd_out_scope": "/Users/torchz/myprojects/other",
            }

            scoped = list(
                iter_in_scope_main_wires(
                    home,
                    ["/Users/torchz/CetWorkspace"],
                    workspace_roots,
                )
            )

            self.assertEqual(scoped, [(in_scope, "/Users/torchz/CetWorkspace/project")])

    def test_scan_filters_by_date_range(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wire = Path(temp_dir) / "wire.jsonl"
            day = date(2026, 8, 5)
            records = [
                {
                    "type": "turn.prompt",
                    "input": [{"type": "text", "text": "只属于指定目录"}],
                    "origin": {"kind": "user"},
                    "time": ms_at(day, 11),
                }
            ]
            self.write_jsonl(wire, records)

            # 时间不在日期范围内 -> 跳过
            self.assertEqual(
                scan_wire_file(
                    wire,
                    date(2026, 8, 1),
                    date(2026, 8, 2),
                    "/Users/torchz/CetWorkspace/project",
                ),
                [],
            )

    def test_resolve_session_workdir_uses_state_then_workspaces(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / ".kimi-code"
            session_dir = home / "sessions" / "wd_project_x" / "session_abc"
            session_dir.mkdir(parents=True)
            workspace_roots = {"wd_project_x": "/Users/torchz/CetWorkspace/project"}

            # 无 state.json 时回退 workspaces.json 映射
            self.assertEqual(
                resolve_session_workdir(session_dir, workspace_roots),
                "/Users/torchz/CetWorkspace/project",
            )

            # session_index 兜底（state 与 workspaces 都没有时）
            self.assertEqual(
                resolve_session_workdir(
                    session_dir,
                    {},
                    {"session_abc": "/Users/torchz/CetWorkspace/from-index"},
                ),
                "/Users/torchz/CetWorkspace/from-index",
            )

            # state.json 优先
            (session_dir / "state.json").write_text(
                json.dumps({"workDir": "/Users/torchz/CetWorkspace/other", "title": "标题"}),
                encoding="utf-8",
            )
            self.assertEqual(
                resolve_session_workdir(session_dir, workspace_roots),
                "/Users/torchz/CetWorkspace/other",
            )


if __name__ == "__main__":
    unittest.main()
