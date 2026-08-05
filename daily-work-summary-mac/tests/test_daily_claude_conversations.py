#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from daily_claude_conversations import (  # noqa: E402
    iter_main_transcript_paths,
    scan_file,
)


class ClaudeConversationSubagentFilterTest(unittest.TestCase):
    def make_record(self, text, **metadata):
        record = {
            "type": "user",
            "timestamp": "2026-08-05T00:00:00+00:00",
            "cwd": "/Users/torchz/CetWorkspace/project",
            "sessionId": "session-1",
            "message": {
                "role": "user",
                "content": text,
            },
        }
        record.update(metadata)
        return record

    def write_jsonl(self, path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )

    def test_iter_main_transcript_paths_skips_subagents_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            main_path = root / "project" / "main.jsonl"
            subagent_path = root / "project" / "session" / "subagents" / "agent-a1.jsonl"
            self.write_jsonl(main_path, [self.make_record("主会话")])
            self.write_jsonl(subagent_path, [self.make_record("子代理")])

            self.assertEqual(list(iter_main_transcript_paths(root)), [main_path])

    def test_scan_file_skips_sidechain_and_agent_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "main.jsonl"
            self.write_jsonl(
                transcript,
                [
                    self.make_record("主会话"),
                    self.make_record("sidechain 子代理", isSidechain=True),
                    self.make_record("agentId 子代理", agentId="agent-a1"),
                ],
            )

            events = scan_file(
                transcript,
                date(2026, 8, 5),
                date(2026, 8, 5),
                ["/Users/torchz/CetWorkspace"],
            )

            self.assertEqual([event["text"] for event in events], ["主会话"])


if __name__ == "__main__":
    unittest.main()
