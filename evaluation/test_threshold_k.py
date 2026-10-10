import unittest

from evaluation.threshold_k import aggregate, evaluate, filter_hits, lost_evidence, top1_diagnostics


def hit(score, text="abcdef"):
    return {"score": score, "source": "policy.txt", "text": text}


class ThresholdKTests(unittest.TestCase):
    def setUp(self):
        self.texts = {"policy.txt": "abcdefghij"}
        self.clauses = {"rule": {"evidence": [{"source": "policy.txt", "quote": "def"}]}}
        self.cases = [
            {"id": "positive", "query": "known", "requires": ["rule"], "evaluation_group": "old60"},
            {"id": "negative", "query": "unknown", "requires": [], "evaluation_group": "seen20"},
        ]
        self.hits = {"positive": [hit(0.6, "abc"), hit(0.5, "def")],
                     "negative": [hit(0.55, "abc"), hit(0.4, "ghi")]}

    def test_threshold_boundary_is_inclusive(self):
        self.assertEqual([row["score"] for row in filter_hits([hit(0.5), hit(0.45), hit(0.44)], 3, 0.45)],
                         [0.5, 0.45])

    def test_top_k_is_applied_before_filtering(self):
        self.assertEqual(filter_hits([hit(0.4), hit(0.9)], 1, 0.45), [])

    def test_no_threshold_retains_original_top_k(self):
        self.assertEqual(filter_hits([hit(0.2), hit(0.1)], 1, None), [hit(0.2)])

    def test_invalid_threshold_or_scores_are_rejected(self):
        for threshold in (float("nan"), float("inf"), 1.1, -1.1):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                filter_hits([hit(0.5)], 1, threshold)
        with self.assertRaises(ValueError):
            filter_hits([hit(float("nan"))], 1, None)
        with self.assertRaises(ValueError):
            filter_hits([hit(0.5)], 0, None)

    def test_missing_evidence_and_negative_results_are_separate(self):
        rows = evaluate(self.cases, self.hits, self.texts, self.clauses, 2, 0.56)
        summary = aggregate(rows)
        self.assertEqual(summary["full_evidence_count"], 0)
        self.assertEqual(summary["answerable_empty_count"], 0)
        self.assertEqual(summary["unanswerable_nonempty_count"], 0)

    def test_higher_threshold_can_empty_answerable_queries(self):
        rows = evaluate(self.cases, self.hits, self.texts, self.clauses, 2, 0.61)
        self.assertEqual(aggregate(rows)["answerable_empty_count"], 1)

    def test_negative_questions_have_no_fake_coverage_score(self):
        rows = evaluate(self.cases, self.hits, self.texts, self.clauses, 2, None)
        self.assertIsNone(rows[1]["full_evidence"])
        self.assertEqual(aggregate(rows)["full_evidence_rate"], 1)

    def test_top_k_does_not_change_empty_result_decision(self):
        for threshold in (None, 0.45, 0.56, 0.61):
            left = aggregate(evaluate(self.cases, self.hits, self.texts, self.clauses, 1, threshold))
            right = aggregate(evaluate(self.cases, self.hits, self.texts, self.clauses, 2, threshold))
            self.assertEqual(left["answerable_empty_count"], right["answerable_empty_count"])
            self.assertEqual(left["unanswerable_nonempty_count"], right["unanswerable_nonempty_count"])

    def test_lost_evidence_is_compared_with_the_same_k(self):
        before = evaluate(self.cases, self.hits, self.texts, self.clauses, 2, None)
        after = evaluate(self.cases, self.hits, self.texts, self.clauses, 2, 0.56)
        losses = lost_evidence(self.cases, before, after)
        self.assertEqual(len(losses), 1)
        self.assertEqual(losses[0]["lost_clauses"], ["rule"])
        self.assertFalse(losses[0]["no_results"])

    def test_overlap_diagnostics_do_not_claim_perfect_separation(self):
        self.hits["negative"][0]["score"] = 0.65
        self.assertFalse(top1_diagnostics(self.cases, self.hits)["can_keep_all_positives_and_reject_all_negatives"])


if __name__ == "__main__":
    unittest.main()
