"""Check real Git provenance failures without network or phone access."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("sources", Path(__file__).resolve().parents[1] / "tools/sources.py")
sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sources)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "references/donor"
        self.path.mkdir(parents=True)
        sources.git(self.path, "init", "--quiet")
        sources.git(self.path, "config", "user.name", "Fixture")
        sources.git(self.path, "config", "user.email", "fixture@example.invalid")
        sources.git(self.path, "remote", "add", "origin", "https://github.com/example/donor")
        (self.path / "LICENSE").write_text("Synthetic license fixture\n")
        sources.git(self.path, "add", "LICENSE")
        sources.git(self.path, "commit", "--quiet", "-m", "fixture")
        self.source = {"id": "donor", "url": "https://github.com/example/donor", "revision": sources.git(self.path, "rev-parse", "HEAD"), "review_files": ["LICENSE"]}

    def tearDown(self):
        self.temp.cleanup()

    def test_clean_head_origin_and_content_digest(self):
        result = sources.verify(self.root, self.source)
        self.assertEqual(result["revision"], self.source["revision"])
        self.assertEqual(len(result["review_file_sha256"]["LICENSE"]), 64)
        self.assertFalse(result["local_device_verified"])

    def test_modified_and_untracked_files_are_rejected(self):
        for file in ["LICENSE", "extra.txt"]:
            with self.subTest(file=file):
                before = (self.path / file).read_bytes() if (self.path / file).exists() else None
                (self.path / file).write_text("changed")
                with self.assertRaises(sources.SourceError):
                    sources.verify(self.root, self.source)
                if before is None:
                    (self.path / file).unlink()
                else:
                    (self.path / file).write_bytes(before)

    def test_origin_and_revision_mismatches(self):
        with self.assertRaises(sources.SourceError):
            sources.verify(self.root, {**self.source, "revision": "f" * 40})
        sources.git(self.path, "remote", "set-url", "origin", "https://github.com/example/other")
        with self.assertRaises(sources.SourceError):
            sources.verify(self.root, self.source)

    def test_invalid_paths_pins_and_missing_review_files(self):
        for change in [{"id": "../escape"}, {"revision": "main"}, {"url": "file:///tmp/repo"}, {"review_files": ["../LICENSE"]}, {"review_files": ["missing"]}]:
            with self.subTest(change=change), self.assertRaises(sources.SourceError):
                sources.verify(self.root, {**self.source, **change})

    def test_existing_fetch_never_overwrites_work(self):
        (self.path / "LICENSE").write_text("Keep this work")
        with self.assertRaises(sources.SourceError):
            sources.fetch(self.root, self.source)
        self.assertEqual((self.path / "LICENSE").read_text(), "Keep this work")

    def test_symlink_checkout_is_rejected(self):
        (self.root / "references/link").symlink_to(self.path, target_is_directory=True)
        with self.assertRaises(sources.SourceError):
            sources.target(self.root, {**self.source, "id": "link"})


if __name__ == "__main__":
    unittest.main()
