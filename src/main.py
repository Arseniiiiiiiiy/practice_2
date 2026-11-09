"""CLI-приложение для анализа зависимостей npm-пакетов."""

import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

MIN_DEPTH = 0
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
    """Прочитать YAML и проверить все настройки."""
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


def main():
    """Запустить приложение и показать настройки."""
    parser = argparse.ArgumentParser(description="Граф зависимостей npm")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    try:
        settings = load_config(Path(args.config))
    except ValueError as error:
        parser.exit(1, f"Ошибка: {error}\n")
    print("Параметры конфигурации:")
    for key, value in settings.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
