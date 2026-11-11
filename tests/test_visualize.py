"""Проверка Graphviz DOT, SVG и ASCII-дерева."""

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src.main import build_graph, main
from src.visualize import (
    dot_name,
    export_visualization,
    format_ascii_tree,
    graph_to_dot,
    show_visualization,
)

ROOT = Path(__file__).resolve().parent.parent

CYCLE = {
    "A": ["B", "C"],
    "B": ["D"],
    "C": ["D"],
    "D": ["A"],
}

DIAMOND = {
    "A": ["B", "C"],
    "B": ["D"],
    "C": ["D"],
    "D": [],
}


class VisualizationTests(unittest.TestCase):
    """Проверить визуализацию разных видов графов."""

    def test_direct_edges(self):
        """Проверить направление стрелок в DOT."""
        dot = graph_to_dot("A", CYCLE)
        self.assertIn('"A" -> "B";', dot)
        self.assertIn('"D" -> "A";', dot)
        self.assertTrue(dot.startswith("digraph"))

    def test_reverse_edges(self):
        """Проверить направление обратных зависимостей."""
        reverse = {
            "D": ["C"],
            "C": ["B"],
            "B": [],
        }
        dot = graph_to_dot("D", reverse, reverse=True)
        self.assertIn('"C" -> "D";', dot)
        self.assertNotIn('"D" -> "C";', dot)

    def test_isolated_node(self):
        """Проверить пакет без зависимостей."""
        dot = graph_to_dot("A", {"A": []})
        self.assertIn('"A" [style=', dot)
        self.assertNotIn(" -> ", dot)

    def test_boundary_node(self):
        """Проверить обозначение предела глубины."""
        dot = graph_to_dot("A", {
            "A": ["B"],
            "B": None,
        })
        self.assertIn('"B" [style="rounded,dashed"]', dot)

    def test_escaped_node(self):
        """Проверить экранирование кавычек."""
        self.assertEqual(dot_name('A"B'), '"A\\"B"')

    def test_cycle_tree(self):
        """Проверить дерево с циклической зависимостью."""
        tree = format_ascii_tree("A", CYCLE)
        self.assertIn("A (цикл)", tree)
        self.assertIn("D (повтор)", tree)

    def test_diamond_tree(self):
        """Проверить повторяющуюся зависимость."""
        tree = format_ascii_tree("A", DIAMOND)
        self.assertIn("D (повтор)", tree)
        self.assertNotIn("(цикл)", tree)

    def test_boundary_tree(self):
        """Проверить ограничение глубины."""
        graph = {
            "A": ["B"],
            "B": None,
        }
        self.assertIn(
            "B (предел глубины)",
            format_ascii_tree("A", graph),
        )
        self.assertIn(
            "(предел глубины)",
            format_ascii_tree("A", {"A": None}),
        )

    def test_empty_tree(self):
        """Проверить дерево без зависимостей."""
        self.assertEqual(
            format_ascii_tree("A", {"A": []}),
            "A",
        )

    def test_ascii_only_when_enabled(self):
        """Проверить выключение ASCII-дерева."""
        output = io.StringIO()
        settings = {
            "output_file": "out.svg",
            "ascii_tree": False,
        }

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"

            with patch("src.visualize.export_visualization") as export:
                export.return_value = (
                    Path("out.dot"),
                    Path("out.svg"),
                )

                with redirect_stdout(output):
                    show_visualization(
                        "A", {"A": []}, settings, path, False
                    )

        self.assertNotIn("ASCII-дерево", output.getvalue())

    def test_ascii_reverse_heading(self):
        """Проверить заголовок обратного ASCII-дерева."""
        output = io.StringIO()
        settings = {
            "output_file": "out.svg",
            "ascii_tree": True,
        }

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"

            with patch("src.visualize.export_visualization") as export:
                export.return_value = (
                    Path("out.dot"),
                    Path("out.svg"),
                )

                with redirect_stdout(output):
                    show_visualization(
                        "A", {"A": []}, settings, path, True
                    )

        self.assertIn(
            "ASCII-дерево обратных зависимостей:",
            output.getvalue(),
        )

    def test_missing_dot_command(self):
        """Проверить отсутствие Graphviz."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"

            with patch(
                "src.visualize.subprocess.run",
                side_effect=FileNotFoundError,
            ):
                with self.assertRaisesRegex(
                    ValueError, "dot не найдена"
                ):
                    export_visualization(
                        "A", {"A": []}, path, "out.svg"
                    )

            self.assertTrue(
                (Path(folder) / "out.dot").exists()
            )

    def test_graphviz_error(self):
        """Проверить ошибку преобразования в SVG."""
        error = subprocess.CalledProcessError(
            1, "dot", stderr="broken"
        )

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"

            with patch(
                "src.visualize.subprocess.run",
                side_effect=error,
            ):
                with self.assertRaisesRegex(
                    ValueError, "broken"
                ):
                    export_visualization(
                        "A", {"A": []}, path, "out.svg"
                    )

    def test_export_command(self):
        """Проверить команду запуска Graphviz."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"

            with patch("src.visualize.subprocess.run") as call:
                export_visualization(
                    "A", {"A": []}, path, "out.svg"
                )

            command = call.call_args.args[0]

            self.assertEqual(
                command[:2],
                ["dot", "-Tsvg"],
            )
            self.assertEqual(
                command[-2:],
                ["-o", str(path.parent / "out.svg")],
            )

    @unittest.skipUnless(
        shutil.which("dot"),
        "Graphviz не установлен",
    )
    def test_actual_svg(self):
        """Проверить создание настоящего SVG."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.yaml"

            dot_file, svg_file = export_visualization(
                "A", CYCLE, path, "out.svg"
            )

            self.assertIn(
                "digraph",
                dot_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "<svg",
                svg_file.read_text(encoding="utf-8"),
            )

    def test_compatibility_of_bfs(self):
        """Проверить совместимость с BFS третьего этапа."""
        graph = build_graph(
            "A", 3, CYCLE.__getitem__
        )

        dot = graph_to_dot("A", graph)
        self.assertIn('"D" -> "A";', dot)

    def test_old_cli_works_without_dot(self):
        """Проверить запуск без визуализации."""
        path = ROOT / "config-test.yaml"

        with patch(
            "sys.argv",
            ["main.py", "--config", str(path)],
        ):
            with patch(
                "src.main.show_visualization"
            ) as visualization:
                with redirect_stdout(io.StringIO()):
                    main()

        visualization.assert_not_called()

    def test_cli_visualize_flag(self):
        """Проверить работу флага --visualize."""
        path = ROOT / "config-test.yaml"

        argv = [
            "main.py",
            "--config",
            str(path),
            "--visualize",
        ]

        with patch("sys.argv", argv):
            with patch(
                "src.main.show_visualization"
            ) as visualization:
                with redirect_stdout(io.StringIO()):
                    main()

        visualization.assert_called_once()


if __name__ == "__main__":
    unittest.main()