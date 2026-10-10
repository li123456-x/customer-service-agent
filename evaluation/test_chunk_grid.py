import unittest

import numpy as np

from evaluation.chunk_grid import (
    candidate_sort_key, check_budget, cosine_hits, normalize_vectors,
    select_joint, split_variants, unique_text_characters,
)
from evaluation.top_k import load_dataset


class ChunkGridTests(unittest.TestCase):
    def test_cosine_is_norm_independent_and_ranked(self):
        chunks = [{"id": 1}, {"id": 2}, {"id": 3}]
        hits = cosine_hits(chunks, [[100, 0], [0, 3], [-4, 0]], [5, 0], 2)
        self.assertEqual([hit["id"] for hit in hits], [1, 2])
        self.assertAlmostEqual(hits[0]["score"], 1)

    def test_ties_are_stable_and_large_k_returns_available_rows(self):
        hits = cosine_hits([{"id": 1}, {"id": 2}], [[1, 1], [1, 1]], [1, 0], 8)
        self.assertEqual([hit["id"] for hit in hits], [1, 2])

    def test_bad_vectors_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_vectors([[0, 0]])
        with self.assertRaises(ValueError):
            normalize_vectors([[np.nan, 1]])

    def test_budget_cannot_exceed_new_authorization(self):
        self.assertEqual(check_budget(59), 60)
        with self.assertRaises(RuntimeError):
            check_budget(60)

    def test_overlapping_source_ranges_are_not_counted_twice(self):
        hits = [{"source": "x", "text": "abcde"}, {"source": "x", "text": "defgh"}]
        self.assertEqual(unique_text_characters(hits, {"x": "abcdefgh"}), 8)

    def test_selection_prefers_complete_evidence_before_shorter_context(self):
        base = {"evidence_coverage": 1, "chunk_count": 10, "overlap": 0, "k": 3, "size": 800}
        summaries = {"short": {**base, "full_evidence": .9, "mean_context_characters": 100},
                     "complete": {**base, "full_evidence": 1, "mean_context_characters": 1000}}
        self.assertEqual(select_joint(summaries), "complete")

    def test_equal_evidence_prefers_less_context_and_target_overlap(self):
        base = {"full_evidence": 1, "evidence_coverage": 1, "chunk_count": 14, "k": 5, "size": 500}
        a = {**base, "mean_context_characters": 1000, "overlap": 0}
        b = {**base, "mean_context_characters": 1000, "overlap": 80}
        self.assertGreater(candidate_sort_key(a), candidate_sort_key(b))

    def test_current_500_zero_and_eighty_have_identical_chunks(self):
        _, texts, _ = load_dataset()
        variants = split_variants(texts)
        self.assertEqual(variants["500/0"]["chunk_set_sha256"], variants["500/80"]["chunk_set_sha256"])
        self.assertEqual(sum(variants["500/80"]["actual_adjacent_overlap"]), 0)
        self.assertEqual(len(variants["800/0"]["chunks"]), 10)


if __name__ == "__main__":
    unittest.main()
