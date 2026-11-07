import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _stdio  # noqa: E402


def make_glossary():
    return {
        "version": 2,
        "terms": [
            {
                "id": "Manhattan",
                "source": "Manhattan",
                "target": "Манхэттен",
                "category": "place",
                "aliases": [],
                "gender": "unknown",
                "confidence": "medium",
                "frequency": 0,
                "evidence_refs": [],
                "notes": "",
            }
        ],
        "high_frequency_top_n": 20,
        "applied_meta_hashes": {},
    }


def make_meta():
    return {
        "schema_version": 1,
        "new_entities": [
            {
                "source": "Brouwer",
                "target_proposal": "Брауэр",
                "category": "person",
                "evidence": "The tale was told of old Brouwer",
            }
        ],
        "alias_hypotheses": [],
        "attribute_hypotheses": [],
        "used_term_sources": [],
        "conflicts": [],
    }


def write_text(directory, name, text):
    Path(directory, name).write_text(text, encoding="utf-8")


class ConfigureUtf8StdioTests(unittest.TestCase):
    def test_reconfigures_stdout_stderr_and_optional_stdin(self):
        class FakeStream:
            def __init__(self):
                self.kwargs = None

            def reconfigure(self, **kwargs):
                self.kwargs = kwargs

        stdout, stderr, stdin = FakeStream(), FakeStream(), FakeStream()
        with mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(sys, "stderr", stderr), \
                mock.patch.object(sys, "stdin", stdin):
            _stdio.configure_utf8_stdio(include_stdin=True)

        for stream in (stdout, stderr, stdin):
            self.assertEqual(stream.kwargs, {"encoding": "utf-8"})

    def test_streams_without_reconfigure_are_ignored(self):
        class StringStream:
            pass

        with mock.patch.object(sys, "stdout", StringStream()), \
                mock.patch.object(sys, "stderr", StringStream()):
            _stdio.configure_utf8_stdio()  # must not raise


class CliUtf8RegressionTests(unittest.TestCase):
    """Windows pipes default to cp1251; the CLIs must still emit UTF-8."""

    def _env(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1251"
        env.pop("PYTHONUTF8", None)
        return env

    def _run(self, args, **kwargs):
        return subprocess.run(
            [sys.executable, *args],
            cwd=str(SCRIPT_DIR.parent),
            capture_output=True,
            env=self._env(),
            **kwargs,
        )

    def test_glossary_print_terms_survives_cp1251_stdout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            write_text(temp_dir, "glossary.json", json.dumps(make_glossary(), ensure_ascii=False))
            write_text(temp_dir, "chunk0001.md", "Manhattan is big.\n")

            proc = self._run(
                [str(SCRIPT_DIR / "glossary.py"), "print-terms-for-chunk", temp_dir, "chunk0001.md"]
            )

            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
            output = proc.stdout.decode("utf-8")
            self.assertIn("原文", output)
            self.assertIn("Манхэттен", output)

    def test_merge_meta_reads_and_writes_utf8_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            write_text(temp_dir, "glossary.json", json.dumps(make_glossary(), ensure_ascii=False))
            write_text(temp_dir, "output_chunk0001.meta.json",
                       json.dumps(make_meta(), ensure_ascii=False))

            prep = self._run([str(SCRIPT_DIR / "merge_meta.py"), "prepare-merge", temp_dir])
            self.assertEqual(prep.returncode, 0, prep.stderr.decode("utf-8", "replace"))
            proposal = json.loads(prep.stdout.decode("utf-8"))
            self.assertEqual(proposal["consumed_chunk_ids"], ["chunk0001"])

            payload = {
                "auto_apply": proposal["auto_apply"],
                "decisions": [],
                "consumed_chunk_ids": proposal["consumed_chunk_ids"],
            }
            applied = self._run(
                [str(SCRIPT_DIR / "merge_meta.py"), "apply-merge", temp_dir],
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            self.assertEqual(applied.returncode, 0, applied.stderr.decode("utf-8", "replace"))

            glossary = json.loads(Path(temp_dir, "glossary.json").read_text(encoding="utf-8"))
            brouwer = next(t for t in glossary["terms"] if t["source"] == "Brouwer")
            self.assertEqual(brouwer["target"], "Брауэр")


if __name__ == "__main__":
    unittest.main()
