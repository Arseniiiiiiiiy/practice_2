
# Визуализатор зависимостей npm

Учебная программа на Python для анализа зависимостей npm-пакетов.
Этап 1 – YAML-конфигурация; этап 2 – прямые зависимости npm;
этап 3 – рекурсивный BFS; этап 4 – обратные зависимости.

## Структура

- `src/main.py` – CLI, чтение YAML, npm Registry, BFS и обратный обход;
- `config.yaml` – реальный npm-пакет;
- `config-test.yaml` – тестовый граф с циклом;
- `config-test-depth.yaml` – ограничение глубины обычного обхода;
- `config-test-diamond.yaml` – общая зависимость;
- `config-test-empty.yaml` – пакеты без зависимостей;
- `config-reverse-chain.yaml` – обратный обход цепочки;
- `config-reverse-diamond.yaml` – общие обратные зависимости;
- `config-reverse-depth.yaml` – ограничение глубины обратного обхода;
- `tests/repository*.json` – локальные тестовые репозитории;
- `tests/test_config.py` – тесты конфигурации;
- `tests/test_npm.py` – тесты npm;
- `tests/test_graph.py` – тесты обычного BFS;
- `tests/test_reverse.py` – тесты обратных зависимостей;
- `run.bat` – запуск Windows;
- `requirements.txt` – PyYAML для чтения конфигурации.

## Конфигурация

Пример `config.yaml`:

```yaml
package: "chalk"
repository: "https://registry.npmjs.org"
test_mode: false
version: "4.1.2"
output_file: "graph.svg"
ascii_tree: true
max_depth: 3
```

- `package` – пакет для анализа;
- `repository` – URL npm Registry или путь к локальному JSON;
- `test_mode` – использовать локальный граф вместо npm;
- `version` – точная версия корневого npm-пакета;
- `output_file` – имя SVG для этапа 5;
- `ascii_tree` – включение ASCII-дерева на этапе 5;
- `max_depth` – число уровней, допустимых при поиске.

В тестовом режиме имена пакетов записываются большими латинскими буквами.
Версия `version` в этом режиме не влияет на граф.

## Установка и запуск

Нужен Python 3.9+ и интернет для обращения к реальному npm Registry.

```powershell
py -m pip install -r requirements.txt
py src/main.py --config config.yaml
```

Запуск через `run.bat`:

```powershell
.\run.bat --config config.yaml
```

Прямые зависимости пакета (режим этапа 2):

```powershell
py src/main.py --config config.yaml --direct
```

## Прямой граф (этап 3)

По умолчанию программа строит граф зависимостей:

```powershell
py src/main.py --config config-test.yaml
```

Граф хранится в словаре `пакет -> список зависимостей`.
Функция `bfs_recursive()` обрабатывает целый уровень графа,
затем вызывает себя для следующего уровня.
Множество `visited` предотвращает повторный обход циклов.

`max_depth: 0` – не получать соседей; `max_depth: 1` – только
прямые зависимости; `max_depth: 2` – два уровня переходов.
Пометка `(предел глубины)` не означает отсутствия зависимостей.

При работе с npm программа использует точную версию корневого пакета
и упрощенный выбор стабильных версий транзитивных зависимостей.
Поддержаны `^`, `~`, `*`, сравнения, точные версии и `||`.
Это не полная реализация SemVer: `file:`, `git:`, алиасы,
частичные версии и некоторые prerelease-диапазоны не поддержаны.

## Обратные зависимости (этап 4)

Обратные зависимости – пакеты, которые используют выбранный пакет.
Для локального репозитория программа инвертирует все ребра, затем
применяет **тот же рекурсивный BFS** с ограничением `max_depth`.

Например, исходная связь `A -> B` означает «A зависит от B».
В обратном режиме будет `B <- A` – «от B зависит A».

Режим запускается флагом `--reverse`:

```powershell
py src/main.py --config config-reverse-chain.yaml --reverse
py src/main.py --config config-reverse-diamond.yaml --reverse
py src/main.py --config config-test.yaml --reverse
py src/main.py --config config-reverse-depth.yaml --reverse
py src/main.py --config config-test-empty.yaml --reverse
```

Тестовые сценарии: цепочка, общая зависимость, цикл,
ограничение глубины и пакет без обратных зависимостей.

**Ограничение:** `--reverse` поддерживается для локального тестового
репозитория. API npm Registry возвращает зависимости пакета,
но не предоставляет полный список всех пакетов, использующих его.
Поэтому невозможно получить глобально полные обратные зависимости
только через тот же API, не собрав сведения о других пакетах.
Для обычного npm-режима программа выводит понятную ошибку.

Флаги `--direct` и `--reverse` нельзя использовать одновременно.

## Тестирование

```powershell
py -m unittest discover -s tests -v
```

Тесты используют локальные файлы и имитацию HTTP-ответов,
поэтому доступны без интернета.

## Этап 5

Будут добавлены Graphviz DOT, экспорт SVG и ASCII-дерево.
