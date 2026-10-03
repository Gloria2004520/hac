import unittest
from unittest.mock import patch

from app import library
from app.config import settings
from app.library import classify_tutorials, display_tutorial_title, keyword_category


class LibraryCategoryTests(unittest.TestCase):
    def test_cooking_title(self):
        self.assertEqual(keyword_category("番茄炒蛋，新手也能学会"), ("cooking", "rule"))
        self.assertEqual(keyword_category("厨师长教你辣子鸡的做法"), ("cooking", "rule"))

    def test_tool_title(self):
        self.assertEqual(keyword_category("如何使用电钻安装置物架"), ("tools", "rule"))

    def test_unknown_title_is_honestly_other(self):
        self.assertEqual(keyword_category("第一次给绿植换盆"), ("other", "rule"))

    def test_display_title_only_adds_suffix_once(self):
        self.assertEqual(display_tutorial_title("番茄炒蛋"), "番茄炒蛋教程")
        self.assertEqual(display_tutorial_title("番茄炒蛋教程"), "番茄炒蛋教程")
        self.assertEqual(
            display_tutorial_title("厨师长教你：“辣子鸡” 的正宗做法，先收藏起来"),
            "辣子鸡教程",
        )

    def test_free_model_can_classify_from_title_and_step_titles(self):
        with (
            patch.object(settings, "model_api_key", "fake"),
            patch.object(settings, "model_name", "example/free-model:free"),
            patch.object(
                library,
                "chat",
                return_value='{"items":[{"id":"v1","category":"tools"}]}',
            ),
        ):
            result = classify_tutorials([
                {"id": "v1", "title": "置物架教程", "step_titles": ["拧紧墙上的螺丝"]}
            ])
        self.assertEqual(result["v1"], ("tools", "model"))

    def test_non_free_model_is_not_called_for_extra_classification(self):
        with (
            patch.object(settings, "model_api_key", "fake"),
            patch.object(settings, "model_name", "paid-model"),
            patch.object(library, "chat") as model_call,
        ):
            result = classify_tutorials([
                {"id": "v1", "title": "番茄炒蛋", "step_titles": []}
            ])
        model_call.assert_not_called()
        self.assertEqual(result["v1"], ("cooking", "rule"))


if __name__ == "__main__":
    unittest.main()
