"""
Unit tests for Clean URL module.
"""

import unittest
from vorssaint.modules.clean_url.module import CleanUrlModule


class DummyApp:
    def clipboard(self):
        return None


class TestCleanUrl(unittest.TestCase):
    def setUp(self):
        self.app = DummyApp()
        self.module = CleanUrlModule(self.app)

    def test_strip_utm_parameters(self):
        url = "https://example.com/article?utm_source=twitter&utm_medium=social&utm_campaign=launch"
        clean, was_cleaned, removed = self.module.clean_url(url)
        self.assertTrue(was_cleaned)
        self.assertEqual(clean, "https://example.com/article")
        self.assertIn("utm_source", removed)
        self.assertIn("utm_medium", removed)
        self.assertIn("utm_campaign", removed)

    def test_preserve_legitimate_parameters(self):
        url = "https://example.com/search?q=linux+tray&page=2&fbclid=IwAR12345"
        clean, was_cleaned, removed = self.module.clean_url(url)
        self.assertTrue(was_cleaned)
        self.assertIn("q=linux+tray", clean)
        self.assertIn("page=2", clean)
        self.assertNotIn("fbclid", clean)
        self.assertIn("fbclid", removed)

    def test_non_url_text(self):
        text = "Hello world! This is just some random text with utm_source=foo."
        clean, was_cleaned, removed = self.module.clean_url(text)
        self.assertFalse(was_cleaned)
        self.assertEqual(clean, text)
        self.assertEqual(removed, [])

    def test_youtube_tracking_si(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=abcdef12345"
        clean, was_cleaned, removed = self.module.clean_url(url)
        self.assertTrue(was_cleaned)
        self.assertEqual(clean, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertIn("si", removed)


if __name__ == "__main__":
    unittest.main()
