import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


class TranscriptApiTests(unittest.TestCase):
    def setUp(self):
        self.video = SimpleNamespace(status="ready", object_key="videos/abc/source.mp4", source_url="https://www.youtube.com/watch?v=abc")
        app.dependency_overrides[get_db] = lambda: SimpleNamespace(get=lambda *args: self.video)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def test_returns_actual_subtitle_evidence(self):
        data = {"source": "subtitle", "segments": [{"id": 1, "start": 1.2, "end": 2, "text": "动作"}]}
        with patch("app.main.get_transcript", return_value=data) as extract:
            response = self.client.post("/api/videos/abc/transcript")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), data)
        extract.assert_called_once()

    def test_unknown_video_is_not_fetched(self):
        self.video = None
        with patch("app.main.get_transcript") as extract:
            self.assertEqual(self.client.post("/api/videos/abc/transcript").status_code, 404)
            extract.assert_not_called()

    def test_extraction_error_is_returned_without_fake_steps(self):
        with patch("app.main.get_transcript", side_effect=ValueError("视频没有可用字幕")):
            response = self.client.post("/api/videos/abc/transcript")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "视频没有可用字幕"})

    def test_unsafe_sources_do_not_reach_downloader(self):
        self.video.source_url = "http://127.0.0.1/private"
        with patch("app.main.get_transcript") as extract:
            self.assertEqual(self.client.post("/api/videos/abc/transcript").status_code, 422)
            extract.assert_not_called()


if __name__ == "__main__":
    unittest.main()
