import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evaluation.top_k import (
    Budget, assert_snapshot_matches, covered, digest, load_dataset, merge_intervals,
    score_hits, select_candidate, summarize,
)
from evaluation.report import validate_reviews


class TopKEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.texts = {"a.txt": "abcdefghij", "b.txt": "xyz"}
        self.clauses = {"first": {"evidence": [{"source": "a.txt", "quote": "defg"}]}}
        self.case = {"id": "a", "split": "dev", "requires": ["first"]}

    def test_adjacent_chunks_cover_whole_gold_clause(self):
        hits = [{"source": "a.txt", "text": "abcde"}, {"source": "a.txt", "text": "fghij"}]
        self.assertTrue(score_hits(self.case, hits, self.texts, self.clauses)["full_evidence"])

    def test_gap_does_not_count_as_coverage(self):
        self.assertFalse(covered(3, 7, [(0, 5), (6, 10)]))
        self.assertEqual(merge_intervals([(0, 4), (3, 6)]), [(0, 6)])

    def test_correct_source_without_clause_is_not_evidence_hit(self):
        row = score_hits(self.case, [{"source": "a.txt", "text": "abc"}], self.texts, self.clauses)
        self.assertTrue(row["source_hit"])
        self.assertFalse(row["evidence_hit"])

    def test_equivalent_evidence_from_another_policy_is_valid(self):
        self.clauses["first"]["evidence"].append({"source": "b.txt", "quote": "xyz"})
        row = score_hits(self.case, [{"source": "b.txt", "text": "xyz"}], self.texts, self.clauses)
        self.assertTrue(row["full_evidence"])

    def test_unanswerable_has_no_fake_recall_score(self):
        row = score_hits({"requires": []}, [{"source": "a.txt", "text": "abc"}], self.texts, self.clauses)
        self.assertIsNone(row["full_evidence"])
        self.assertIsNone(row["evidence_coverage"])

    def test_stale_collection_is_rejected(self):
        with self.assertRaises(ValueError):
            assert_snapshot_matches([{"source": "a", "text": "one"}], [{"source": "a", "text": "two"}])

    def test_budget_persists_and_blocks_extra_requests(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            path.write_text(json.dumps({"embedding": 79, "deepseek": 40}), encoding="utf-8")
            budget = Budget(path)
            budget.consume("embedding")
            with self.assertRaises(RuntimeError):
                Budget(path).consume("embedding")
            with self.assertRaises(RuntimeError):
                budget.consume("deepseek")

    def test_selection_uses_only_dev_metrics(self):
        summary = {"dev": {str(k): {"full_evidence": value, "evidence_coverage": value,
                                   "mean_context_characters": k * 100}
                           for k, value in ((1, .2), (3, .6), (5, .9), (8, .9))},
                   "test": {"1": {"full_evidence": 1}}}
        self.assertEqual(select_candidate(summary), 5)

    def test_incomplete_results_are_not_summarized(self):
        with self.assertRaises(ValueError):
            summarize({"cases": [self.case]}, {})

    def test_real_fixture_is_valid_and_within_approved_plan(self):
        dataset, _, _ = load_dataset()
        self.assertEqual(len(dataset["cases"]), 60)
        self.assertEqual(sum(bool(case.get("generate")) for case in dataset["cases"]), 20)

    def test_new_answers_cannot_reuse_old_reviews(self):
        with self.assertRaises(ValueError):
            validate_reviews({"a:3": {"reply": "new answer"}},
                             {"reviews": {"a:3": {}}, "answers_sha256": "old"})

    def test_matching_review_hash_is_accepted(self):
        answers = {"a:3": {"reply": "answer"}}
        validate_reviews(answers, {"reviews": {"a:3": {}}, "answers_sha256": digest(answers)})


if __name__ == "__main__":
    unittest.main()
