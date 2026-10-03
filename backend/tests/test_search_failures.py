import unittest

from app.search import SearchUpstreamError, _failure_reason, _payload_or_failure, _tail, _timeout_reason

# 真实场景里 yt-dlp 打出来的报错（本机网络到不了 YouTube 时）
UNREACHABLE_STDERR = """
WARNING: [youtube:search] HTTPSConnectionPool(host='www.youtube.com', port=443): Read timed out. (read timeout=10.0). Retrying (1/3)...
ERROR: query "虾仁滑蛋 教程" page 1: Unable to download API page: HTTPSConnectionPool(host='www.youtube.com', port=443): Read timed out. (read timeout=10.0)
"""


class FailureReasonTests(unittest.TestCase):
    def test_unreachable_says_so_instead_of_pretending(self):
        reason = _failure_reason(UNREACHABLE_STDERR)
        self.assertIn("连不上 YouTube", reason)
        # 必须给出可执行的替代路径，而不是只说「失败了」
        self.assertIn("粘贴视频链接", reason)

    def test_rate_limit_is_reported_as_rate_limit(self):
        reason = _failure_reason('ERROR: HTTP Error 429: Too Many Requests')
        self.assertIn("限制了搜索请求", reason)
        self.assertNotIn("连不上", reason)

    def test_unknown_failure_is_not_dressed_up(self):
        reason = _failure_reason("ERROR: something odd happened")
        self.assertIn("检索失败", reason)
        self.assertIn("something odd happened", reason)

    def test_tail_is_bounded(self):
        self.assertLessEqual(len(_tail("x" * 5000)), 300)
        self.assertEqual(_tail(""), "")

    def test_timeout_reason_mentions_seconds(self):
        self.assertIn("等了 25 秒", _timeout_reason("", 25))
        self.assertIn("连不上 YouTube", _timeout_reason(UNREACHABLE_STDERR, 25))


class PayloadVerdictTests(unittest.TestCase):
    """yt-dlp 失败时照样吐 JSON，这里必须把它判成失败。"""

    FAILED_STDOUT = (
        '{"id": "\\u867e\\u4ec1\\u6ed1\\u86cb \\u6559\\u7a0b", "_type": "playlist", '
        '"entries": [null], "webpage_url": "ytsearch20:\\u867e\\u4ec1\\u6ed1\\u86cb \\u6559\\u7a0b"}'
    )

    def test_null_entries_with_nonzero_returncode_is_a_failure(self):
        with self.assertRaises(SearchUpstreamError) as ctx:
            _payload_or_failure(self.FAILED_STDOUT, UNREACHABLE_STDERR, 1)
        self.assertIn("连不上 YouTube", str(ctx.exception))

    def test_genuinely_empty_result_is_not_a_failure(self):
        # 返回码 0 + 真的没结果：这是「没搜到」，不是「失败了」
        payload = _payload_or_failure('{"entries": []}', "", 0)
        self.assertEqual(payload["entries"], [])

    def test_valid_results_pass_through(self):
        stdout = '{"entries": [{"id": "abc123", "title": "番茄炒蛋"}]}'
        self.assertEqual(len(_payload_or_failure(stdout, "", 0)["entries"]), 1)

    def test_empty_stdout_is_a_failure(self):
        with self.assertRaises(SearchUpstreamError):
            _payload_or_failure("", UNREACHABLE_STDERR, 1)

    def test_unparsable_stdout_is_a_failure(self):
        with self.assertRaises(SearchUpstreamError):
            _payload_or_failure("not json at all", "", 0)


if __name__ == "__main__":
    unittest.main()
