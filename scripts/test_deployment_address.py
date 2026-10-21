#!/usr/bin/env python3
"""Unit tests for deployment address validation."""

import unittest

from deployment_address import is_placeholder


class TestIsPlaceholder(unittest.TestCase):
    def test_detects_placeholder_values(self):
        for value in ("TODO", "tbd", "N/A", "", "CXXXXXX"):
            with self.subTest(value=value):
                self.assertTrue(is_placeholder(value))

    def test_accepts_a_strkey_address(self):
        self.assertFalse(is_placeholder("C" + "A" * 55))

    def test_rejects_malformed_non_placeholder_address(self):
        self.assertTrue(is_placeholder("not-an-address"))


if __name__ == "__main__":
    unittest.main()
