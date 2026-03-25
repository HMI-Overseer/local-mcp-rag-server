import unittest

from rag.search_utils import build_snippet, keyword_score, vector_distance_to_score


class SearchUtilsTests(unittest.TestCase):
    def test_vector_distance_to_score_is_bounded(self):
        self.assertEqual(vector_distance_to_score(0.0), 1.0)
        self.assertGreater(vector_distance_to_score(0.5), vector_distance_to_score(2.0))

    def test_keyword_score_rewards_overlap(self):
        self.assertGreater(keyword_score("The moon glows at night", "moon night"), 0.0)
        self.assertEqual(keyword_score("Completely unrelated text", "moon night"), 0.0)

    def test_build_snippet_prefers_query_region(self):
        text = "Intro " * 50 + "target phrase appears here and matters " + "tail " * 50
        snippet = build_snippet(text, "phrase", 120)

        self.assertIn("phrase", snippet.lower())
        self.assertLessEqual(len(snippet), 126)


if __name__ == "__main__":
    unittest.main()
