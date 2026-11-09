import argparse
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import yaml

MIN_DEPTH = 0
HTTP_NOT_FOUND = 404
REQUEST_TIMEOUT = 10
VERSION_RE = (
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)


def text_value(data, key):
    """Получить обязательный текстовый параметр."""
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}: нужна непустая строка")
    return value.strip()


def bool_value(data, key):
    """Получить логический параметр."""
    value = data.get(key)
    if type(value) is not bool:
        raise ValueError(f"{key}: нужно true или false")
    return value


def depth_value(data):
    """Проверить максимальную глубину анализа."""
    value = data.get("max_depth")
    if type(value) is not int or value < MIN_DEPTH:
        raise ValueError("max_depth: нужно целое число от 0")
    return value


def check_package(package, test_mode):
    """Проверить имя реального или тестового пакета."""
    pattern = r"[A-Z]+" if test_mode else r"(?:@[a-z0-9._-]+/)?[a-z0-9._-]+"
    if not re.fullmatch(pattern, package):
        raise ValueError("package: неправильное имя пакета")


def check_repository(repository, test_mode, base):
    """Проверить URL npm или путь к тестовому файлу."""
    if test_mode:
        if not (base / repository).is_file():
            raise ValueError("repository: тестовый файл не найден")
        return
    try:
        address = urlsplit(repository)
        valid = address.scheme in ("http", "https")
        valid = valid and bool(address.hostname)
        _ = address.port
    except ValueError:
        valid = False
    if not valid or any(char.isspace() for char in repository):
        raise ValueError("repository: нужен корректный URL")


def check_version(version):
    """Проверить формат конкретной версии пакета."""
    if not re.fullmatch(VERSION_RE, version):
        raise ValueError("version: нужен номер вида 1.2.3")


def check_output_file(file_name):
    """Проверить имя выходного SVG-файла."""
    if not file_name.endswith(".svg") or "/" in file_name:
        raise ValueError("output_file: нужно имя файла .svg")
    if "\\" in file_name or file_name == ".svg":
        raise ValueError("output_file: нужен файл без пути")


def load_config(path):
    if not path.is_file():
        raise ValueError("config: файл не найден")
    try:
        with path.open(encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except (OSError, yaml.YAMLError) as error:
        raise ValueError("config: ошибка чтения YAML") from error
    if not isinstance(data, dict):
        raise ValueError("config: ожидается набор ключей и значений")

    settings = {
        "package": text_value(data, "package"),
        "repository": text_value(data, "repository"),
        "test_mode": bool_value(data, "test_mode"),
        "version": text_value(data, "version"),
        "output_file": text_value(data, "output_file"),
        "ascii_tree": bool_value(data, "ascii_tree"),
        "max_depth": depth_value(data),
    }
    check_package(settings["package"], settings["test_mode"])
    check_repository(settings["repository"], settings["test_mode"],
                     path.parent)
    check_version(settings["version"])
    check_output_file(settings["output_file"])
    return settings


def package_url(repository, package, version):
    name = quote(package, safe="@")
    release = quote(version, safe="")
    return f"{repository.rstrip('/')}/{name}/{release}"


def fetch_direct_dependencies(repository, package, version):
    url = package_url(repository, package, version)
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            metadata = json.load(response)
    except HTTPError as error:
        if error.code == HTTP_NOT_FOUND:
            raise ValueError("npm: пакет или версия не найдены") from error
        raise ValueError(f"npm: ошибка HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError("npm: не удалось подключиться") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("npm: некорректный ответ JSON") from error

    if not isinstance(metadata, dict):
        raise ValueError("npm: ожидался объект JSON")
    if metadata.get("name") != package or metadata.get("version") != version:
        raise ValueError("npm: неверный пакет или версия в ответе")
    dependencies = metadata.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise ValueError("npm: неверный формат dependencies")
    for name, release in dependencies.items():
        if not isinstance(name, str) or not isinstance(release, str):
            raise ValueError("npm: неверные данные зависимости")
    return dependencies


def main():
    parser = argparse.ArgumentParser(description="Граф зависимостей npm")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    try:
        settings = load_config(Path(args.config))
        if settings["test_mode"]:
            raise ValueError("тестовый режим будет добавлен на этапе 3")
        dependencies = fetch_direct_dependencies(
            settings["repository"], settings["package"],
            settings["version"],
        )
    except ValueError as error:
        parser.exit(1, f"Ошибка: {error}\n")

    name = settings["package"]
    version = settings["version"]
    print(f"Прямые зависимости {name}@{version}:")
    if not dependencies:
        print("(нет зависимостей)")
    for package, release in sorted(dependencies.items()):
        print(f"{package}: {release}")


if __name__ == "__main__":
    main()
