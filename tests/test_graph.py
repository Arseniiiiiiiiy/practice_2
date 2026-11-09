
"""Тесты рекурсивного BFS, ограничений глубины и тестовых графов."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src.main import (
    build_graph,
    build_npm_graph,
    build_test_graph,
    load_config,
    load_test_repository,
    main,
    resolve_version,
    version_matches,
)

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = "https://registry.npmjs.org"


class GraphTests(unittest.TestCase):
    """Проверить построение графа в ширину."""

    def test_cycle(self):
        """Цикл D -> A сохраняется без повторного обхода."""
        path = ROOT / "config-test.yaml"
        root, graph = build_test_graph(load_config(path), path)
        self.assertEqual(root, "A")
        self.assertEqual(graph, {
            "A": ["B", "C"],
            "B": ["D"],
            "C": ["D"],
            "D": ["A"],
        })

    def test_zero_depth(self):
        """При глубине ноль не исследовать соседей."""
        get_children = lambda node: self.fail("Не должно быть вызова")
        graph = build_graph("A", 0, get_children)
        self.assertEqual(graph, {"A": None})

    def test_one_level(self):
        """Проверить отсечение зависимостей на глубине один."""
        path = ROOT / "config-test-depth.yaml"
        settings = load_config(path)
        settings["max_depth"] = 1
        _, graph = build_test_graph(settings, path)
        self.assertEqual(graph, {"A": ["B"], "B": None})

    def test_two_levels(self):
        """Проверить отсечение зависимостей на глубине два."""
        path = ROOT / "config-test-depth.yaml"
        root, graph = build_test_graph(load_config(path), path)
        self.assertEqual(root, "A")
        self.assertEqual(graph, {
            "A": ["B"], "B": ["C"], "C": None,
        })

    def test_convergence(self):
        """Общий пакет D не должен обрабатываться дважды."""
        path = ROOT / "config-test-diamond.yaml"
        root, graph = build_test_graph(load_config(path), path)
        self.assertEqual(root, "A")
        self.assertEqual(graph["B"], ["D"])
        self.assertEqual(graph["C"], ["D"])
        self.assertEqual(len(graph), 4)

    def test_isolated(self):
        """Обработать пакет без зависимостей."""
        path = ROOT / "config-test-empty.yaml"
        _, graph = build_test_graph(load_config(path), path)
        self.assertEqual(graph, {"A": []})

    def test_bfs_order(self):
        """Обходить пакеты по уровням, а не в глубину."""
        neighbors = {
            "A": ["C", "B"], "B": ["D"], "C": ["E"],
            "D": [], "E": [],
        }
        graph = build_graph("A", 3, neighbors.__getitem__)
        self.assertEqual(list(graph), ["A", "B", "C", "D", "E"])

    def test_long_cycle(self):
        """Не зацикливаться при большой заданной глубине."""
        graph = build_graph("A", 50, lambda node: ["B"] if node == "A"
                            else ["A"])
        self.assertEqual(graph, {"A": ["B"], "B": ["A"]})

    def test_missing_root(self):
        """Сообщить об отсутствии выбранного тестового пакета."""
        path = ROOT / "config-test.yaml"
        settings = load_config(path)
        settings["package"] = "Z"
        with self.assertRaisesRegex(ValueError, "не найден"):
            build_test_graph(settings, path)

    def test_bad_json(self):
        """Отклонить поврежденный JSON-файл."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON"):
                load_test_repository(path)

    def test_invalid_dependencies(self):
        """Отклонить отсутствующую вершину в тестовом графе."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.json"
            path.write_text(json.dumps({"A": ["B"]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "отсутствует"):
                load_test_repository(path)

    def test_invalid_package_name(self):
        """Отклонить строчные имена тестовых пакетов."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.json"
            path.write_text(json.dumps({"a": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "имя пакета"):
                load_test_repository(path)

    def test_not_a_list(self):
        """Отклонить строку вместо списка зависимостей."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.json"
            path.write_text(json.dumps({"A": "B"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "списком"):
                load_test_repository(path)

    def test_cli_cycle(self):
        """Вывести найденные связи цикла из тестового репозитория."""
        output = io.StringIO()
        path = ROOT / "config-test.yaml"
        with patch("sys.argv", ["main.py", "--config", str(path)]):
            with redirect_stdout(output):
                main()
        self.assertIn("D -> A", output.getvalue())
        self.assertIn("A -> B, C", output.getvalue())

    def test_cli_depth(self):
        """Показывать узлы, остановленные ограничением глубины."""
        output = io.StringIO()
        path = ROOT / "config-test-depth.yaml"
        with patch("sys.argv", ["main.py", "--config", str(path)]):
            with redirect_stdout(output):
                main()
        self.assertIn("C -> (предел глубины)", output.getvalue())


class VersionTests(unittest.TestCase):
    """Проверить выбор точных npm-версий по ограничениям."""

    def test_caret(self):
        """Не выбирать следующую мажорную версию."""
        self.assertTrue(version_matches((4, 3, 1), "^4.1.0"))
        self.assertFalse(version_matches((5, 0, 0), "^4.1.0"))

    def test_zero_major(self):
        """Учитывать особую семантику ^0.x.y."""
        self.assertTrue(version_matches((0, 2, 9), "^0.2.3"))
        self.assertFalse(version_matches((0, 3, 0), "^0.2.3"))
        self.assertFalse(version_matches((0, 0, 9), "^0.0.4"))

    def test_tilde(self):
        """Не выбирать следующую минорную версию."""
        self.assertTrue(version_matches((1, 2, 9), "~1.2.3"))
        self.assertFalse(version_matches((1, 3, 0), "~1.2.3"))

    def test_comparisons(self):
        """Поддержать интервалы через операторы сравнения."""
        self.assertTrue(version_matches((1, 5, 0), ">=1.0.0 <2.0.0"))
        self.assertFalse(version_matches((2, 0, 0), ">=1.0.0 <2.0.0"))

    def test_alternatives(self):
        """Поддержать альтернативные диапазоны через ||."""
        self.assertTrue(version_matches((2, 1, 0), "^1.0.0 || ^2.0.0"))

    def test_unsupported(self):
        """Не подменять неподдерживаемый диапазон догадкой."""
        with self.assertRaisesRegex(ValueError, "не поддерживается"):
            version_matches((1, 2, 3), "file:../local")

    def test_resolve_highest(self):
        """Выбрать наибольшую стабильную подходящую версию."""
        cache = {"B": {
            "versions": {"1.0.0": {}, "1.5.0": {}, "2.0.0": {}},
            "dist-tags": {"latest": "2.0.0"},
        }}
        actual = resolve_version(REGISTRY, "B", "^1.0.0", cache)
        self.assertEqual(actual, "1.5.0")
        self.assertEqual(resolve_version(REGISTRY, "B", "latest", cache),
                         "2.0.0")

    def test_missing_range(self):
        """Сообщить, если подходящей версии не существует."""
        cache = {"B": {"versions": {"1.0.0": {}}}}
        with self.assertRaisesRegex(ValueError, "нет подходящей"):
            resolve_version(REGISTRY, "B", "^2.0.0", cache)

    def test_npm_transitive(self):
        """Разрешить диапазоны, сохранив версии в идентификаторах."""
        settings = {
            "repository": REGISTRY, "package": "A", "version": "1.0.0",
            "max_depth": 2,
        }
        dep_data = {
            ("A", "1.0.0"): {"B": "^1.0.0"},
            ("B", "1.5.0"): {"C": "~2.0.0"},
        }
        packuments = {
            "B": {"versions": {"1.0.0": {}, "1.5.0": {}}},
            "C": {"versions": {"2.0.0": {}, "2.1.0": {}}},
        }
        with patch("src.main.fetch_direct_dependencies") as direct:
            direct.side_effect = lambda _, name, ver: dep_data[name, ver]
            with patch("src.main.fetch_packument") as packument:
                packument.side_effect = lambda _, name: packuments[name]
                root, graph = build_npm_graph(settings)
        self.assertEqual(root, "A@1.0.0")
        self.assertEqual(graph, {
            "A@1.0.0": ["B@1.5.0"],
            "B@1.5.0": ["C@2.0.0"],
            "C@2.0.0": None,
        })


if __name__ == "__main__":
    unittest.main()
