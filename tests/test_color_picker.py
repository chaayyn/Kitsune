"""
Unit tests for Color Picker calculations and formatting.
"""

import unittest
from vorssaint.modules.color_picker.module import ColorPickerModule


class DummyApp:
    def __init__(self):
        self.env = None
        self.config_manager = None

    def clipboard(self):
        return None


class TestColorPicker(unittest.TestCase):
    def setUp(self):
        self.app = DummyApp()
        self.module = ColorPickerModule(self.app)

    def test_calculate_formats_pure_red(self):
        rgb, hsl = self.module.calculate_formats("#FF0000")
        self.assertEqual(rgb, "rgb(255, 0, 0)")
        self.assertEqual(hsl, "hsl(0°, 100%, 50%)")

    def test_calculate_formats_pure_blue(self):
        rgb, hsl = self.module.calculate_formats("#0000FF")
        self.assertEqual(rgb, "rgb(0, 0, 255)")
        self.assertEqual(hsl, "hsl(240°, 100%, 50%)")

    def test_calculate_formats_white_and_black(self):
        rgb_w, hsl_w = self.module.calculate_formats("#FFFFFF")
        self.assertEqual(rgb_w, "rgb(255, 255, 255)")

        rgb_b, hsl_b = self.module.calculate_formats("#000000")
        self.assertEqual(rgb_b, "rgb(0, 0, 0)")


if __name__ == "__main__":
    unittest.main()
