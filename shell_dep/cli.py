import argparse
import sys
from pathlib import Path

from colorama import Fore, Style

from .parser import scan_directory
from .graph import build_dependency_graph
from .renderer import render_tree, render_summary
from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='shell-dep',
        description='Analyze shell script dependencies (.sh/.bash) and render ASCII tree.',
    )
    parser.add_argument(
        'directory',
        nargs='?',
        default='.',
        help='Target directory to scan (default: current directory)',
    )
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'%(prog)s {__version__}',
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output',
    )
    parser.add_argument(
        '--warn-only',
        action='store_true',
        help='Exit 0 even if issues are found (default: exit 1 on issues)',
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Only print summary, not the full tree',
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.no_color:
        import colorama
        colorama.deinit()
        import colorama.initialise
        colorama.initialise.wrap = False

    target = Path(args.directory).resolve()

    if not target.exists():
        print(f'{Fore.RED}Error: directory not found: {target}{Style.RESET_ALL}', file=sys.stderr)
        return 1

    if not target.is_dir():
        print(f'{Fore.RED}Error: not a directory: {target}{Style.RESET_ALL}', file=sys.stderr)
        return 1

    scripts = scan_directory(target)
    if not scripts:
        print(f'{Fore.YELLOW}No .sh or .bash scripts found in: {target}{Style.RESET_ALL}')
        return 0

    graph = build_dependency_graph(scripts)

    if not args.quiet:
        print(render_tree(graph, base_dir=target))

    print(render_summary(graph))

    if graph.has_issues() and not args.warn_only:
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
