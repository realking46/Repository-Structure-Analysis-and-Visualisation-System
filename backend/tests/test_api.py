from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


class ApiTests(unittest.TestCase):
    def test_health_endpoint(self) -> None:
        client = TestClient(app)

        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ai_status_endpoint_does_not_expose_secrets(self) -> None:
        client = TestClient(app)

        response = client.get("/api/ai/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data["activeProvider"], {"local", "openai", "gemini"})
        self.assertIn("cacheEntries", data)
        self.assertNotIn("apiKey", data)

    def test_analyze_endpoint_returns_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("import b\n", encoding="utf-8")
            (root / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
            client = TestClient(app)

            response = client.get("/api/analyze", params={"path": str(root)})

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["totalFiles"], 2)
            self.assertEqual(len(data["edges"]), 1)


if __name__ == "__main__":
    unittest.main()
