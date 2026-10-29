import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_state  # noqa: E402
from manifest import create_manifest, file_hash  # noqa: E402


def glossary_doc(target="太一", aliases=None):
    return {
        "version": 2,
        "terms": [
            {
                "id": "Tai",
                "source": "Tai",
                "target": target,
                "category": "person",
                "aliases": aliases or [],
                "gender": "unknown",
                "confidence": "medium",
                "frequency": 1,
                "evidence_refs": [],
                "notes": "",
            }
        ],
        "high_frequency_top_n": 0,
        "applied_meta_hashes": {},
    }


class RunStateTests(unittest.TestCase):
    def _write(self, path, content):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")

    def _workspace(self):
        tmp = tempfile.TemporaryDirectory()
        temp_dir = Path(tmp.name)
        self._write(temp_dir / "input.md", "Tai went home.\n")
        self._write(temp_dir / "chunk0001.md", "Tai went home.\n")
        self._write(temp_dir / "chunk0002.md", "No glossary hit.\n")
        self._write(temp_dir / "output_chunk0001.md", "太一回家了。\n")
        self._write(temp_dir / "output_chunk0002.md", "没有术语。\n")
        create_manifest(
            str(temp_dir),
            ["chunk0001.md", "chunk0002.md"],
            str(temp_dir / "input.md"),
        )
        self._write(temp_dir / "glossary.json", json.dumps(glossary_doc(), ensure_ascii=False))
        return tmp, temp_dir

    def test_untracked_outputs_are_record_only_by_default(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            plan = run_state.plan(str(temp_dir))

        self.assertEqual(plan["translation_chunk_ids"], [])
        self.assertEqual(plan["record_only_chunk_ids"], ["chunk0001", "chunk0002"])

    def test_retranslate_untracked_flag_marks_existing_outputs_for_translation(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            plan = run_state.plan(str(temp_dir), retranslate_untracked=True)

        self.assertEqual(plan["translation_chunk_ids"], ["chunk0001", "chunk0002"])

    def test_record_then_plan_is_unchanged(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            run_state.record_chunks(str(temp_dir), ["chunk0001", "chunk0002"])
            plan = run_state.plan(str(temp_dir))

        self.assertEqual(plan["translation_chunk_ids"], [])
        self.assertEqual(plan["record_only_chunk_ids"], [])
        self.assertEqual(plan["unchanged_chunk_ids"], ["chunk0001", "chunk0002"])

    def test_missing_output_needs_translation(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            os.remove(temp_dir / "output_chunk0002.md")
            plan = run_state.plan(str(temp_dir))

        self.assertIn("chunk0002", plan["translation_chunk_ids"])

    def test_blank_output_needs_translation(self):
        # Whitespace-only output has bytes on disk but no usable translation;
        # planning must treat it like a missing output, not record it.
        tmp, temp_dir = self._workspace()
        with tmp:
            self._write(temp_dir / "output_chunk0002.md", "\n   \n\t\n")
            plan = run_state.plan(str(temp_dir))
            reasons = {
                item["chunk_id"]: item["reasons"] for item in plan["chunks"]
            }

        self.assertIn("chunk0002", plan["translation_chunk_ids"])
        self.assertIn("blank_output", reasons["chunk0002"])

    def test_record_rejects_blank_output(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            self._write(temp_dir / "output_chunk0001.md", "   \n")
            with self.assertRaises(ValueError):
                run_state.record_chunks(str(temp_dir), ["chunk0001"])

    def test_source_hash_change_needs_translation_after_record(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            run_state.record_chunks(str(temp_dir), ["chunk0001", "chunk0002"])
            self._write(temp_dir / "chunk0001.md", "Tai changed.\n")
            plan = run_state.plan(str(temp_dir))

        self.assertIn("chunk0001", plan["translation_chunk_ids"])

    def test_glossary_target_change_needs_translation_for_affected_chunk_only(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            run_state.record_chunks(str(temp_dir), ["chunk0001", "chunk0002"])
            self._write(
                temp_dir / "glossary.json",
                json.dumps(glossary_doc(target="泰"), ensure_ascii=False),
            )
            plan = run_state.plan(str(temp_dir))

        self.assertIn("chunk0001", plan["translation_chunk_ids"])
        self.assertNotIn("chunk0002", plan["translation_chunk_ids"])

    def test_alias_change_on_selected_term_needs_translation(self):
        # chunk0001 contains the source "Tai", so the term is already selected
        # before AND after the alias edit — selection alone cannot detect the
        # change. The injected term table's 别名 column changed, so term_hash
        # must flag the chunk for re-translation.
        tmp, temp_dir = self._workspace()
        with tmp:
            run_state.record_chunks(str(temp_dir), ["chunk0001", "chunk0002"])
            self._write(
                temp_dir / "glossary.json",
                json.dumps(glossary_doc(aliases=["Taig"]), ensure_ascii=False),
            )
            plan = run_state.plan(str(temp_dir))
            reasons = {
                item["chunk_id"]: item["reasons"] for item in plan["chunks"]
            }

        self.assertIn("chunk0001", plan["translation_chunk_ids"])
        self.assertNotIn("chunk0002", plan["translation_chunk_ids"])
        self.assertTrue(
            any(
                isinstance(r, dict) and r.get("code") == "glossary_term_hash_changed"
                for r in reasons["chunk0001"]
            ),
            msg=f"expected glossary_term_hash_changed, got {reasons['chunk0001']}",
        )

    def test_new_alias_that_hits_chunk_changes_term_selection(self):
        tmp = tempfile.TemporaryDirectory()
        with tmp:
            temp_dir = Path(tmp.name)
            self._write(temp_dir / "input.md", "Taig appears.\n")
            self._write(temp_dir / "chunk0001.md", "Taig appears.\n")
            self._write(temp_dir / "output_chunk0001.md", "泰格出现。\n")
            create_manifest(str(temp_dir), ["chunk0001.md"], str(temp_dir / "input.md"))
            self._write(temp_dir / "glossary.json", json.dumps(glossary_doc(), ensure_ascii=False))
            run_state.record_chunks(str(temp_dir), ["chunk0001"])

            self._write(
                temp_dir / "glossary.json",
                json.dumps(glossary_doc(aliases=["Taig"]), ensure_ascii=False),
            )
            plan = run_state.plan(str(temp_dir))

        self.assertEqual(plan["translation_chunk_ids"], ["chunk0001"])

    def test_output_hash_change_is_record_only(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            run_state.record_chunks(str(temp_dir), ["chunk0001"])
            self._write(temp_dir / "output_chunk0001.md", "手工编辑。\n")
            plan = run_state.plan(str(temp_dir))

        self.assertIn("chunk0001", plan["record_only_chunk_ids"])
        self.assertNotIn("chunk0001", plan["translation_chunk_ids"])

    def test_record_writes_required_fields(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            run_state.record_chunks(str(temp_dir), ["chunk0001"])
            data = run_state.load_run_state(str(temp_dir))
            record = data["chunks"]["chunk0001"]

        self.assertIn("glossary_version_used", record)
        self.assertEqual(record["entity_ids_used"], ["Tai"])
        self.assertIn("output_hash", record)


class SaveRunStateAtomicTests(unittest.TestCase):
    """save_run_state() writes via a tmp file + os.replace; a failed dump must
    leave the previous state intact and no temp litter behind."""

    def test_save_writes_a_loadable_state_file(self):
        with tempfile.TemporaryDirectory() as temp:
            state = {"version": 1, "chunks": {"chunk0001": {"ok": True}}}
            run_state.save_run_state(temp, state)

            self.assertEqual(run_state.load_run_state(temp), state)

    def test_second_save_replaces_the_previous_state(self):
        with tempfile.TemporaryDirectory() as temp:
            run_state.save_run_state(temp, {"version": 1, "chunks": {"chunk0001": {}}})
            run_state.save_run_state(temp, {"version": 1, "chunks": {"chunk0002": {}}})

            self.assertEqual(
                run_state.load_run_state(temp),
                {"version": 1, "chunks": {"chunk0002": {}}},
            )

    def test_failed_dump_keeps_previous_state_and_no_temp_files(self):
        with tempfile.TemporaryDirectory() as temp:
            first = {"version": 1, "chunks": {"chunk0001": {}}}
            run_state.save_run_state(temp, first)
            before = Path(temp, "run_state.json").read_text(encoding="utf-8")

            with mock.patch("run_state.json.dump", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    run_state.save_run_state(temp, {"version": 1, "chunks": {}})

            self.assertEqual(Path(temp, "run_state.json").read_text(encoding="utf-8"),
                             before)
            self.assertEqual(list(Path(temp).glob(".run_state.*")), [])


class BuildChunkRecordTests(unittest.TestCase):
    """build_chunk_record() — the per-chunk observation record that enables
    selective re-translation."""

    def _workspace(self, with_glossary=True):
        tmp = tempfile.TemporaryDirectory()
        temp_dir = Path(tmp.name)
        (temp_dir / "input.md").write_text("Tai went home.\n", encoding="utf-8")
        (temp_dir / "chunk0001.md").write_text("Tai went home.\n", encoding="utf-8")
        (temp_dir / "output_chunk0001.md").write_text("太一回家了。\n",
                                                      encoding="utf-8")
        create_manifest(str(temp_dir), ["chunk0001.md"], str(temp_dir / "input.md"))
        if with_glossary:
            (temp_dir / "glossary.json").write_text(
                json.dumps(glossary_doc(), ensure_ascii=False), encoding="utf-8")
        return tmp, temp_dir

    def test_record_contains_hashes_and_selected_entities(self):
        tmp, temp_dir = self._workspace()
        with tmp:
            record = run_state.build_chunk_record(str(temp_dir), "chunk0001")
            expected_source_hash = file_hash(str(temp_dir / "chunk0001.md"))
            expected_output_hash = file_hash(str(temp_dir / "output_chunk0001.md"))

        self.assertEqual(
            set(record),
            {
                "source_file", "output_file", "source_hash", "output_hash",
                "glossary_version_used", "entity_ids_used", "entity_hashes_used",
                "updated_at",
            },
        )
        self.assertEqual(record["source_file"], "chunk0001.md")
        self.assertEqual(record["output_file"], "output_chunk0001.md")
        self.assertRegex(record["source_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(record["source_hash"], expected_source_hash)
        self.assertEqual(record["output_hash"], expected_output_hash)
        self.assertEqual(record["entity_ids_used"], ["Tai"])
        self.assertEqual(list(record["entity_hashes_used"]), ["Tai"])
        self.assertTrue(record["glossary_version_used"])
        # ISO-8601 with an explicit UTC offset
        self.assertEqual(datetime.fromisoformat(record["updated_at"]).utcoffset(),
                         timezone.utc.utcoffset(None))

    def test_record_without_glossary_selects_no_entities(self):
        tmp, temp_dir = self._workspace(with_glossary=False)
        with tmp:
            record = run_state.build_chunk_record(str(temp_dir), "chunk0001")

        self.assertEqual(record["entity_ids_used"], [])
        self.assertEqual(record["entity_hashes_used"], {})
        self.assertEqual(record["glossary_version_used"], "")

    def test_unknown_chunk_id_raises_value_error(self):
        tmp, temp_dir = self._workspace(with_glossary=False)
        with tmp:
            with self.assertRaisesRegex(ValueError, "Unknown chunk id 'chunk0099'"):
                run_state.build_chunk_record(str(temp_dir), "chunk0099")

    def test_missing_source_chunk_raises_file_not_found(self):
        tmp, temp_dir = self._workspace(with_glossary=False)
        with tmp:
            os.remove(temp_dir / "chunk0001.md")
            with self.assertRaisesRegex(FileNotFoundError, "Source chunk not found"):
                run_state.build_chunk_record(str(temp_dir), "chunk0001")

    def test_missing_output_chunk_raises_file_not_found(self):
        tmp, temp_dir = self._workspace(with_glossary=False)
        with tmp:
            os.remove(temp_dir / "output_chunk0001.md")
            with self.assertRaisesRegex(FileNotFoundError, "Output chunk not found"):
                run_state.build_chunk_record(str(temp_dir), "chunk0001")

    def test_empty_output_chunk_raises_value_error(self):
        tmp, temp_dir = self._workspace(with_glossary=False)
        with tmp:
            (temp_dir / "output_chunk0001.md").write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Output chunk is empty"):
                run_state.build_chunk_record(str(temp_dir), "chunk0001")

    def test_blank_output_chunk_raises_value_error(self):
        tmp, temp_dir = self._workspace(with_glossary=False)
        with tmp:
            (temp_dir / "output_chunk0001.md").write_text(" \n\t", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "whitespace-only"):
                run_state.build_chunk_record(str(temp_dir), "chunk0001")

    def test_unreadable_output_chunk_raises_value_error(self):
        tmp, temp_dir = self._workspace(with_glossary=False)
        with tmp:
            (temp_dir / "output_chunk0001.md").write_bytes(b"\xff\xfe\x00\x01")
            with self.assertRaisesRegex(ValueError, "readable UTF-8"):
                run_state.build_chunk_record(str(temp_dir), "chunk0001")


if __name__ == "__main__":
    unittest.main()
