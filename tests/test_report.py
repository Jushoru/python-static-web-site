"""Regression checks for stale results, damaged caches and invalid input data."""

import csv
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_report as report
import report_cache as cache


class ReportTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "_build" / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        # Retain tiny test fixtures under the ignored directory; no source data is altered.
        self.work = Path(tempfile.mkdtemp(prefix="report-", dir=parent))

    def cache_fixture(self):
        output = self.work / "generated"
        for name in cache.OUTPUTS:
            cache.write_if_changed(output / name, f"original {name}")
        store = self.work / "cache"
        cache.save(store, "test-key", output)
        return store, output

    def test_restore_recovers_missing_and_modified_output(self):
        store, output = self.cache_fixture()
        cache.write_if_changed(output / "results.md", "stale data")
        target = self.work / "fresh-output"
        self.assertTrue(cache.restore(store, "test-key", target))
        self.assertEqual((target / "results.md").read_text(), "original results.md")
        self.assertTrue(cache.restore(store, "test-key", output))
        self.assertEqual((output / "results.md").read_text(), "original results.md")

    def test_corrupt_cache_is_not_a_hit_and_restores_nothing(self):
        store, _ = self.cache_fixture()
        (store / "test-key/results.md").write_text("corruption")
        target = self.work / "not-created"
        self.assertFalse(cache.restore(store, "test-key", target))
        self.assertFalse(target.exists())

    def test_missing_cache_is_a_miss(self):
        self.assertFalse(cache.restore(self.work / "absent", "key", self.work / "out"))

    def test_each_analysis_input_and_runtime_invalidate_cache(self):
        root = self.work / "project"
        for name in cache.INPUTS:
            cache.write_if_changed(root / name, "original\n")
        baseline = cache.cache_key(root, runtime={"python": "A"})
        for name in cache.INPUTS:
            cache.write_if_changed(root / name, "changed\n")
            self.assertNotEqual(cache.cache_key(root, runtime={"python": "A"}), baseline, name)
            cache.write_if_changed(root / name, "original\n")
        self.assertNotEqual(cache.cache_key(root, runtime={"python": "B"}), baseline)
        cache.write_if_changed(root / "docs/practice.md", "text-only edit")
        self.assertEqual(cache.cache_key(root, runtime={"python": "A"}), baseline)

    def test_dependency_snapshot_accepts_git_line_endings_but_not_edits(self):
        original = b"package==1.0\r\nother==2.0\r\n"
        recorded = cache.digest(original)
        self.assertTrue(cache.snapshot_matches(original.replace(b"\r\n", b"\n"), recorded))
        self.assertFalse(cache.snapshot_matches(b"package==9.0\nother==2.0\n", recorded))

    def test_csv_rejects_missing_duplicate_nonfinite_and_negative_data(self):
        with report.DATA.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        variants = [rows[:-1], rows + [rows[0]],
                    [dict(rows[0], build_seconds="nan")] + rows[1:],
                    [dict(rows[0], build_seconds="-1")] + rows[1:]]
        for i, rows in enumerate(variants):
            path = self.work / f"invalid-{i}.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=report.FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ValueError):
                report.read_measurements(path, report.METADATA)

    def test_known_statistics_and_changed_data(self):
        samples = [{"pages": 10, "build_seconds": value, "site_bytes": 100} for value in (1.0, 2.0, 3.0)]
        result = report.summarize(samples)[0]
        self.assertEqual(result["mean"], 2.0)
        self.assertEqual(result["stdev"], 1.0)
        samples[0]["build_seconds"] = 4.0
        self.assertTrue(math.isclose(report.summarize(samples)[0]["mean"], 3.0))


if __name__ == "__main__":
    unittest.main()
