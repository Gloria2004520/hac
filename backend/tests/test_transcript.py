import json
import tempfile
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.transcript import get_transcript, parse_vtt

CAPTIONS = """WEBVTT

00:00:01.200 --> 00:00:03.000 align:start
<c>穿针 &amp; 打结</c>

00:00:03.000 --> 00:00:04.000
穿针 &amp; 打结

00:00:05.000 --> 00:00:07.000
将纽扣放好
"""


class TranscriptTests(unittest.TestCase):
    def test_real_timestamps_tags_and_rolling_duplicates(self):
        cues = parse_vtt(CAPTIONS)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0], {"id": 1, "start": 1.2, "end": 4.0, "text": "穿针 & 打结"})
        self.assertEqual(cues[1]["start"], 5.0)

    def test_malformed_and_reversed_cues_are_ignored(self):
        self.assertEqual(parse_vtt("invalid --> timestamp\n文字\n\n00:00:02.000 --> 00:00:01.000\n反向"), [])

    def test_download_must_be_ready(self):
        with self.assertRaisesRegex(ValueError, "下载完成"):
            get_transcript(SimpleNamespace(status="downloading", object_key=None), None, None)

    def test_subtitles_are_cached_and_do_not_repeat_external_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.mp4"
            video = SimpleNamespace(status="ready", object_key="source.mp4", source_url="https://youtube.com/watch?v=abc")
            settings = SimpleNamespace(yt_dlp_cookie_file=None)

            def fake_run(command, **kwargs):
                self.assertEqual(kwargs["timeout"], 40)
                out = command[command.index("--output") + 1]
                Path(out.replace("%(ext)s", "zh-Hans.vtt")).write_text(CAPTIONS, encoding="utf-8")
                return SimpleNamespace(returncode=0)

            with patch("app.transcript.subprocess.run", side_effect=fake_run) as run:
                data = get_transcript(video, settings, lambda _: path)
                self.assertEqual(len(data["segments"]), 2)
                self.assertEqual(get_transcript(video, settings, lambda _: path), data)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(json.loads((path.parent / "transcript.json").read_text())["source"], "subtitle")

    def test_missing_subtitles_and_timeout_have_actionable_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            video = SimpleNamespace(status="ready", object_key="source.mp4", source_url="https://youtube.com/watch?v=abc")
            settings = SimpleNamespace(yt_dlp_cookie_file=None)
            resolve = lambda _: Path(directory) / "source.mp4"
            with patch("app.transcript.subprocess.run", return_value=SimpleNamespace(returncode=0)):
                with self.assertRaisesRegex(ValueError, "没有可用字幕"):
                    get_transcript(video, settings, resolve)
            with patch("app.transcript.subprocess.run", side_effect=subprocess.TimeoutExpired("yt-dlp", 40)):
                with self.assertRaisesRegex(ValueError, "超时"):
                    get_transcript(video, settings, resolve)
            # The concurrency slot is released after either failure.
            with patch("app.transcript.subprocess.run", return_value=SimpleNamespace(returncode=1)):
                with self.assertRaisesRegex(ValueError, "未能提供字幕"):
                    get_transcript(video, settings, resolve)


if __name__ == "__main__":
    unittest.main()
