
"""Создание DOT, SVG и ASCII-дерева для графа зависимостей."""

import json
import subprocess


def dot_name(name):
    """Безопасно заключить имя вершины в кавычки Graphviz."""
    return json.dumps(name, ensure_ascii=False)


def graph_to_dot(root, graph, reverse=False):
    """Построить текст ориентированного графа на языке DOT."""
    lines = [
        "digraph dependencies {",
        "  rankdir=LR;",
        '  graph [bgcolor="white"];',
        '  node [shape=box, style="rounded", fontname="Arial"];',
        '  edge [color="#64748B"];',
    ]
    for node in sorted(graph):
        name = dot_name(node)
        if node == root:
            lines.append(
                f'  {name} [style="rounded,filled", '
                'fillcolor="#DCE8F7"];'
            )
        elif graph[node] is None:
            lines.append(f'  {name} [style="rounded,dashed"];')
        else:
            lines.append(f"  {name};")
        for child in graph[node] or []:
            source, target = (child, node) if reverse else (node, child)
            lines.append(f"  {dot_name(source)} -> {dot_name(target)};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def tree_branches(node, graph, prefix, ancestors, visited):
    """Рекурсивно вывести ветви дерева и отметить повторения."""
    lines = []
    children = graph[node] or []
    for index, child in enumerate(children):
        last = index == len(children) - 1
        marker = "`-- " if last else "|-- "
        next_prefix = prefix + ("    " if last else "|   ")
        if child in ancestors:
            note = " (цикл)"
        elif child in visited:
            note = " (повтор)"
        elif graph[child] is None:
            note = " (предел глубины)"
        else:
            note = ""
        lines.append(f"{prefix}{marker}{child}{note}")
        if child not in visited:
            visited.add(child)
            lines.extend(tree_branches(
                child, graph, next_prefix, ancestors | {child}, visited
            ))
    return lines


def format_ascii_tree(root, graph):
    """Представить граф ASCII-деревом без бесконечных циклов."""
    label = root
    if graph[root] is None:
        label += " (предел глубины)"
    lines = [label]
    lines.extend(tree_branches(root, graph, "", {root}, {root}))
    return "\n".join(lines)


def export_visualization(root, graph, config_path, output_file,
                         reverse=False):
    """Сохранить DOT и преобразовать его в SVG программой Graphviz."""
    svg_path = config_path.parent / output_file
    dot_path = svg_path.with_suffix(".dot")
    try:
        dot_path.write_text(graph_to_dot(root, graph, reverse),
                            encoding="utf-8")
        subprocess.run(
            ["dot", "-Tsvg", str(dot_path), "-o", str(svg_path)],
            check=True, capture_output=True, text=True, encoding="utf-8"
        )
    except FileNotFoundError as error:
        raise ValueError("Graphviz: команда dot не найдена") from error
    except subprocess.CalledProcessError as error:
        raise ValueError(f"Graphviz: ошибка SVG: {error.stderr}") from error
    except OSError as error:
        raise ValueError(f"Graphviz: ошибка записи: {error}") from error
    return dot_path, svg_path


def show_visualization(root, graph, settings, config_path, reverse):
    """Создать файлы и при необходимости вывести ASCII-дерево."""
    dot_path, svg_path = export_visualization(
        root, graph, config_path, settings["output_file"], reverse
    )
    print(f"Graphviz DOT: {dot_path}")
    print(f"SVG: {svg_path}")
    if settings["ascii_tree"]:
        print("ASCII-дерево обратных зависимостей:" if reverse
              else "ASCII-дерево зависимостей:")
        print(format_ascii_tree(root, graph))
