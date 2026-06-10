from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.analyzer import analyze_repository
from app import analyzer


class AnalyzerTests(unittest.TestCase):
    def test_detects_internal_python_import_edges_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "pkg"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "helper.py").write_text("def help_me():\n    return 1\n", encoding="utf-8")
            (package / "service.py").write_text("from . import helper\n\nif True:\n    helper.help_me()\n", encoding="utf-8")
            (root / "main.py").write_text("from pkg import service\n", encoding="utf-8")

            graph = analyze_repository(root)

            self.assertEqual(graph["totalFiles"], 4)
            self.assertGreaterEqual(graph["totalLoc"], 4)
            edge_pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
            self.assertIn(("main.py", "pkg/service.py"), edge_pairs)
            self.assertIn(("pkg/service.py", "pkg/helper.py"), edge_pairs)
            nodes = {node["path"]: node for node in graph["nodes"]}
            self.assertEqual(nodes["pkg/service.py"]["fanIn"], 1)
            self.assertEqual(nodes["pkg/service.py"]["fanOut"], 1)
            self.assertGreater(nodes["pkg/service.py"]["hotspotScore"], nodes["pkg/__init__.py"]["hotspotScore"])
            directories = {item["path"]: item for item in graph["directories"]}
            self.assertEqual(directories["pkg"]["files"], 3)
            self.assertEqual(directories["pkg"]["incomingImports"], 2)
            self.assertGreater(directories["pkg"]["hotspotScore"], directories["root"]["hotspotScore"])

    def test_ignores_dependency_and_build_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "node_modules").mkdir()
            (root / "dist").mkdir()
            (root / "src" / "index.ts").write_text("import './view'\n", encoding="utf-8")
            (root / "src" / "view.ts").write_text("export const view = 1\n", encoding="utf-8")
            (root / "node_modules" / "library.ts").write_text("export const hidden = 1\n", encoding="utf-8")
            (root / "dist" / "bundle.js").write_text("console.log('hidden')\n", encoding="utf-8")

            graph = analyze_repository(root)

            paths = {node["path"] for node in graph["nodes"]}
            self.assertEqual(paths, {"src/index.ts", "src/view.ts"})
            self.assertEqual(len(graph["edges"]), 1)

    def test_detects_javascript_and_cpp_internal_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "web").mkdir()
            (root / "native").mkdir()
            (root / "web" / "app.ts").write_text(
                "import { view } from './view'\nconsole.log(view)\n",
                encoding="utf-8",
            )
            (root / "web" / "view.ts").write_text("export const view = 'repo'\n", encoding="utf-8")
            (root / "native" / "main.cpp").write_text(
                '#include "graph.hpp"\nint main() { return 0; }\n',
                encoding="utf-8",
            )
            (root / "native" / "graph.hpp").write_text("#pragma once\n", encoding="utf-8")

            graph = analyze_repository(root)

            edge_pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
            self.assertIn(("web/app.ts", "web/view.ts"), edge_pairs)
            self.assertIn(("native/main.cpp", "native/graph.hpp"), edge_pairs)
            directories = {item["path"]: item for item in graph["directories"]}
            self.assertEqual(directories["web"]["internalImports"], 1)
            self.assertEqual(directories["native"]["internalImports"], 1)

    def test_skips_oversized_source_files_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "small.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "large.py").write_text("x = 1\n" * 200, encoding="utf-8")
            original_limit = analyzer.MAX_SOURCE_FILE_BYTES
            analyzer.MAX_SOURCE_FILE_BYTES = 128

            try:
                graph = analyze_repository(root)
            finally:
                analyzer.MAX_SOURCE_FILE_BYTES = original_limit

            paths = {node["path"] for node in graph["nodes"]}
            self.assertEqual(paths, {"small.py"})
            self.assertEqual(graph["skippedFiles"][0]["path"], "large.py")
            self.assertTrue(graph["warnings"])


if __name__ == "__main__":
    unittest.main()
