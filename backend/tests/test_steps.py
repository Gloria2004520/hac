import unittest
from types import SimpleNamespace

from app.breakdown import MOCK_BASIS, build_steps, mock_note
from app.coach import _normalize_verdict, parse_loose_json


class BreakdownTests(unittest.TestCase):
    def test_every_step_carries_a_checkpoint(self):
        steps = build_steps(None)
        self.assertGreaterEqual(len(steps), 3)
        for index, step in enumerate(steps):
            self.assertEqual(step["position"], index)
            self.assertTrue(step["title"].strip())
            self.assertTrue(step["summary"].strip())
            # 没有自检问题和合格标准，「过了没有」就没法判定
            self.assertTrue(step["question"].strip())
            self.assertTrue(step["criteria"].strip())

    def test_steps_are_marked_as_mock(self):
        steps = build_steps(None)
        self.assertTrue(all(step["basis"] == MOCK_BASIS for step in steps))

    def test_no_placeholder_timestamps_without_duration(self):
        steps = build_steps(None)
        self.assertTrue(all(step["start_seconds"] is None for step in steps))

    def test_timestamps_only_use_total_duration(self):
        steps = build_steps(SimpleNamespace(duration_seconds=600))
        self.assertEqual(steps[0]["start_seconds"], 0)
        self.assertEqual(steps[-1]["end_seconds"], 600)
        starts = [step["start_seconds"] for step in steps]
        self.assertEqual(starts, sorted(starts))

    def test_note_refuses_to_claim_parsing(self):
        note = mock_note(SimpleNamespace(duration_seconds=600))
        self.assertIn("模拟", note)
        self.assertIn("没有读画面", note)
        self.assertIn("别把它当成这个视频的解析结果", note)


class LooseJsonTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_loose_json('{"verdict":"pass"}'), {"verdict": "pass"})

    def test_code_fence_and_chatter(self):
        raw = '好的，我看看：\n```json\n{"verdict":"retry","reason":"还差一步"}\n```\n希望有帮助'
        self.assertEqual(parse_loose_json(raw), {"verdict": "retry", "reason": "还差一步"})

    def test_nested_json_string(self):
        self.assertEqual(parse_loose_json('"{\\"verdict\\":\\"unclear\\"}"'), {"verdict": "unclear"})

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_loose_json("这一步你做得不错，继续加油。"))
        self.assertIsNone(parse_loose_json(""))


class VerdictTests(unittest.TestCase):
    def test_aliases(self):
        for value in ("pass", "PASS", "通过", "过了", "做到了"):
            self.assertEqual(_normalize_verdict(value), "pass")
        for value in ("retry", "fail", "不通过", "还没过"):
            self.assertEqual(_normalize_verdict(value), "retry")
        for value in ("unclear", "说不清", "不确定"):
            self.assertEqual(_normalize_verdict(value), "unclear")

    def test_unknown_verdict_is_rejected(self):
        self.assertIsNone(_normalize_verdict("maybe"))
        self.assertIsNone(_normalize_verdict(None))
        self.assertIsNone(_normalize_verdict(1))


if __name__ == "__main__":
    unittest.main()
