
"""Проверки обратных зависимостей через рекурсивный BFS."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src.main import (
    build_reverse_graph,
    load_config,
    main,
    print_reverse_graph,
    reverse_repository,
)

ROOT = Path(__file__).resolve().parent.parent


class ReverseTests(unittest.TestCase):
    """Проверить инверсию связей, обход и работу командной строки."""

    def graph(self, config):
        """Прочитать конфигурацию и получить обратный граф."""
        path = ROOT / config
        return build_reverse_graph(load_config(path), path)

    def cli(self, config):
        """Запустить --reverse с указанной конфигурацией."""
        output = io.StringIO()
        path = ROOT / config
        with patch("sys.argv", ["main.py", "--config", str(path),
                                "--reverse"]):
            with redirect_stdout(output):
                main()
        return output.getvalue()

    def test_invert_edges(self):
        """Инвертировать связи в обе стороны для всех пакетов."""
        repository = {"A": ["B"], "B": ["C"], "C": []}
        self.assertEqual(reverse_repository(repository), {
            "A": [], "B": ["A"], "C": ["B"],
        })

    def test_chain(self):
        """Найти пакеты, косвенно зависящие от D в цепочке."""
        root, graph = self.graph("config-reverse-chain.yaml")
        self.assertEqual(root, "D")
        self.assertEqual(graph, {
            "D": ["C"], "C": ["B"], "B": ["A"], "A": [],
        })

    def test_diamond(self):
        """Два прямых зависимых пакета могут иметь общего родителя."""
        root, graph = self.graph("config-reverse-diamond.yaml")
        self.assertEqual(root, "D")
        self.assertEqual(graph, {
            "D": ["B", "C"], "B": ["A"], "C": ["A"], "A": [],
        })

    def test_cycle(self):
        """Не обходить циклическую зависимость повторно."""
        root, graph = self.graph("config-test.yaml")
        self.assertEqual(root, "A")
        self.assertEqual(graph, {
            "A": ["D"], "D": ["B", "C"],
            "B": ["A"], "C": ["A"],
        })

    def test_isolated(self):
        """У изолированного пакета нет обратных зависимостей."""
        root, graph = self.graph("config-test-empty.yaml")
        self.assertEqual((root, graph), ("A", {"A": []}))

    def test_depth_one(self):
        """Остановиться после первого уровня обратных связей."""
        _, graph = self.graph("config-reverse-depth.yaml")
        self.assertEqual(graph, {"D": ["C"], "C": None})

    def test_depth_zero(self):
        """При нулевой глубине не искать зависимые пакеты."""
        path = ROOT / "config-reverse-chain.yaml"
        settings = load_config(path)
        settings["max_depth"] = 0
        _, graph = build_reverse_graph(settings, path)
        self.assertEqual(graph, {"D": None})

    def test_missing_package(self):
        """Проверить ошибку при отсутствии корневого пакета."""
        path = ROOT / "config-reverse-chain.yaml"
        settings = load_config(path)
        settings["package"] = "Z"
        with self.assertRaisesRegex(ValueError, "не найден"):
            build_reverse_graph(settings, path)

    def test_real_npm_not_supported(self):
        """Не выдавать неполный npm-граф за все обратные зависимости."""
        path = ROOT / "config.yaml"
        settings = load_config(path)
        with self.assertRaisesRegex(ValueError, "тестового"):
            build_reverse_graph(settings, path)

    def test_cli_chain(self):
        """Показать обратные связи в правильном направлении."""
        output = self.cli("config-reverse-chain.yaml")
        self.assertIn("Обратные зависимости D:", output)
        self.assertIn("D <- C", output)
        self.assertIn("C <- B", output)
        self.assertIn("B <- A", output)
        self.assertIn("A <- (нет зависимых пакетов)", output)

    def test_cli_diamond(self):
        """Отобразить два прямых обратных соседа D."""
        output = self.cli("config-reverse-diamond.yaml")
        self.assertIn("D <- B, C", output)
        self.assertIn("B <- A", output)
        self.assertIn("C <- A", output)

    def test_cli_cycle(self):
        """Показать цикл без бесконечного вывода."""
        output = self.cli("config-test.yaml")
        self.assertIn("A <- D", output)
        self.assertIn("D <- B, C", output)

    def test_cli_empty(self):
        """Показать отсутствие обратных зависимостей."""
        output = self.cli("config-test-empty.yaml")
        self.assertIn("A <- (нет зависимых пакетов)", output)

    def test_cli_depth(self):
        """Отметить предел глубины при обратном обходе."""
        output = self.cli("config-reverse-depth.yaml")
        self.assertIn("C <- (предел глубины)", output)

    def test_mutually_exclusive_modes(self):
        """Запретить совместное использование --direct и --reverse."""
        path = ROOT / "config-test.yaml"
        argv = ["main.py", "--config", str(path),
                "--direct", "--reverse"]
        with patch("sys.argv", argv), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exit_error:
                main()
        self.assertEqual(exit_error.exception.code, 2)

    def test_print_reverse_graph(self):
        """Отображать пустой и отсеченный уровень отдельно."""
        output = io.StringIO()
        with redirect_stdout(output):
            print_reverse_graph("A", {"A": ["B"],
                                      "B": None, "C": []})
        self.assertIn("B <- (предел глубины)", output.getvalue())
        self.assertIn("C <- (нет зависимых пакетов)", output.getvalue())


if __name__ == "__main__":
    unittest.main()
