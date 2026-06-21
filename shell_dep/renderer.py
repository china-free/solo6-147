import os
from pathlib import Path
from typing import Set, List, Optional, Tuple

from colorama import Fore, Style, init as colorama_init

from .graph import DependencyGraph, DependencyEdge, is_part_of_cycle


colorama_init()

TREE_VERTICAL = '│   '
TREE_BRANCH = '├── '
TREE_LAST_BRANCH = '└── '
TREE_EMPTY = '    '

STATUS_MISSING = f'{Fore.RED}✗ MISSING{Style.RESET_ALL}'
STATUS_CYCLE = f'{Fore.RED}↻ CYCLE{Style.RESET_ALL}'
STATUS_DYNAMIC = f'{Fore.YELLOW}? DYNAMIC{Style.RESET_ALL}'


def _rel_or_name(full_path: Path, base_dir: Path) -> str:
    try:
        return str(full_path.relative_to(base_dir))
    except ValueError:
        return full_path.name


def _format_script_name(
    script_path: Path,
    graph: DependencyGraph,
    base_dir: Path,
) -> str:
    name = _rel_or_name(script_path, base_dir)
    if is_part_of_cycle(graph, script_path):
        return f'{Fore.RED}{Style.BRIGHT}{name}{Style.RESET_ALL} {STATUS_CYCLE}'
    return f'{Fore.CYAN}{name}{Style.RESET_ALL}'


def _format_edge_source_info(
    edge: DependencyEdge,
    graph: DependencyGraph,
    base_dir: Path,
    already_visited: bool = False,
) -> str:
    line = edge.source_stmt.line_number

    if edge.is_dynamic:
        return (
            f'{Fore.YELLOW}{edge.source_stmt.raw_path}{Style.RESET_ALL} '
            f'{STATUS_DYNAMIC} {Fore.LIGHTBLACK_EX}(line {line}){Style.RESET_ALL}'
        )

    if edge.is_missing:
        return (
            f'{Fore.RED}{Style.BRIGHT}{edge.source_stmt.raw_path}{Style.RESET_ALL} '
            f'{STATUS_MISSING} {Fore.LIGHTBLACK_EX}(line {line}){Style.RESET_ALL}'
        )

    if edge.to_script is not None:
        if already_visited:
            return (
                f'{_format_script_name(edge.to_script, graph, base_dir)} '
                f'{Fore.LIGHTBLACK_EX}(line {line}, already shown){Style.RESET_ALL}'
            )
        return (
            f'{_format_script_name(edge.to_script, graph, base_dir)} '
            f'{Fore.LIGHTBLACK_EX}(line {line}){Style.RESET_ALL}'
        )

    return f'{edge.source_stmt.raw_path} (line {line})'


def _path_key(path: Path) -> str:
    return str(path.resolve())


def _render_tree_iterative(
    graph: DependencyGraph,
    base_dir: Path,
    roots: List[Path],
) -> List[str]:
    lines: List[str] = []

    for root_idx, root in enumerate(roots):
        is_last_root = (root_idx == len(roots) - 1)

        lines.append(_format_script_name(root, graph, base_dir))

        if root not in graph.edges or not graph.edges[root]:
            if not is_last_root:
                lines.append('')
            continue

        root_key = _path_key(root)
        visited_global: Set[str] = {root_key}

        root_edges = graph.edges[root]

        stack: List[Tuple[Path, str, Set[str], List[DependencyEdge], int, bool]] = []

        for i in range(len(root_edges) - 1, -1, -1):
            is_last_edge = (i == len(root_edges) - 1)
            stack.append((
                root, '', {root_key}, root_edges, i, is_last_edge
            ))

        while stack:
            parent, prefix, visited_path, edges, edge_idx, is_last_edge = stack.pop()

            if edge_idx >= len(edges):
                continue

            edge = edges[edge_idx]

            connector = TREE_LAST_BRANCH if is_last_edge else TREE_BRANCH
            line_prefix = prefix + connector

            if edge.is_dynamic or edge.is_missing:
                edge_label = _format_edge_source_info(edge, graph, base_dir)
                lines.append(f'{line_prefix}{edge_label}')
            else:
                target = edge.to_script
                if target is None:
                    continue

                target_key = _path_key(target)
                in_path = target_key in visited_path
                in_global = target_key in visited_global
                already_visited = in_path or in_global

                edge_label = _format_edge_source_info(
                    edge, graph, base_dir, already_visited=already_visited
                )
                lines.append(f'{line_prefix}{edge_label}')

                if not already_visited:
                    visited_global.add(target_key)
                    new_visited_path = visited_path | {target_key}

                    if target in graph.edges and graph.edges[target]:
                        child_edges = graph.edges[target]
                        child_prefix = prefix + (TREE_EMPTY if is_last_edge else TREE_VERTICAL)

                        for i in range(len(child_edges) - 1, -1, -1):
                            ce_last = (i == len(child_edges) - 1)
                            stack.append((
                                target, child_prefix, new_visited_path,
                                child_edges, i, ce_last
                            ))

        if not is_last_root:
            lines.append('')

    return lines


