import unittest

from setuptools import find_packages


class TestPackaging(unittest.TestCase):
    def test_setuptools_finds_runtime_packages(self):
        packages = set(find_packages())

        self.assertIn("echogit", packages)
        self.assertIn("echogit.core", packages)
        self.assertIn("echogit.gui", packages)
        self.assertIn("echogit.sync", packages)


if __name__ == "__main__":
    unittest.main()
