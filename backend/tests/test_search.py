import unittest

from app.search import normalize_query, parse_search_payload


class SearchParsingTests(unittest.TestCase):
    def test_normalizes_whitespace(self):
        self.assertEqual(normalize_query("  番茄   炒蛋  "), "番茄 炒蛋")

    def test_accepts_missing_optional_fields(self):
        results = parse_search_payload(
            "番茄炒蛋",
            {"entries": [{"id": "abc123", "title": "番茄炒蛋家常做法"}]},
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://www.youtube.com/watch?v=abc123")
        self.assertIsNone(results[0]["duration_seconds"])
        self.assertIsNone(results[0]["view_count"])
        self.assertIsNone(results[0]["thumbnail_url"])

    def test_synonym_match_ranks_relevant_video_first(self):
        results = parse_search_payload(
            "番茄炒蛋",
            {
                "entries": [
                    {"id": "noise", "title": "城市探店合集", "duration": 300, "view_count": 5000000},
                    {"id": "recipe", "title": "西红柿炒蛋家常做法", "duration": 180, "view_count": 1000},
                ]
            },
        )
        self.assertEqual(results[0]["platform_video_id"], "recipe")
        self.assertGreater(results[0]["score"], 0.8)


if __name__ == "__main__":
    unittest.main()
