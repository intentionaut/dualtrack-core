import unittest
from textkit import slugify, truncate


class TextkitTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_truncate(self):
        self.assertEqual(truncate("abcdef", 3), "abc...")
