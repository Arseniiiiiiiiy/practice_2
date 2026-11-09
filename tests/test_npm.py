import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from src.main import (
    HTTP_NOT_FOUND,
    REQUEST_TIMEOUT,
    fetch_direct_dependencies,
    main,
    package_url,
)

REGISTRY = "https://registry.npmjs.org"
PACKAGE = "chalk"
VERSION = "4.1.2"
DIRECT = {"ansi-styles": "^4.1.0", "supports-color": "^7.1.0"}


class RegistryTests(unittest.TestCase):
    """Проверить чтение npm-метаданных и ошибки запроса."""

    def metadata(self, dependencies=None):
        """Создать ответ для заданной версии пакета."""
        return {
            "name": PACKAGE,
            "version": VERSION,
            "dependencies": DIRECT if dependencies is None else dependencies,
        }

    def get(self, data):
        """Подменить HTTP и получить зависимости."""
        response = io.BytesIO(json.dumps(data).encode("utf-8"))
        with patch("src.main.urlopen", return_value=response) as mock:
            result = fetch_direct_dependencies(REGISTRY, PACKAGE, VERSION)
        return result, mock

    def test_direct_dependencies(self):
        """Вернуть только прямые зависимости нужной версии."""
        data = self.metadata()
        data["devDependencies"] = {"mocha": "^10.0.0"}
        result, mock = self.get(data)
        self.assertEqual(result, DIRECT)
        request = mock.call_args.args[0]
        self.assertEqual(request.full_url, f"{REGISTRY}/chalk/4.1.2")
        self.assertEqual(mock.call_args.kwargs["timeout"], REQUEST_TIMEOUT)

    def test_scoped_package_url(self):
        """Экранировать слеш в имени scoped-пакета."""
        url = package_url(REGISTRY, "@scope/name", "1.2.3")
        self.assertEqual(url, f"{REGISTRY}/@scope%2Fname/1.2.3")

    def test_empty_dependencies(self):
        """Поддержать пакет без зависимостей."""
        result, _ = self.get(self.metadata({}))
        self.assertEqual(result, {})

    def test_missing_dependencies(self):
        """Отсутствие поля dependencies означает пустой список."""
        data = self.metadata()
        del data["dependencies"]
        result, _ = self.get(data)
        self.assertEqual(result, {})

    def test_not_found(self):
        """Обработать отсутствие версии или пакета."""
        error = HTTPError(REGISTRY, HTTP_NOT_FOUND, "Not Found", {}, None)
        with patch("src.main.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "не найдены"):
                fetch_direct_dependencies(REGISTRY, PACKAGE, VERSION)

    def test_server_error(self):
        """Показать код ошибки сервера."""
        error = HTTPError(REGISTRY, 503, "Unavailable", {}, None)
        with patch("src.main.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "HTTP 503"):
                fetch_direct_dependencies(REGISTRY, PACKAGE, VERSION)

    def test_connection_error(self):
        """Обработать отсутствие подключения."""
        with patch("src.main.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(ValueError, "подключиться"):
                fetch_direct_dependencies(REGISTRY, PACKAGE, VERSION)

    def test_bad_json(self):
        """Отклонить поврежденный JSON от сервера."""
        with patch("src.main.urlopen", return_value=io.BytesIO(b"{")):
            with self.assertRaisesRegex(ValueError, "JSON"):
                fetch_direct_dependencies(REGISTRY, PACKAGE, VERSION)

    def test_json_not_object(self):
        """Отклонить массив вместо объекта метаданных."""
        with self.assertRaisesRegex(ValueError, "объект JSON"):
            self.get([])

    def test_wrong_package(self):
        """Не принимать метаданные другого пакета."""
        data = self.metadata()
        data["name"] = "other"
        with self.assertRaisesRegex(ValueError, "неверный пакет"):
            self.get(data)

    def test_wrong_version(self):
        """Не принимать метаданные другой версии."""
        data = self.metadata()
        data["version"] = "1.0.0"
        with self.assertRaisesRegex(ValueError, "неверный пакет"):
            self.get(data)

    def test_bad_dependencies(self):
        """Отклонить неправильный тип поля dependencies."""
        with self.assertRaisesRegex(ValueError, "формат dependencies"):
            self.get(self.metadata(["wrong"]))

    def test_bad_dependency_values(self):
        """Отклонить зависимость без строки версии."""
        with self.assertRaisesRegex(ValueError, "данные зависимости"):
            self.get(self.metadata({"lib": None}))

    def test_cli_output(self):
        """Показать прямые зависимости без лишних данных."""
        output = io.StringIO()
        config = Path(__file__).resolve().parent.parent / "config.yaml"
        with patch("sys.argv", ["main.py", "--config", str(config)]):
            with patch("src.main.fetch_direct_dependencies",
                       return_value=DIRECT):
                with redirect_stdout(output):
                    main()
        self.assertEqual(output.getvalue().splitlines(), [
            "Прямые зависимости chalk@4.1.2:",
            "ansi-styles: ^4.1.0",
            "supports-color: ^7.1.0",
        ])

    def test_cli_no_dependencies(self):
        """Сообщить об отсутствии прямых зависимостей."""
        output = io.StringIO()
        config = Path(__file__).resolve().parent.parent / "config.yaml"
        with patch("sys.argv", ["main.py", "--config", str(config)]):
            with patch("src.main.fetch_direct_dependencies",
                       return_value={}):
                with redirect_stdout(output):
                    main()
        self.assertIn("(нет зависимостей)", output.getvalue())


if __name__ == "__main__":
    unittest.main()
