"""
Unit tests for Clipboard SQLite Storage.
"""

import tempfile
import unittest
from pathlib import Path
from kitsune.modules.clipboard.storage import ClipboardStorage


class TestClipboardStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_clipboard.sqlite3"
        self.storage = ClipboardStorage(db_path=db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_and_retrieve(self):
        self.storage.add_entry("First snippet")
        self.storage.add_entry("Second snippet")

        items = self.storage.get_recent(limit=10)
        self.assertEqual(len(items), 2)
        # Most recent first
        self.assertEqual(items[0][1], "Second snippet")
        self.assertEqual(items[1][1], "First snippet")

    def test_retention_limit(self):
        limit = 5
        for i in range(10):
            self.storage.add_entry(f"Snippet {i}", limit=limit)

        items = self.storage.get_recent(limit=100)
        self.assertEqual(len(items), limit)
        self.assertEqual(items[0][1], "Snippet 9")

    def test_search(self):
        self.storage.add_entry("Python 3 snippet")
        self.storage.add_entry("Rust code snippet")
        self.storage.add_entry("Unrelated line")

        results = self.storage.get_recent(limit=10, search_query="snippet")
        self.assertEqual(len(results), 2)

    def test_clear(self):
        self.storage.add_entry("Snippet to clear")
        self.storage.clear()
        items = self.storage.get_recent()
        self.assertEqual(len(items), 0)


if __name__ == "__main__":
    unittest.main()
