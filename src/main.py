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
STABLE_VERSION_RE = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"


def text_value(data, key):
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


def package_url(repository, package, version):
    """Сформировать URL конкретной версии npm-пакета."""
    name = quote(package, safe="@")
    release = quote(version, safe="")
    return f"{repository.rstrip('/')}/{name}/{release}"


def request_json(url, accept="application/json"):
    """Получить JSON через стандартную библиотеку Python."""
    request = Request(url, headers={"Accept": accept})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            result = json.load(response)
    except HTTPError as error:
        if error.code == HTTP_NOT_FOUND:
            raise ValueError("npm: пакет или версия не найдены") from error
        raise ValueError(f"npm: ошибка HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError("npm: не удалось подключиться") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("npm: некорректный ответ JSON") from error
    if not isinstance(result, dict):
        raise ValueError("npm: ожидался объект JSON")
    return result


def fetch_direct_dependencies(repository, package, version):
    """Получить прямые зависимости конкретной версии npm-пакета."""
    url = package_url(repository, package, version)
    metadata = request_json(url)
    if metadata.get("name") != package or metadata.get("version") != version:
        raise ValueError("npm: неверный пакет или версия в ответе")
    dependencies = metadata.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise ValueError("npm: неверный формат dependencies")
    for name, release in dependencies.items():
        if not isinstance(name, str) or not isinstance(release, str):
            raise ValueError("npm: неверные данные зависимости")
    return dependencies


def version_numbers(version):
    """Превратить стабильную версию в три числа для сравнения."""
    if not re.fullmatch(STABLE_VERSION_RE, version):
        return None
    return tuple(int(number) for number in version.split("."))


def range_upper_bound(base, sign):
    """Найти верхнюю границу для ^ и ~ в упрощенном SemVer."""
    major, minor, patch = base
    if sign == "~":
        return major, minor + 1, 0
    if major:
        return major + 1, 0, 0
    if minor:
        return 0, minor + 1, 0
    return 0, 0, patch + 1


def check_comparison(version, condition, sign):
    """Проверить один оператор сравнения версий."""
    base = version_numbers(condition[len(sign):])
    if base is None:
        raise ValueError(f"npm: диапазон не поддерживается: {condition}")
    if sign == ">=":
        return version >= base
    if sign == "<=":
        return version <= base
    if sign == ">":
        return version > base
    if sign == "<":
        return version < base
    return version == base


def check_condition(version, condition):
    """Проверить одну часть диапазона npm-версий."""
    if condition == "*":
        return True
    if condition.startswith(("^", "~")):
        base = version_numbers(condition[1:])
        if base is None:
            raise ValueError(f"npm: диапазон не поддерживается: {condition}")
        return base <= version < range_upper_bound(base, condition[0])
    for sign in (">=", "<=", ">", "<", "="):
        if condition.startswith(sign):
            return check_comparison(version, condition, sign)
    base = version_numbers(condition)
    if base is None:
        raise ValueError(f"npm: диапазон не поддерживается: {condition}")
    return version == base


def version_matches(version, requirement):
    """Проверить диапазон: ^, ~, сравнения, *, или ||."""
    for alternative in requirement.split("||"):
        parts = alternative.split()
        if parts and all(check_condition(version, part) for part in parts):
            return True
    return False


def fetch_packument(repository, package):
    """Получить список версий npm-пакета для выбора подходящей."""
    url = f"{repository.rstrip('/')}/{quote(package, safe='@')}"
    metadata = request_json(url, "application/vnd.npm.install-v1+json")
    if metadata.get("name") != package:
        raise ValueError("npm: неверное имя пакета в списке версий")
    if not isinstance(metadata.get("versions"), dict):
        raise ValueError("npm: нет списка версий пакета")
    return metadata


def resolve_version(repository, package, requirement, cache):
    """Выбрать наибольшую стабильную версию под заданный диапазон."""
    if package not in cache:
        cache[package] = fetch_packument(repository, package)
    metadata = cache[package]
    tags = metadata.get("dist-tags", {})
    if isinstance(tags, dict) and requirement in tags:
        return tags[requirement]
    available = metadata["versions"]
    stable = [(version_numbers(v), v) for v in available]
    stable = sorted((item for item in stable if item[0]), reverse=True)
    for numbers, version in stable:
        if version_matches(numbers, requirement):
            return version
    raise ValueError(f"npm: нет подходящей версии {package}@{requirement}")


def validate_test_repository(data):
    """Проверить имена и связи локального тестового графа."""
    if not isinstance(data, dict):
        raise ValueError("repository: ожидается объект JSON")
    for package, children in data.items():
        if not isinstance(package, str) or not re.fullmatch(r"[A-Z]+", package):
            raise ValueError("repository: неправильное имя пакета")
        if not isinstance(children, list):
            raise ValueError("repository: зависимости должны быть списком")
        for child in children:
            if not isinstance(child, str) or child not in data:
                raise ValueError("repository: отсутствует описание зависимости")


def load_test_repository(path):
    """Прочитать и проверить тестовый граф из JSON-файла."""
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("repository: неправильный JSON") from error
    validate_test_repository(data)
    return data


def bfs_recursive(level, depth, limit, graph, visited, get_children):
    """Рекурсивно обойти один уровень BFS и перейти к следующему."""
    if not level or depth >= limit:
        return
    next_level = []
    for package in level:
        children = sorted(set(get_children(package)))
        graph[package] = children
        for child in children:
            if child not in visited:
                visited.add(child)
                graph[child] = None
                next_level.append(child)
    bfs_recursive(next_level, depth + 1, limit,
                  graph, visited, get_children)


def build_graph(package, max_depth, get_children):
    """Собрать граф зависимостей в ширину с ограничением глубины."""
    graph = {package: None}
    bfs_recursive([package], 0, max_depth, graph, {package}, get_children)
    return graph


def build_npm_graph(settings):
    """Собрать версии и зависимости пакетов из npm Registry."""
    repository = settings["repository"]
    cache = {}

    def get_children(node):
        """Найти зависимости одной точной версии npm-пакета."""
        name, _, version = node.rpartition("@")
        direct = fetch_direct_dependencies(repository, name, version)
        result = []
        for package, requirement in sorted(direct.items()):
            selected = resolve_version(repository, package, requirement,
                                       cache)
            result.append(f"{package}@{selected}")
        return result

    root = f"{settings['package']}@{settings['version']}"
    return root, build_graph(root, settings["max_depth"], get_children)


def build_test_graph(settings, config_path):
    """Собрать граф из локального тестового репозитория."""
    path = config_path.parent / settings["repository"]
    repository = load_test_repository(path)
    root = settings["package"]
    if root not in repository:
        raise ValueError(f"repository: пакет {root} не найден")
    def get_children(name):
        """Получить соседей указанного тестового пакета."""
        return repository[name]
    return root, build_graph(root, settings["max_depth"], get_children)


def print_graph(root, graph):
    """Показать найденные связи и узлы на границе глубины."""
    print(f"Граф зависимостей {root}:")
    for package, children in graph.items():
        if children is None:
            print(f"{package} -> (предел глубины)")
        elif children:
            print(f"{package} -> {', '.join(children)}")
        else:
            print(f"{package} -> (нет зависимостей)")


def print_direct(settings):
    """Показать результат этапа 2 по запросу --direct."""
    if settings["test_mode"]:
        raise ValueError("--direct доступен только для npm")
    name = settings["package"]
    version = settings["version"]
    direct = fetch_direct_dependencies(settings["repository"],
                                       name, version)
    print(f"Прямые зависимости {name}@{version}:")
    if not direct:
        print("(нет зависимостей)")
    for package, release in sorted(direct.items()):
        print(f"{package}: {release}")


def main():
    """Проверить настройки и вывести прямые зависимости или граф."""
    parser = argparse.ArgumentParser(description="Граф зависимостей npm")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--direct", action="store_true")
    args = parser.parse_args()
    try:
        path = Path(args.config)
        settings = load_config(path)
        if args.direct:
            print_direct(settings)
            return
        if settings["test_mode"]:
            root, graph = build_test_graph(settings, path)
        else:
            root, graph = build_npm_graph(settings)
        print_graph(root, graph)
    except ValueError as error:
        parser.exit(1, f"Ошибка: {error}\n")


if __name__ == "__main__":
    main()
