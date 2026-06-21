"""
Unit tests for shell-dep circular dependency handling.
"""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from shell_dep.parser import parse_shell_script, scan_directory
from shell_dep.graph import (
    build_dependency_graph,
    detect_cycles,
    DependencyGraph,
    is_part_of_cycle,
)
from shell_dep.renderer import render_tree, render_summary, _path_key


class TestCircularDependency(unittest.TestCase):
    """Test circular dependency detection and rendering."""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_script(self, name: str, content: str) -> Path:
        path = self.test_dir / name
        path.write_text(content, encoding='utf-8')
        return path

    def test_self_reference_detection(self):
        """Test detection of self-referencing script (A source A)."""
        self._create_script('a.sh', '''#!/bin/bash
source ./a.sh
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        self.assertEqual(len(graph.scripts), 1)
        self.assertEqual(len(graph.cycles), 1)
        self.assertTrue(graph.has_issues())

        a_path = list(graph.scripts.keys())[0]
        self.assertTrue(is_part_of_cycle(graph, a_path))

    def test_two_way_circular_dependency(self):
        """Test detection of two-way circular dependency (A source B, B source A)."""
        self._create_script('a.sh', '''#!/bin/bash
source ./b.sh
''')
        self._create_script('b.sh', '''#!/bin/bash
source ./a.sh
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        self.assertEqual(len(graph.scripts), 2)
        self.assertEqual(len(graph.cycles), 1)
        self.assertTrue(graph.has_issues())

        for path in graph.scripts:
            self.assertTrue(is_part_of_cycle(graph, path))

    def test_three_way_circular_dependency(self):
        """Test detection of three-way circular dependency (A->B->C->A)."""
        self._create_script('a.sh', '''#!/bin/bash
source ./b.sh
''')
        self._create_script('b.sh', '''#!/bin/bash
source ./c.sh
''')
        self._create_script('c.sh', '''#!/bin/bash
source ./a.sh
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        self.assertEqual(len(graph.scripts), 3)
        self.assertEqual(len(graph.cycles), 1)
        self.assertTrue(graph.has_issues())

        for path in graph.scripts:
            self.assertTrue(is_part_of_cycle(graph, path))

    def test_missing_file_detection(self):
        """Test detection of source to non-existent file."""
        self._create_script('a.sh', '''#!/bin/bash
source ./exists.sh
source ./missing.sh
''')
        self._create_script('exists.sh', '''#!/bin/bash
echo "exists"
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        self.assertEqual(len(graph.scripts), 2)
        self.assertEqual(len(graph.missing_files), 1)
        self.assertEqual(len(graph.cycles), 0)
        self.assertTrue(graph.has_issues())

        missing_edge = graph.missing_files[0]
        self.assertEqual(missing_edge.source_stmt.raw_path, './missing.sh')

    def test_dynamic_source_detection(self):
        """Test detection of dynamic source with variables."""
        self._create_script('a.sh', '''#!/bin/bash
MODULE="utils"
source ./${MODULE}.sh
source "$HOME/config.sh"
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        self.assertEqual(len(graph.scripts), 1)
        self.assertEqual(len(graph.dynamic_sources), 2)
        self.assertEqual(len(graph.cycles), 0)
        self.assertFalse(graph.has_issues())

    def test_render_tree_no_recursion_error(self):
        """Test that rendering circular dependencies does NOT cause RecursionError."""
        self._create_script('a.sh', '''#!/bin/bash
source ./b.sh
source ./c.sh
''')
        self._create_script('b.sh', '''#!/bin/bash
source ./a.sh
''')
        self._create_script('c.sh', '''#!/bin/bash
echo "leaf node"
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        old_limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(50)
            output = render_tree(graph, base_dir=self.test_dir)
            self.assertIsInstance(output, str)
            self.assertIn('↻ CYCLE', output)
        finally:
            sys.setrecursionlimit(old_limit)

    def test_render_tree_missing_file_highlight(self):
        """Test that missing files are highlighted in red."""
        self._create_script('a.sh', '''#!/bin/bash
source ./missing.sh
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)
        output = render_tree(graph, base_dir=self.test_dir)

        self.assertIn('✗ MISSING', output)
        self.assertIn('missing.sh', output)

    def test_render_tree_cycle_highlight(self):
        """Test that circular dependencies are highlighted in red."""
        self._create_script('a.sh', '''#!/bin/bash
source ./b.sh
''')
        self._create_script('b.sh', '''#!/bin/bash
source ./a.sh
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)
        output = render_tree(graph, base_dir=self.test_dir)

        self.assertIn('↻ CYCLE', output)

    def test_exit_code_1_on_issues(self):
        """Test that graph.has_issues() returns True when problems exist."""
        self._create_script('a.sh', '''#!/bin/bash
source ./b.sh
''')
        self._create_script('b.sh', '''#!/bin/bash
source ./a.sh
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        self.assertTrue(graph.has_issues())

    def test_exit_code_0_when_clean(self):
        """Test that graph.has_issues() returns False when no problems exist."""
        self._create_script('a.sh', '''#!/bin/bash
source ./b.sh
''')
        self._create_script('b.sh', '''#!/bin/bash
echo "hello"
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        self.assertFalse(graph.has_issues())

    def test_path_key_consistency(self):
        """Test that _path_key produces consistent keys for the same file."""
        path1 = Path(self.test_dir / 'a.sh')
        path2 = Path(self.test_dir / './a.sh')
        path3 = Path(str(self.test_dir) + '/a.sh')

        self.assertEqual(_path_key(path1), _path_key(path2))
        self.assertEqual(_path_key(path1), _path_key(path3))

    def test_already_shown_marker(self):
        """Test that already visited nodes are marked as 'already shown'."""
        self._create_script('a.sh', '''#!/bin/bash
source ./b.sh
source ./c.sh
''')
        self._create_script('b.sh', '''#!/bin/bash
source ./c.sh
''')
        self._create_script('c.sh', '''#!/bin/bash
echo "shared"
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)
        output = render_tree(graph, base_dir=self.test_dir)

        self.assertIn('already shown', output)

    def test_multiple_independent_cycles(self):
        """Test detection of multiple independent circular dependencies."""
        self._create_script('a.sh', 'source ./b.sh\n')
        self._create_script('b.sh', 'source ./a.sh\n')
        self._create_script('c.sh', 'source ./d.sh\n')
        self._create_script('d.sh', 'source ./c.sh\n')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)

        self.assertEqual(len(graph.scripts), 4)
        self.assertEqual(len(graph.cycles), 2)
        self.assertTrue(graph.has_issues())

    def test_render_summary(self):
        """Test that summary output contains expected information."""
        self._create_script('a.sh', '''#!/bin/bash
source ./b.sh
source ./missing.sh
''')
        self._create_script('b.sh', '''#!/bin/bash
source ./a.sh
source "$VAR"
''')

        scripts = scan_directory(self.test_dir)
        graph = build_dependency_graph(scripts)
        summary = render_summary(graph)

        self.assertIn('Total scripts:', summary)
        self.assertIn('Missing files:', summary)
        self.assertIn('Dependency cycles:', summary)
        self.assertIn('Dynamic sources:', summary)
        self.assertIn('Missing source files:', summary)
        self.assertIn('Circular dependencies detected:', summary)

    def test_no_shell_scripts(self):
        """Test behavior when no shell scripts are found."""
        self._create_script('readme.txt', 'Not a shell script\n')

        scripts = scan_directory(self.test_dir)
        self.assertEqual(len(scripts), 0)

        graph = build_dependency_graph(scripts)
        output = render_tree(graph, base_dir=self.test_dir)

        self.assertIn('No shell scripts found', output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
