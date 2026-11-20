"""
Unit tests for ConfigManager.
"""

import tempfile
import unittest
from pathlib import Path
from vorssaint.core.config import ConfigManager


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cfg_dir = Path(self.temp_dir.name)
        self.config = ConfigManager(config_dir=self.cfg_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_values(self):
        self.assertEqual(self.config.get_value("theme"), "dark")
        self.assertTrue(self.config.is_module_enabled("keep_awake"))

    def test_set_and_persist(self):
        self.config.set_value("theme", "light")
        self.config.set_module_enabled("keep_awake", False)

        # Reload from disk
        reloaded = ConfigManager(config_dir=self.cfg_dir)
        self.assertEqual(reloaded.get_value("theme"), "light")
        self.assertFalse(reloaded.is_module_enabled("keep_awake"))


if __name__ == "__main__":
    unittest.main()
