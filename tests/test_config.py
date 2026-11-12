"""Тесты параметров приложения."""

import tempfile
import unittest
from pathlib import Path

import yaml

from src.main import load_config


class ConfigTests(unittest.TestCase):

    def set_up(self):
        """Создать временную папку и корректные настройки."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.yaml"
        self.data = {
            "package": "chalk",
            "repository": "https://registry.npmjs.org",
            "test_mode": False,
            "version": "4.1.2",
            "output_file": "graph.svg",
            "ascii_tree": True,
            "max_depth": 3,
        }
        
    setUp = set_up

    def save(self, data):
        """Сохранить настройки во временный YAML-файл."""
        text = yaml.safe_dump(data, sort_keys=False)
        self.path.write_text(text, encoding="utf-8")

    def expect_error(self, key, value):
        """Проверить реакцию на неправильный параметр."""
        data = self.data.copy()
        data[key] = value
        self.save(data)
        with self.assertRaisesRegex(ValueError, key):
            load_config(self.path)

    def test_valid_config(self):
        """Принять корректные настройки."""
        self.save(self.data)
        self.assertEqual(load_config(self.path), self.data)

    def test_package_error(self):
        """Отклонить пустое имя пакета."""
        self.expect_error("package", "")

    def test_repository_error(self):
        """Отклонить неправильный URL."""
        self.expect_error("repository", "not-a-url")

    def test_test_mode_error(self):
        """Отклонить строку вместо логического значения."""
        self.expect_error("test_mode", "yes")

    def test_version_error(self):
        """Отклонить номер версии в неправильном формате."""
        self.expect_error("version", "latest")

    def test_output_file_error(self):
        """Отклонить неверное расширение файла."""
        self.expect_error("output_file", "graph.png")

    def test_ascii_tree_error(self):
        """Отклонить строку вместо логического значения."""
        self.expect_error("ascii_tree", "no")

    def test_max_depth_error(self):
        """Отклонить отрицательную глубину."""
        self.expect_error("max_depth", -1)

    def test_missing_parameter(self):
        """Отклонить конфигурацию с отсутствующим параметром."""
        data = self.data.copy()
        del data["package"]
        self.save(data)
        with self.assertRaisesRegex(ValueError, "package"):
            load_config(self.path)

    def test_invalid_yaml(self):
        """Отклонить поврежденный YAML."""
        self.path.write_text("package: [", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "config"):
            load_config(self.path)

    def test_missing_config(self):
        """Сообщить об отсутствии файла конфигурации."""
        with self.assertRaisesRegex(ValueError, "config"):
            load_config(self.path)

    def test_valid_test_mode(self):
        """Принять существующий тестовый репозиторий."""
        (self.path.parent / "repo.json").write_text("{}", encoding="utf-8")
        data = self.data.copy()
        data.update(package="A", test_mode=True, repository="repo.json")
        self.save(data)
        self.assertEqual(load_config(self.path), data)

    def test_missing_test_repository(self):
        """Отклонить отсутствующий тестовый репозиторий."""
        data = self.data.copy()
        data.update(package="A", test_mode=True, repository="missing.json")
        self.save(data)
        with self.assertRaisesRegex(ValueError, "repository"):
            load_config(self.path)


if __name__ == "__main__":
    unittest.main()
