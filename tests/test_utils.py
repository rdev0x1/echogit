import unittest

from echogit.utils import _is_local_peer


class TestUtils(unittest.TestCase):
    def test_is_local_peer_localhost(self):
        self.assertTrue(_is_local_peer("localhost"))
        self.assertTrue(_is_local_peer("127.0.0.1"))
        self.assertTrue(_is_local_peer("::1"))

    def test_is_local_peer_invalid_host(self):
        self.assertFalse(_is_local_peer("example.invalid"))


if __name__ == "__main__":
    unittest.main()
