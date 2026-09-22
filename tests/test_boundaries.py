from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_stack import notebook, pipeline, reverse, state, wiki_adapter
from knowledge_stack.decisions import typesafe
from knowledge_stack.policy import choice_questions
from knowledge_stack.paths import DATAWEAVE
from hooks import codex as codex_hook


def candidate() -> dict:
    return {
        "candidate_id": "c1", "kind": "decision", "title": "Project decision",
        "body": "The project selected option A.",
        "evidence": [{"source": "transcript", "locator": "turn:1", "excerpt": "We selected option A for this project."}],
        "scope": {"project": "fixture", "domain": "test"},
        "jev_safe": True, "cloud_safe": True,
    }


def answer(choice: str) -> typesafe.ChoiceResult:
    return typesafe.ChoiceResult(choice, 0.7, {choice: 0.7})


class BoundaryTests(unittest.TestCase):
    def test_policy_questions_are_complete(self) -> None:
        for policy in ("pass-a", "pass-b", "end-intent"):
            self.assertTrue(choice_questions(policy))

    def test_jev_choice_api_uses_documented_shape(self) -> None:
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self):
                return json.dumps({"model": "jev-1.13.0", "answers": {
                    "end_intent": {"type": "choice", "choice": "CONTINUE", "confidence": 0.8,
                                   "probabilities": {"SESSION_END": 0.1, "CONTINUE": 0.8, "UNCERTAIN": 0.1}}
                }}).encode()
        captured = {}
        def fake_urlopen(request, timeout, context):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data)
            self.assertEqual(timeout, 15)
            self.assertIsNotNone(context)
            return FakeResponse()
        with patch.object(typesafe, "urlopen", side_effect=fake_urlopen):
            result = typesafe.TypeSafeJevProvider("test-key").end_intent("закончили миграцию, теперь тесты")
        self.assertEqual(captured["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(captured["payload"]["questions"]["end_intent"]["type"], "choice")
        self.assertEqual(result.answers["end_intent"].choice, "CONTINUE")

    def test_two_pass_jev_only_retrieves_after_supported_keep(self) -> None:
        class FakeProvider:
            def pass_a(self, _):
                return typesafe.JevResult({"evidence_support": answer("SUPPORTED"), "retention": answer("KEEP")}, "fixture")
            def pass_b(self, _, matches, wiki):
                self_matches.append((matches, wiki))
                return typesafe.JevResult({"canonical_relation": answer("NEW"), "canonical_representation": answer("ATOMIC"), "ai_brain_bucket": answer("DECISIONS")}, "fixture")
        self_matches = []
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/"in.json", Path(tmp)/"out.json"
            source.write_text(json.dumps({"session_id": "s", "candidates": [candidate()]}))
            with patch.object(pipeline, "TypeSafeJevProvider", return_value=FakeProvider()), \
                 patch.object(pipeline, "retrieve", return_value=([{"path": "old.md"}], [])) as retrieve:
                result = pipeline.classify(source, output)
            self.assertEqual(result["candidates"][0]["status"], "READY")
            self.assertEqual(self_matches, [([{"path": "old.md"}], [])])
            retrieve.assert_called_once()

    def test_missing_jev_keeps_candidate_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/"in.json", Path(tmp)/"out.json"
            source.write_text(json.dumps({"session_id": "s", "candidates": [candidate()]}))
            with patch.object(pipeline, "TypeSafeJevProvider", side_effect=RuntimeError("no token")), \
                 patch.object(pipeline, "retrieve") as retrieve:
                result = pipeline.classify(source, output)
            self.assertEqual(result["candidates"][0]["status"], "REVIEW")
            retrieve.assert_not_called()

    def test_pending_completion_does_not_recreate_same_revision(self) -> None:
        def line(text):
            return json.dumps({"type":"response_item", "payload":{"type":"message", "role":"user", "content":[{"type":"input_text", "text":text}]}})+"\n"
        with tempfile.TemporaryDirectory() as tmp, patch.object(state, "STATE", Path(tmp)):
            transcript = Path(tmp)/"source.jsonl"
            transcript.write_text(line("пока"))
            event = {"session_id":"session/1", "cwd":tmp, "transcript_path":str(transcript), "hook_event_name":"UserPromptSubmit", "prompt":"пока"}
            record = state.capture(event)
            self.assertEqual(Path(json.loads(record.read_text())["transcript_path"]).stat().st_mode & 0o777, 0o600)
            state.mark_done("session/1")
            event.pop("prompt")
            event["hook_event_name"] = "SessionEnd"
            self.assertIsNone(state.capture(event))
            transcript.write_text(line("пока")+line("новый запрос"))
            self.assertIsNotNone(state.capture(event))

    def test_hook_injects_only_for_session_end(self) -> None:
        class FakeProvider:
            def end_intent(self, message):
                selected = "CONTINUE" if "тесты" in message else "SESSION_END"
                return typesafe.JevResult({"end_intent":answer(selected)}, "fixture")
        def invoke(prompt: str) -> str:
            event = {"hook_event_name":"UserPromptSubmit", "session_id":"s", "prompt":prompt}
            output = io.StringIO()
            with patch.object(codex_hook.sys, "stdin", io.StringIO(json.dumps(event))), \
                 patch.object(codex_hook.sys, "stdout", output), \
                 patch.object(codex_hook, "TypeSafeJevProvider", return_value=FakeProvider()), \
                 patch.object(codex_hook, "capture", return_value=Path("/tmp/pending.json")) as capture:
                codex_hook.main()
                if "завтра" in prompt:
                    capture.assert_called_once()
                else:
                    capture.assert_not_called()
            return output.getvalue()
        self.assertEqual(invoke("Закончили миграцию, теперь проверим тесты"), "")
        self.assertIn("В ЭТОМ turn", invoke("Ладно, оставим до завтра"))
        self.assertEqual(invoke("Давай писать код"), "")

    def test_apply_blocks_review_and_unexplained_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = {"session_id":"s", "candidates":[{**candidate(), "status":"REVIEW", "classified_status":"REVIEW"}]}
            file = Path(tmp)/"plan.json"
            file.write_text(json.dumps(plan))
            self.assertEqual(pipeline.apply(file)["status"], "needs_semantic_work")
            plan["candidates"][0]["status"] = "READY"
            file.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "agent_resolution"):
                pipeline.apply(file)

    def test_projection_reads_live_canonical_and_rejects_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root/"note.md").write_text("current value")
            cfg = {"buckets": {"DECISIONS": {"title":"x", "drive_path":"gdrive:x/y.txt"}}}
            with patch.object(notebook, "_config", return_value=cfg), \
                 patch.object(notebook, "vault_path", return_value=root), \
                 patch.object(notebook, "load_catalog", return_value={"note.md":{"bucket":"DECISIONS","status":"active"}}):
                self.assertIn("current value", notebook.projection("DECISIONS")[0])
                (root/"note.md").write_text("updated value")
                self.assertIn("updated value", notebook.projection("DECISIONS")[0])
                (root/"note.md").write_text("api_key=abcdef")
                with self.assertRaisesRegex(ValueError, "Potential secret"):
                    notebook.projection("DECISIONS")

    def test_real_dataweave_writer_creates_and_semantically_updates_in_temp_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            runtime, vault = root/"runtime", root/"vault"
            shutil.copytree(DATAWEAVE.resolve()/"scripts", runtime/"scripts")
            (runtime/"config.toml").write_text(
                f'[vault]\nvault_path = "{vault}"\nnotes_folder = "Research & Insights"\n'
                f'moc_folder = "Guides & Overviews"\nsource_folder = "Sources"\ncontacts_folder = "Networking"\n'
                f'[memory]\nenabled = true\ndb_dir = "{root/"db"}"\ntokenizer = "unicode61"\nauto_update = true\n'
                '[wiki]\nwiki_folder = "LLM Wiki"\n', encoding="utf-8")
            vault.mkdir()
            with patch.object(pipeline, "verify_runtime", return_value=runtime), \
                 patch.object(pipeline, "vault_path", return_value=vault):
                relative = pipeline._write_atomic({"candidate_id":"c1", "title":"Temporary fact", "body":"Original [[Known Link]] fact."}, "s", root/"stage1")
                target = vault/relative
                self.assertTrue(target.is_file())
                with self.assertRaisesRegex(ValueError, "wikilinks"):
                    pipeline._write_atomic({"candidate_id":"c2", "mutation":{"merged_body":"Changed fact without link."}}, "s", root/"stage2", target=target)
                updated = pipeline._write_atomic({"candidate_id":"c2", "mutation":{"merged_body":"Original [[Known Link]] fact with the verified update."}}, "s", root/"stage3", target=target)
            self.assertEqual(relative, updated)
            self.assertIn("verified update", target.read_text(encoding="utf-8"))
            self.assertEqual(len(list((vault/"Research & Insights").glob("*.md"))), 1)

    def test_real_dataweave_wiki_writer_preserves_existing_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            runtime, vault = root/"runtime", root/"vault"
            wiki = vault/"LLM Wiki"/"test-stack"
            shutil.copytree(DATAWEAVE.resolve()/"scripts", runtime/"scripts")
            (runtime/"config.toml").write_text(
                f'[vault]\nvault_path = "{vault}"\nnotes_folder = "Research & Insights"\n'
                f'moc_folder = "Guides & Overviews"\nsource_folder = "Sources"\ncontacts_folder = "Networking"\n'
                f'[memory]\nenabled = true\ndb_dir = "{root/"db"}"\ntokenizer = "unicode61"\nauto_update = true\n'
                '[wiki]\nwiki_folder = "LLM Wiki"\ndefault_mode = "project"\ndefault_lang = "ru"\n', encoding="utf-8")
            wiki.mkdir(parents=True)
            (wiki/"SCHEMA.md").write_text('---\nnote_type: wiki\nwiki_project: test-stack\nwiki_page_type: meta\nwiki_status: stable\ndate: 2026-09-22\nwiki_mode: project\n---\n\n# Test\n')
            def fm(kind: str, stem: str) -> dict:
                return {"note_type":"wiki", "wiki_project":"test-stack", "wiki_page_type":kind,
                        "wiki_status":"ingested" if kind == "raw" else "draft", "date":"2026-09-22",
                        "source_doc":f"wiki:test-stack:{kind}:{stem}", **({"raw_kind":"docs"} if kind == "raw" else {})}
            first = {"project":"test-stack", "compile_id":"fixture-1", "creates":[
                {"rel_path":"raw/docs/source.md", "frontmatter":fm("raw","source"), "body":"# Source\n\nEvidence."},
                {"rel_path":"entities/fixture.md", "frontmatter":fm("entity","fixture"), "body":"# Fixture\n\nA [[source]] fact."}],
                "updates":[], "renames":[], "open_questions":[], "contradictions":[]}
            with patch.object(wiki_adapter, "verify_runtime", return_value=runtime):
                relative = wiki_adapter.apply_changeset({"mutation":{"type":"wiki_changeset", "changeset":first,
                    "expected_sha256":{}, "primary_path":"entities/fixture.md"}}, root/"stage1")
                self.assertEqual(relative, "LLM Wiki/test-stack/entities/fixture.md")
                target = vault/relative
                before = hashlib.sha256(target.read_bytes()).hexdigest()
                second = {"project":"test-stack", "compile_id":"fixture-2", "creates":[
                    {"rel_path":"raw/docs/source2.md", "frontmatter":fm("raw","source2"), "body":"# Source 2\n\nNew evidence."}],
                    "updates":[{"rel_path":"entities/fixture.md", "expected_existing_links":["source"],
                        "frontmatter":fm("entity","fixture"), "body":"# Fixture\n\nLink removed."}],
                    "renames":[], "open_questions":[], "contradictions":[]}
                with self.assertRaisesRegex(RuntimeError, "Wikilink preservation guard"):
                    wiki_adapter.apply_changeset({"mutation":{"type":"wiki_changeset", "changeset":second,
                        "expected_sha256":{"entities/fixture.md":before}, "primary_path":"entities/fixture.md"}}, root/"stage2")
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), before)

    def test_seven_source_migration_preserves_legacy_until_all_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"id":"n", "title":"AI Brain", "buckets":{
                "PROJECTS":{"title":"managed-projects", "drive_path":"gdrive:x/projects.txt"},
                "DECISIONS":{"title":"managed-decisions", "drive_path":"gdrive:x/decisions.txt"}}}
            data = {"source_id":"old", "drive_file_id":"d-old", "title":"managed-old", "drive_path":"gdrive:x/old.txt"}
            path = Path(tmp)/"publication.json"
            path.write_text(json.dumps(data))
            live = [{"id":"old", "title":"managed-old", "drive_document_id":"d-old", "status":"ready"}]
            calls = {"add":0, "deleted":[]}
            def fake_run(*args, **kwargs):
                if args[:2] == ("source","list"):
                    return {"notebook_id":"n", "sources":list(live)}
                if args[:2] == ("source","add-drive"):
                    calls["add"] += 1
                    if calls["add"] == 2 and not calls.get("retried"):
                        raise RuntimeError("Google outage")
                    sid=f"s{calls['add']}"
                    live.append({"id":sid,"title":args[3],"drive_document_id":args[2],"status":"ready"})
                    return {"source":{"id":sid}}
                if args[:2] == ("source","delete"):
                    calls["deleted"].append(args[2])
                    live[:]=[s for s in live if s["id"]!=args[2]]
                return {}
            def fake_upload(local_file, remote_path, *, expected_id):
                return expected_id or "d-"+Path(remote_path).stem
            with patch.object(notebook, "STATE", Path(tmp)), \
                 patch.object(notebook, "preflight", return_value=cfg), \
                 patch.object(notebook, "projections", return_value={"PROJECTS":("project", "h1"),"DECISIONS":("decision","h2")}), \
                 patch.object(notebook, "_run", side_effect=fake_run), \
                 patch.object(notebook.drive, "file_id", return_value=None), \
                 patch.object(notebook.drive, "upload", side_effect=fake_upload):
                with self.assertRaisesRegex(RuntimeError, "Google outage"):
                    notebook.publish()
                self.assertEqual(calls["deleted"], [])
                self.assertNotIn("active_schema", json.loads(path.read_text()))
                calls["retried"] = True
                result = notebook.publish()
            self.assertEqual(result["status"], "ready")
            self.assertEqual(calls["deleted"], ["old"])
            recovered = json.loads(path.read_text())
            self.assertEqual(recovered["active_schema"], "seven-buckets-v1")
            recovered["legacy"]["retired"] = False  # Crash after remote delete, before registry commit.
            path.write_text(json.dumps(recovered))
            with patch.object(notebook, "STATE", Path(tmp)), \
                 patch.object(notebook, "preflight", return_value=cfg), \
                 patch.object(notebook, "projections", return_value={"PROJECTS":("project", "h1"),"DECISIONS":("decision","h2")}), \
                 patch.object(notebook, "_run", side_effect=fake_run), \
                 patch.object(notebook.drive, "file_id", return_value=None), \
                 patch.object(notebook.drive, "upload", side_effect=fake_upload):
                notebook.publish()
            self.assertEqual(calls["deleted"], ["old"])
            self.assertTrue(json.loads(path.read_text())["legacy"]["retired"])

    def test_drive_creation_recovers_only_matching_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"id":"n", "buckets":{"PROJECTS":{"title":"owned", "drive_path":"gdrive:x/projects.txt"}}}
            path = Path(tmp)/"publication.json"
            path.write_text(json.dumps({"sources":{"PROJECTS":{"creation_intent":"h1", "title":"owned", "drive_path":"gdrive:x/projects.txt"}}}))
            live = []
            def fake_run(*args, **_kwargs):
                if args[:2] == ("source","list"):
                    return {"notebook_id":"n", "sources":live}
                if args[:2] == ("source","add-drive"):
                    live.append({"id":"s1", "title":"owned", "drive_document_id":"d1", "status":"ready"})
                    return {"source":{"id":"s1"}}
                return {}
            with patch.object(notebook, "STATE", Path(tmp)), \
                 patch.object(notebook, "preflight", return_value=cfg), \
                 patch.object(notebook, "projections", return_value={"PROJECTS":("project", "h1")}), \
                 patch.object(notebook, "_run", side_effect=fake_run), \
                 patch.object(notebook.drive, "file_id", return_value="d1"), \
                 patch.object(notebook.drive, "content_matches", return_value=True) as verified, \
                 patch.object(notebook.drive, "upload", return_value="d1") as upload:
                notebook.publish()
            verified.assert_called_once_with("gdrive:x/projects.txt", "project")
            self.assertEqual(upload.call_args.kwargs["expected_id"], "d1")
            self.assertEqual(json.loads(path.read_text())["sources"]["PROJECTS"]["source_id"], "s1")

    def test_reverse_import_empty_notes_is_noop(self) -> None:
        cfg = {"id":"full-notebook-id"}
        with patch.object(reverse, "preflight", return_value=cfg), \
             patch.object(reverse, "_run", return_value={"notebook_id":cfg["id"], "notes":[], "count":0}), \
             patch.object(reverse, "verify_runtime") as runtime:
            self.assertEqual(reverse.import_notes(), {"status":"no_curated_notes", "notes":0})
        runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
