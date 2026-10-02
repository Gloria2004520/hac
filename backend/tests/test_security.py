import socket
import unittest
from unittest.mock import patch

from app.security import UnsafeURLError, is_allowed_host, validate_source_url


class AllowedHostTests(unittest.TestCase):
    domains = ("youtube.com", "youtu.be", "bilibili.com")

    def test_exact_domain_is_allowed(self):
        self.assertTrue(is_allowed_host("youtube.com", self.domains))

    def test_subdomain_is_allowed(self):
        self.assertTrue(is_allowed_host("www.bilibili.com", self.domains))

    def test_suffix_trick_is_rejected(self):
        self.assertFalse(is_allowed_host("youtube.com.example.org", self.domains))

    def test_prefix_trick_is_rejected(self):
        self.assertFalse(is_allowed_host("evilyoutube.com", self.domains))

    @patch("app.security.socket.getaddrinfo")
    def test_trusted_platform_allows_proxy_fake_ip(self, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.1", 0))
        ]
        url = "https://www.youtube.com/watch?v=abc"
        self.assertEqual(validate_source_url(url, self.domains), url)
        getaddrinfo.assert_not_called()

    @patch("app.security.socket.getaddrinfo")
    def test_custom_domain_still_rejects_private_resolution(self, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))
        ]
        with self.assertRaises(UnsafeURLError):
            validate_source_url("https://video.example.com/watch", ("example.com",))


if __name__ == "__main__":
    unittest.main()
