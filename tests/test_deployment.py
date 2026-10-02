"""Check publication safeguards without contacting a server or reading SSH keys."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy_helios as deploy
import check_published as published


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "_build" / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.site = Path(tempfile.mkdtemp(prefix="deployment-", dir=parent))
        (self.site / "index.html").write_text(deploy.MARKER, encoding="utf-8")
        (self.site / "results.html").write_text("results", encoding="utf-8")
        (self.site / "search").mkdir()
        (self.site / "search/search_index.json").write_text('{}', encoding="utf-8")

    def test_upload_stays_in_fixed_report_directory_and_does_not_delete(self):
        batch, count = deploy.make_batch(self.site)
        self.assertEqual(count, 3)
        self.assertEqual(batch.splitlines()[0], f'cd "{deploy.REMOTE}"')
        self.assertNotIn("rm ", batch)
        self.assertNotIn("rmdir ", batch)
        self.assertIn('put "./index.html" "./index.html"', batch)
        self.assertLess(batch.index('put "./search/'), batch.index('put "./index.html"'))
        self.assertLess(batch.index('put "./index.html"'), batch.index('put "./results.html"'))

    def test_missing_report_and_unsafe_filename_are_rejected(self):
        (self.site / "index.html").write_text("another website", encoding="utf-8")
        with self.assertRaises(ValueError):
            deploy.make_batch(self.site)
        (self.site / "index.html").write_text(deploy.MARKER, encoding="utf-8")
        (self.site / "bad[name].txt").write_text("bad", encoding="utf-8")
        with self.assertRaises(ValueError):
            deploy.make_batch(self.site)

    def test_symlink_is_rejected(self):
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError):
                deploy.make_batch(self.site)

    def test_connection_rejects_empty_and_option_like_host(self):
        for host, port in [("", "2222"), ("-Fconfig", "2222"), ("host", "0"), ("host", "22\nput")]:
            with patch.dict("os.environ", {"HELIOS_HOST": host, "HELIOS_PORT": port}):
                with self.assertRaises(ValueError):
                    deploy.connection()

    def test_http_check_rejects_stale_commit_missing_marker_index_or_image(self):
        commit = "a" * 40
        valid = {"index.html": deploy.MARKER, "results.html": commit,
                 "theory.html": '<img src="assets/theory/radar_ssg.png">',
                 "practice.html": '<div id="eq-mean"></div><div id="eq-stdev"></div>'
                     + '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>t</mi></math>' * 2,
                 "search/search_index.json": json.dumps({"docs": [{"title": "Report"}]}),
                 "assets/generated/build-times.svg": '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
                 **published.IMAGE_SIGNATURES}
        published.validate_contents(valid, commit)
        for name, replacement in [("index.html", "404"), ("results.html", "b" * 40),
                                  ("search/search_index.json", '{"docs": []}'),
                                  ("theory.html", '<img src="old-diagram.svg">'),
                                  ("practice.html", '<p>Formula not rendered</p>'),
                                  ("assets/generated/build-times.svg", "<html>Not Found</html>"),
                                  ("assets/theory/radar_ssg.png", b"<html>Not Found</html>"),
                                  ("assets/theory/image2.jpg", b"<html>Not Found</html>")]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                published.validate_contents({**valid, name: replacement}, commit)


if __name__ == "__main__":
    unittest.main()