def render_tree(graph: DependencyGraph, base_dir: Optional[Path] = None) -> str:
    if base_dir is None:
        all_paths = list(graph.scripts.keys())
        if all_paths:
            base_dir = Path(os.path.commonpath([str(p) for p in all_paths])).resolve()
        else:
            base_dir = Path.cwd()
    base_dir = base_dir.resolve()

    lines: List[str] = []
    roots = sorted(graph.roots) if graph.roots else sorted(graph.scripts.keys())

    if not roots:
        return f'{Fore.YELLOW}No shell scripts found in the target directory.{Style.RESET_ALL}'

    lines.append(f'{Fore.WHITE}{Style.BRIGHT}Shell Script Dependency Tree{Style.RESET_ALL}')
    lines.append(f'{Fore.LIGHTBLACK_EX}Base directory: {base_dir}{Style.RESET_ALL}')
    lines.append('')

    tree_lines = _render_tree_iterative(graph, base_dir, roots)
    lines.extend(tree_lines)

    return '\n'.join(lines)


def render_summary(graph: DependencyGraph) -> str:
    lines: List[str] = []
    total = len(graph.scripts)
    missing = len(graph.missing_files)
    cycles = len(graph.cycles)
    dynamic = len(graph.dynamic_sources)

    lines.append('')
    lines.append(f'{Fore.WHITE}{Style.BRIGHT}Summary{Style.RESET_ALL}')
    lines.append(f'  {Fore.CYAN}Total scripts:       {total}{Style.RESET_ALL}')
    if missing:
        lines.append(f'  {Fore.RED}Missing files:       {missing}{Style.RESET_ALL}')
    else:
        lines.append(f'  {Fore.GREEN}Missing files:       0{Style.RESET_ALL}')
    if cycles:
        lines.append(f'  {Fore.RED}Dependency cycles:   {cycles}{Style.RESET_ALL}')
    else:
        lines.append(f'  {Fore.GREEN}Dependency cycles:   0{Style.RESET_ALL}')
    if dynamic:
        lines.append(f'  {Fore.YELLOW}Dynamic sources:     {dynamic}{Style.RESET_ALL}')

    if missing:
        lines.append('')
        lines.append(f'{Fore.RED}{Style.BRIGHT}Missing source files:{Style.RESET_ALL}')
        for edge in graph.missing_files:
            lines.append(
                f'  {Fore.RED}✗{Style.RESET_ALL} '
                f'{Fore.LIGHTBLACK_EX}{edge.from_script.name}:{edge.source_stmt.line_number}{Style.RESET_ALL} '
                f'→ {Fore.RED}{edge.source_stmt.raw_path}{Style.RESET_ALL}'
            )

    if cycles:
        lines.append('')
        lines.append(f'{Fore.RED}{Style.BRIGHT}Circular dependencies detected:{Style.RESET_ALL}')
        for cycle in graph.cycles:
            cycle_str = f' {Fore.RED}↻{Style.RESET_ALL} '.join(
                f'{Fore.RED}{p.name}{Style.RESET_ALL}' for p in cycle
            )
            lines.append(f'  {cycle_str}')

    return '\n'.join(lines)
