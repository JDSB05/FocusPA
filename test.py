"""Simple unit tests covering the chat and anomaly services metrics."""

from __future__ import annotations

import csv
import json
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Test environment bootstrap
# ---------------------------------------------------------------------------

# Ensure metrics are written to a deterministic path for assertions.
METRICS_PATH = Path("test_metrics.csv")
os.environ["LLM_METRICS_CSV_PATH"] = str(METRICS_PATH)

# Provide lightweight stubs for optional heavy dependencies before importing
# the application modules.
mock_st = types.ModuleType("sentence_transformers")
mock_embedder = MagicMock()
mock_embedder.encode.return_value = [[0.0]]
mock_st.SentenceTransformer = MagicMock(return_value=mock_embedder)
mock_st.util = types.ModuleType("sentence_transformers.util")
sys.modules.setdefault("sentence_transformers", mock_st)

mock_chromadb = types.ModuleType("chromadb")
mock_chroma_client = MagicMock()
mock_chroma_client.heartbeat.return_value = True
mock_chromadb.HttpClient = MagicMock(return_value=mock_chroma_client)
sys.modules.setdefault("chromadb", mock_chromadb)

# Avoid outbound HTTP calls when Elasticsearch health is checked.
requests_get_patcher = patch(
    "requests.get", return_value=SimpleNamespace(status_code=200, text="ok")
)
requests_get_patcher.start()

# Now the application modules can be imported safely.
from app.controllers import rag_controller  # noqa: E402
from app.services import anomaly_service  # noqa: E402


class MetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        if METRICS_PATH.exists():
            METRICS_PATH.unlink()

    def tearDown(self) -> None:
        if METRICS_PATH.exists():
            METRICS_PATH.unlink()

    def _read_metrics(self):
        with METRICS_PATH.open("r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_query_hybrid_rag_metrics_logged(self):
        fake_es_docs = [
            {
                "@timestamp": "2024-01-01T00:00:00Z",
                "event.code": "1000",
                "winlog.event_id": "4625",
                "user": {"name": "alice"},
                "message": "Falha de logon detectada.",
            }
        ]
        fake_chroma_docs = [{"text": "[POLICY] Apenas admins podem aceder."}]

        with patch.object(rag_controller, "reformulate_for_es", return_value="{\"query\":{\"match_all\":{}}}"), \
            patch.object(rag_controller, "es_search", return_value=fake_es_docs), \
            patch.object(rag_controller, "chroma_search", return_value=fake_chroma_docs), \
            patch.object(rag_controller, "ask_llm", return_value="Resposta final"):
            response = rag_controller.query_hybrid_rag(
                "Existe algum log suspeito?",
                max_es_logs=1,
                max_chroma_chunks=1,
            )

        self.assertEqual(response, "Resposta final")
        rows = self._read_metrics()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["service"], "chat")
        self.assertEqual(row["operation"], "hybrid_rag")
        self.assertEqual(row["num_es_logs"], "1")
        self.assertEqual(row["num_chroma_chunks"], "1")
        self.assertEqual(row["success"], "yes")

    def test_classify_events_metrics_logged(self):
        response_payload = json.dumps([
            {
                "id": "log-1",
                "description": "Tentativa de login suspeita",
                "severity": "high",
            }
        ])

        with patch.object(anomaly_service, "ask_llm", return_value=response_payload):
            result = anomaly_service.classify_events_with_rag(
                "Eventos críticos",
                "Contexto adicional",
                events_count=3,
            )

        self.assertNotEqual(result, "null")
        rows = self._read_metrics()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["service"], "anomaly")
        self.assertEqual(row["operation"], "classify_events")
        self.assertEqual(row["events_considered"], "3")
        self.assertEqual(row["success"], "yes")


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        requests_get_patcher.stop()
