from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

from .parser import ShellScript, SourceStatement


@dataclass
class DependencyEdge:
    from_script: Path
    to_script: Optional[Path]
    source_stmt: SourceStatement

    @property
    def is_missing(self) -> bool:
        return self.source_stmt.resolved_path is None and not self.source_stmt.is_dynamic

    @property
    def is_dynamic(self) -> bool:
        return self.source_stmt.is_dynamic


@dataclass
class DependencyGraph:
    scripts: Dict[Path, ShellScript] = field(default_factory=dict)
    edges: Dict[Path, List[DependencyEdge]] = field(default_factory=dict)
    missing_files: List[DependencyEdge] = field(default_factory=list)
    dynamic_sources: List[DependencyEdge] = field(default_factory=list)
    cycles: List[List[Path]] = field(default_factory=list)
    roots: Set[Path] = field(default_factory=set)

    def has_issues(self) -> bool:
        return bool(self.missing_files) or bool(self.cycles)


def build_dependency_graph(scripts: Dict[Path, ShellScript]) -> DependencyGraph:
    graph = DependencyGraph(scripts=scripts)

    script_paths: Set[Path] = set(scripts.keys())
    all_dependencies: Set[Path] = set()

    for script_path, script in scripts.items():
        graph.edges[script_path] = []
        for source_stmt in script.sources:
            edge = DependencyEdge(
                from_script=script_path,
                to_script=source_stmt.resolved_path,
                source_stmt=source_stmt,
            )
            graph.edges[script_path].append(edge)

            if edge.is_missing:
                graph.missing_files.append(edge)
            elif edge.is_dynamic:
                graph.dynamic_sources.append(edge)
            elif source_stmt.resolved_path is not None:
                all_dependencies.add(source_stmt.resolved_path)

    graph.roots = script_paths - all_dependencies

    graph.cycles = detect_cycles(graph)

    cycle_nodes: Set[Path] = set()
    for cycle in graph.cycles:
        cycle_nodes.update(cycle)
    reachable_from_roots: Set[Path] = set()
    stack = list(graph.roots)
    while stack:
        node = stack.pop()
        if node in reachable_from_roots:
            continue
        reachable_from_roots.add(node)
        if node in graph.edges:
            for edge in graph.edges[node]:
                if edge.to_script and edge.to_script not in reachable_from_roots:
                    stack.append(edge.to_script)
    unreachable = script_paths - reachable_from_roots
    if unreachable:
        cycle_representatives: Set[Path] = set()
        for node in sorted(unreachable):
            covered = False
            for rep in cycle_representatives:
                if rep in reachable_from_roots:
                    covered = True
                    break
            if not covered:
                cycle_representatives.add(node)
                reachable_from_roots.add(node)
                local_stack = [node]
                while local_stack:
                    n = local_stack.pop()
                    if n in graph.edges:
                        for e in graph.edges[n]:
                            if e.to_script and e.to_script not in reachable_from_roots:
                                reachable_from_roots.add(e.to_script)
                                local_stack.append(e.to_script)
        graph.roots |= cycle_representatives

    return graph


def detect_cycles(graph: DependencyGraph) -> List[List[Path]]:
    cycles: List[List[Path]] = []
    visited: Set[Path] = set()
    rec_stack: List[Path] = []
    rec_set: Set[Path] = set()

    def dfs(node: Path):
        visited.add(node)
        rec_stack.append(node)
        rec_set.add(node)

        if node in graph.edges:
            for edge in graph.edges[node]:
                neighbor = edge.to_script
                if neighbor is None:
                    continue
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_set:
                    cycle_start = rec_stack.index(neighbor)
                    cycle = rec_stack[cycle_start:] + [neighbor]
                    cycles.append(cycle)

        rec_stack.pop()
        rec_set.discard(node)

    for script_path in graph.scripts:
        if script_path not in visited:
            dfs(script_path)

    return cycles


def is_part_of_cycle(graph: DependencyGraph, script_path: Path) -> bool:
    for cycle in graph.cycles:
        if script_path in cycle:
            return True
    return False


def get_cycles_involving(graph: DependencyGraph, script_path: Path) -> List[List[Path]]:
    return [c for c in graph.cycles if script_path in c]
