import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Tuple


@dataclass
class SourceStatement:
    raw_path: str
    resolved_path: Optional[Path]
    line_number: int
    is_dynamic: bool = False


@dataclass
class ShellScript:
    path: Path
    sources: List[SourceStatement] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name


SOURCE_PATTERNS = [
    re.compile(r'^\s*source\s+(.+?)\s*$'),
    re.compile(r'^\s*\.\s+(.+?)\s*$'),
]

DYNAMIC_PATH_PATTERN = re.compile(r'(\$|\{)')


def is_shell_script(file_path: Path) -> bool:
    if file_path.suffix.lower() in ('.sh', '.bash'):
        return True
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            if first_line.startswith('#!') and ('bash' in first_line or 'sh' in first_line):
                return True
    except (OSError, IOError):
        pass
    return False


def strip_shell_comments(line: str) -> str:
    in_single_quote = False
    in_double_quote = False
    for i, char in enumerate(line):
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == '#' and not in_single_quote and not in_double_quote:
            if i == 0 or (i > 0 and line[i - 1].isspace()):
                return line[:i].rstrip()
    return line


def strip_quotes(path_str: str) -> str:
    path_str = path_str.strip()
    if len(path_str) >= 2:
        if (path_str[0] == '"' and path_str[-1] == '"') or \
           (path_str[0] == "'" and path_str[-1] == "'"):
            return path_str[1:-1]
    return path_str


def parse_source_path(raw_match: str) -> Tuple[str, bool]:
    parts = raw_match.split()
    if not parts:
        return '', False
    path_str = strip_quotes(parts[0])
    is_dynamic = bool(DYNAMIC_PATH_PATTERN.search(path_str))
    return path_str, is_dynamic


def resolve_source_path(source_file: Path, raw_path: str) -> Optional[Path]:
    source_path = Path(raw_path)
    if source_path.is_absolute():
        candidate = source_path
    else:
        candidate = source_file.parent / source_path
    candidate = candidate.resolve()
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def parse_shell_script(file_path: Path) -> ShellScript:
    script = ShellScript(path=file_path.resolve())
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except (OSError, IOError):
        return script

    for line_num, raw_line in enumerate(lines, start=1):
        line = strip_shell_comments(raw_line)
        if not line.strip():
            continue
        for pattern in SOURCE_PATTERNS:
            match = pattern.match(line)
            if match:
                raw_match = match.group(1)
                raw_path, is_dynamic = parse_source_path(raw_match)
                if raw_path:
                    resolved = None if is_dynamic else resolve_source_path(file_path, raw_path)
                    script.sources.append(SourceStatement(
                        raw_path=raw_path,
                        resolved_path=resolved,
                        line_number=line_num,
                        is_dynamic=is_dynamic,
                    ))
                break
    return script


def scan_directory(directory: Path) -> Dict[Path, ShellScript]:
    scripts: Dict[Path, ShellScript] = {}
    for root, dirs, files in os.walk(directory):
        root_path = Path(root)
        for filename in files:
            file_path = root_path / filename
            if is_shell_script(file_path):
                script = parse_shell_script(file_path)
                scripts[script.path] = script
    return scripts
