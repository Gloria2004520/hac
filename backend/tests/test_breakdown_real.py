"""真分解这条链路的测试。

刻意分成两半：
  · 纯逻辑（解析 / 挑切点 / 分边界 / 诚实说明）—— 不碰 ffmpeg、不碰网络，必须永远能跑；
  · 「该不该重拆」的判定 —— 这条最容易写错，写错了每次刷新都白烧一遍 ffmpeg。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import breakdown as bd
from app import main as app_main
from app import video_analysis as va
from app.config import settings


# ------------------------------------------------------------- ffmpeg 输出的解析


class ParseSceneOutputTests(unittest.TestCase):
    def test_pairs_scores_with_the_following_frame_time(self):
        # ffmpeg 先打印分数，再打印这一帧的头信息；第一帧的头信息要多出来一个
        raw = "\n".join(
            [
                "frame:0    pts:0       pts_time:0",
                "frame:1    pts:3000    pts_time:0.1",
                "lavfi.scene_score=0.4231",
                "frame:2    pts:6000    pts_time:0.2",
                "lavfi.scene_score=0.9000",
            ]
        )
        self.assertEqual(va.parse_scene_output(raw), [(0.1, 0.4231), (0.2, 0.9)])

    def test_nothing_detected_is_an_empty_list_not_an_error(self):
        self.assertEqual(va.parse_scene_output("frame:0 pts_time:0"), [])

    def test_unbalanced_output_is_an_error_not_a_guess(self):
        raw = "lavfi.scene_score=0.4\nlavfi.scene_score=0.5\nframe:1 pts_time:9"
        with self.assertRaises(va.AnalysisError):
            va.parse_scene_output(raw)


# ------------------------------------------------------------- 挑切点 / 分边界


class PickCutsTests(unittest.TestCase):
    def test_prefers_the_bigger_change_when_two_points_are_too_close(self):
        # 10.0 和 11.0 只差 1 秒，只能留一个 —— 留分数高的那个（11.0）
        scenes = [(10.0, 0.5), (11.0, 0.95), (30.0, 0.6)]
        self.assertEqual(va.pick_cuts(scenes, 60.0, min_gap=8.0), [11.0, 30.0])

    def test_result_is_sorted_by_time_not_by_score(self):
        scenes = [(50.0, 0.4), (10.0, 0.95), (30.0, 0.8)]
        self.assertEqual(va.pick_cuts(scenes, 60.0), [10.0, 30.0, 50.0])

    def test_keeps_a_minimum_gap_so_quick_cuts_do_not_shatter_one_step(self):
        # 12.0 分比 12.5 高，但两者只差 0.5 秒，只该留下更近的那个之一
        scenes = [(12.0, 0.9), (12.5, 0.85), (40.0, 0.7)]
        cuts = va.pick_cuts(scenes, 60.0, min_gap=8.0)
        self.assertEqual(cuts, [12.0, 40.0])

    def test_ignores_weak_and_out_of_range_points(self):
        scenes = [(5.0, 0.1), (70.0, 0.99), (-1.0, 0.99), (0.0, 0.99)]
        self.assertEqual(va.pick_cuts(scenes, 60.0), [])

    def test_caps_the_number_of_cuts(self):
        scenes = [(float(index * 20), 0.9) for index in range(1, 20)]
        cuts = va.pick_cuts(scenes, 1000.0, max_cuts=3)
        self.assertEqual(len(cuts), 3)
        self.assertEqual(cuts, sorted(cuts))

    def test_no_scene_changes_means_no_cuts(self):
        self.assertEqual(va.pick_cuts([], 300.0), [])


class BoundaryTests(unittest.TestCase):
    def test_split_boundaries_wraps_the_video(self):
        self.assertEqual(va.split_boundaries([30.0, 90.0], 100.0), [0.0, 30.0, 90.0, 100.0])

    def test_even_boundaries_cover_the_whole_video(self):
        bounds = va.even_boundaries(300.0, 6)
        self.assertEqual(len(bounds), 7)
        self.assertEqual(bounds[0], 0.0)
        self.assertEqual(bounds[-1], 300.0)
        self.assertEqual(bounds, sorted(bounds))

    def test_even_boundaries_are_capped(self):
        self.assertEqual(len(va.even_boundaries(300.0, 99)), va.MAX_SEGMENTS + 1)

    def test_frame_sample_time_is_the_middle_not_the_cut(self):
        # 切点那一帧常常还是上一段的画面，所以不能取段首
        self.assertEqual(va.frame_sample_time(0.0, 10.0), 5.0)
        self.assertEqual(va.frame_sample_time(90.0, 100.0), 95.0)

    def test_degenerate_segment_does_not_go_negative(self):
        self.assertEqual(va.frame_sample_time(10.0, 10.0), 10.0)


# ------------------------------------------------------------- 没有模型时的兜底


class CaptionFallbackTests(unittest.TestCase):
    """没模型时只能给「这一段是画面切出来的」这个事实，一个字都不许编。"""

    def _segment(self, position=0, start=0.0, end=12.8):
        return bd.Segment(
            position=position,
            start_seconds=start,
            end_seconds=end,
            frame=b"\xff\xd8\xff fake",
            title="",
            summary="",
            question="",
            criteria="",
            hint=None,
            text_basis=bd.NO_TEXT,
        )

    def test_vision_disabled_keeps_the_placeholder(self):
        with patch.object(settings, "model_vision_enabled", False):
            segment = bd.caption_segment(self._segment(), 10, 310.0)
        self.assertEqual(segment.text_basis, bd.NO_TEXT)
        self.assertEqual(segment.title, "")

    def test_placeholder_says_we_do_not_know(self):
        title, summary, question, criteria, hint = bd._placeholder_text(2, 40.0, 52.0)
        self.assertIn("第 3 步", title)
        self.assertIn("不知道", summary)
        self.assertIn("画面自己切出来的", summary)
        self.assertIn("40~52", summary)
        # 绝不能出现任何「视频里出现过的东西」
        for forbidden in ("土豆", "盐", "克", "分钟", "度"):
            self.assertNotIn(forbidden, summary)
        self.assertTrue(question.strip() and criteria.strip() and hint.strip())

    def test_blank_segment_is_marked_as_text_less(self):
        segment = bd._blank_segment(0, 0.0, 5.0, b"\xff\xd8\xff")
        self.assertEqual(segment.text_basis, bd.NO_TEXT)
        self.assertTrue(segment.frame)

    def test_model_error_does_not_blow_up_the_whole_breakdown(self):
        segment = self._segment()
        with (
            patch.object(settings, "model_api_key", "fake"),
            patch.object(settings, "model_vision_enabled", True),
            patch.object(bd, "chat", side_effect=bd.ModelError("上游 429")),
        ):
            result = bd.caption_segment(segment, 10, 310.0)
        self.assertEqual(result.text_basis, bd.NO_TEXT)

    def test_garbled_model_reply_is_rejected_instead_of_half_used(self):
        segment = self._segment()
        with (
            patch.object(settings, "model_api_key", "fake"),
            patch.object(settings, "model_vision_enabled", True),
            patch.object(bd, "chat", return_value='{"title":"切土豆片"}'),  # 缺 criteria
        ):
            result = bd.caption_segment(segment, 10, 310.0)
        self.assertEqual(result.text_basis, bd.NO_TEXT)
        self.assertEqual(result.title, "")

    def test_good_reply_fills_every_checkpoint_field(self):
        segment = self._segment()
        reply = (
            "```json\n"
            '{"title":"把菜切成均匀薄片","summary":"切成厚度一致的小片。",'
            '"question":"每片厚度看起来一样吗？","criteria":"片与片厚度接近，不连刀。"}\n```'
        )
        with (
            patch.object(settings, "model_api_key", "fake"),
            patch.object(settings, "model_vision_enabled", True),
            patch.object(bd, "chat", return_value=reply),
        ):
            result = bd.caption_segment(segment, 10, 310.0)
        self.assertEqual(result.text_basis, bd.MODEL_TEXT)
        self.assertEqual(result.title, "第 1 步 · 把菜切成均匀薄片")
        self.assertTrue(result.question and result.criteria)
        # 页面上不显示 hint 了，提示词也不再要它
        self.assertIsNone(result.hint)

    def test_model_written_step_prefix_is_stripped(self):
        # 我们自己加「第 N 步 · 」，模型偶尔也写一遍，别变成「第 3 步 · 第 3 步 · …」
        self.assertEqual(bd._clean_title("第 3 步 · 把黄瓜斜刀切片"), "把黄瓜斜刀切片")
        self.assertEqual(bd._clean_title("第2步：把黄瓜斜刀切片"), "把黄瓜斜刀切片")
        self.assertEqual(bd._clean_title("「把黄瓜斜刀切片」"), "把黄瓜斜刀切片")
        self.assertEqual(bd._clean_title("  把黄瓜斜刀切片  "), "把黄瓜斜刀切片")


# ------------------------------------------------------------- 给用户看的说明


class RealNoteTests(unittest.TestCase):
    def _breakdown(self, method, captioned, uncaptioned, segments=10, cuts=9):
        item = SimpleNamespace(
            method=method,
            cuts=[float(index) for index in range(cuts)],
            segments=[None] * segments,
            captioned=captioned,
            uncaptioned=uncaptioned,
        )
        return item

    def test_shot_based_note_admits_it_only_saw_one_frame(self):
        note = bd.real_note(self._breakdown(bd.SHOT_BASIS, captioned=10, uncaptioned=0))
        self.assertIn("ffmpeg", note)
        self.assertIn("9 个切点", note)
        self.assertIn("不是整段视频", note)
        self.assertIn("没听声音", note)

    def test_even_fallback_says_the_boundary_was_ours(self):
        note = bd.real_note(self._breakdown(bd.EVEN_BASIS, captioned=0, uncaptioned=6))
        self.assertIn("平均分", note)
        self.assertIn("这个边界是我分的", note)

    def test_uncaptioned_segments_are_reported_not_hidden(self):
        note = bd.real_note(self._breakdown(bd.SHOT_BASIS, captioned=7, uncaptioned=3))
        self.assertIn("3 段模型没答上来", note)

    def test_no_model_note_says_nothing_was_invented(self):
        note = bd.real_note(self._breakdown(bd.SHOT_BASIS, captioned=0, uncaptioned=10))
        self.assertIn("没有可用的看图模型", note)
        self.assertIn("一个字都没编", note)


# ------------------------------------------------------------- 该不该重拆


class NeedsAnalysisTests(unittest.TestCase):
    def _video(self):
        return SimpleNamespace(id="v1", status="ready", object_key="videos/v1/source.mp4")

    def _record(self, **values):
        base = {"method": "shots", "status": "ready", "error_message": None}
        base.update(values)
        return SimpleNamespace(**base)

    def test_first_visit_triggers_analysis(self):
        with patch.object(app_main, "_local_video_path", return_value=object()):
            self.assertTrue(app_main._needs_analysis(self._video(), None))

    def test_ready_real_breakdown_is_reused(self):
        with patch.object(app_main, "_local_video_path", return_value=object()):
            self.assertFalse(app_main._needs_analysis(self._video(), self._record()))

    def test_mock_breakdown_is_upgraded_once_the_file_arrives(self):
        with patch.object(app_main, "_local_video_path", return_value=object()):
            self.assertTrue(
                app_main._needs_analysis(
                    self._video(), self._record(method="mock", status="ready")
                )
            )

    def test_failed_analysis_is_not_retried_on_every_refresh(self):
        # 拆失败过就别自动重跑，不然用户每刷新一次都要白等一遍 ffmpeg
        with patch.object(app_main, "_local_video_path", return_value=object()):
            self.assertFalse(
                app_main._needs_analysis(
                    self._video(), self._record(status="failed", error_message="ffmpeg 挂了")
                )
            )

    def test_mock_stays_mock_while_the_file_is_missing(self):
        with patch.object(app_main, "_local_video_path", return_value=None):
            self.assertFalse(
                app_main._needs_analysis(
                    self._video(), self._record(method="mock", status="ready")
                )
            )


if __name__ == "__main__":
    unittest.main()
