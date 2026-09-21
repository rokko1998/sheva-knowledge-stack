from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_stack import notebook, pipeline, state
from knowledge_stack.decisions import typesafe


class BoundaryTests(unittest.TestCase):
    def test_pending_capture_and_completion_preserve_private_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(state, "STATE", Path(tmp)):
                transcript = Path(tmp) / "source.jsonl"
                transcript.write_text('{"message":"decision"}\n', encoding="utf-8")
                pending = state.capture({"session_id": "session/1", "cwd": tmp, "transcript_path": str(transcript), "hook_event_name": "SessionEnd"})
                record = json.loads(pending.read_text(encoding="utf-8"))
                snapshot = Path(record["transcript_path"])
                self.assertEqual(snapshot.read_text(encoding="utf-8"), transcript.read_text(encoding="utf-8"))
                self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
                state.mark_done("session/1")
                self.assertFalse(pending.exists())

    def test_missing_official_jev_key_requires_review_instead_of_dropping_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "candidates.json"
            output = Path(tmp) / "review.json"
            source.write_text(json.dumps({"session_id": "s", "candidates": [{"title": "Decision", "body": "Keep this", "jev_safe": True}]}), encoding="utf-8")
            with patch.object(typesafe, "get_typesafe_key", return_value=None):
                result = pipeline.classify(source, output)
            self.assertEqual(result["candidates"][0]["retention"], "UNCERTAIN")
            self.assertEqual(result["candidates"][0]["route"], "REVIEW")
            self.assertFalse(result["reviewed_by_agent"])

    def test_official_jev_adapter_uses_documented_choice_contract(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps({
                    "model": "jev-1.13.0",
                    "answers": {
                        "retention": {"type": "choice", "choice": "KEEP", "confidence": 0.9, "probabilities": {"KEEP": 0.95, "DROP": 0.02, "UNCERTAIN": 0.03}},
                        "route": {"type": "choice", "choice": "LOCAL_ONLY", "confidence": 0.8, "probabilities": {"LOCAL_ONLY": 0.9, "LOCAL_AND_AI_BRAIN": 0.05, "REVIEW": 0.05}},
                    },
                }).encode()

        captured = {}

        def fake_urlopen(request, timeout, context):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data)
            self.assertEqual(timeout, 15)
            self.assertIsNotNone(context)
            return FakeResponse()

        with patch.object(typesafe, "urlopen", side_effect=fake_urlopen):
            result = typesafe.TypeSafeJevProvider("test-key").evaluate("Decision", "Durable architecture")
        self.assertEqual(captured["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(captured["payload"]["questions"]["retention"]["type"], "choice")
        self.assertEqual(result.retention.choice, "KEEP")

    def test_apply_refuses_unreviewed_and_unresolved_plan(self) -> None:
        base = {"session_id": "s", "candidates": [{"title": "Decision", "body": "Long-term choice", "retention": "KEEP", "route": "LOCAL_ONLY"}]}
        with self.assertRaisesRegex(ValueError, "semantic review"):
            pipeline._validate_for_apply(base)
        base["reviewed_by_agent"] = True
        base["candidates"][0]["route"] = "REVIEW"
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            pipeline._validate_for_apply(base)

    def test_projection_refuses_secret_before_google_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox"
            outbox.mkdir()
            (outbox / "a.json").write_text(json.dumps({"title": "bad", "body": "api_key=abcdef"}), encoding="utf-8")
            with patch.object(notebook, "STATE", Path(tmp)):
                with self.assertRaisesRegex(ValueError, "Potential secret"):
                    notebook.projection()

    def test_existing_text_source_is_not_replaced_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            with patch.object(notebook, "preflight", return_value={"id": "n", "managed_source_title": "managed"}), \
                 patch.object(notebook, "projection", return_value=("new content", "new hash")), \
                 patch.object(notebook, "_run", return_value={"sources": [{"id": "s1", "title": "managed", "status": "ready"}]}), \
                 patch.object(notebook, "STATE", state_dir):
                (state_dir / "publication.json").write_text(json.dumps({"source_id": "s1", "content_hash": "old hash"}), encoding="utf-8")
                result = notebook.publish()
                self.assertEqual(result["status"], "needs_refresh")


if __name__ == "__main__":
    unittest.main()
