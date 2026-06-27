#!/usr/bin/env python3
"""Offline tests for the pure formatting/writing logic of bot.py.

No network or Telegram token required:  python3 test_bot.py
"""

import os
import tempfile
import unittest
from datetime import datetime

import bot


class FormatEntryTests(unittest.TestCase):
    def setUp(self):
        self.dt = datetime(2026, 6, 27, 9, 5)
        self.template = bot.DEFAULT_CONFIG["template"]
        self.fmt = bot.DEFAULT_CONFIG["datetime_format"]

    def test_text_entry_matches_guide_shape(self):
        entry = bot.format_entry(self.template, self.dt, self.fmt, "идея для контента")
        self.assertEqual(
            entry,
            "## 2026-06-27 09:05 · telegram\nидея для контента\n\n---\n",
        )

    def test_voice_transcript_is_appended(self):
        entry = bot.format_entry(
            self.template, self.dt, self.fmt, "", "\nрасшифровка голоса"
        )
        self.assertIn("\nрасшифровка голоса", entry)
        self.assertTrue(entry.startswith("## 2026-06-27 09:05 · telegram"))

    def test_braces_in_content_are_literal(self):
        entry = bot.format_entry(self.template, self.dt, self.fmt, "use {datetime} here")
        self.assertIn("use {datetime} here", entry)


class AppendInboxTests(unittest.TestCase):
    def test_creates_dirs_and_separates_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "_BRAIN", "Инбокс", "inbox.md")
            bot.append_inbox(inbox, "## a\nfirst\n\n---\n")
            bot.append_inbox(inbox, "## b\nsecond\n\n---\n")
            with open(inbox, encoding="utf-8") as f:
                data = f.read()
            self.assertTrue(os.path.exists(inbox))
            self.assertLess(data.index("first"), data.index("second"))
            self.assertIn("first\n\n---\n\n## b", data)  # blank-line gap between blocks


class ConfigTests(unittest.TestCase):
    def test_deep_merge_preserves_unset_voice_keys(self):
        merged = bot.deep_merge(
            bot.DEFAULT_CONFIG, {"voice": {"transcribe": True}}
        )
        self.assertTrue(merged["voice"]["transcribe"])
        self.assertIn("save", merged["voice"])  # not clobbered by partial override

    def test_is_allowed_open_and_restricted(self):
        self.assertTrue(bot.is_allowed({"allowed_user_ids": []}, {"from": {"id": 1}}))
        self.assertTrue(bot.is_allowed({"allowed_user_ids": [1]}, {"from": {"id": 1}}))
        self.assertFalse(bot.is_allowed({"allowed_user_ids": [1]}, {"from": {"id": 2}}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
