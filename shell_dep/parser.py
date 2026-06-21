"""Orchestration layer: coordinates detection, extraction, and resolution.

Single responsibility of THIS module:
  - define the public data classes (SourceStatement, ShellScript)
  - resolve raw source paths against the filesystem (PathResolver)
  - parse a single file / scan a directory by delegating to the
    detection, extraction, and lexing layers.

Lower layers know nothing about the filesystem or about ShellScript:
  - detector.py  -> "is this a shell script?"
  - lexer.py     -> "tokenize this text"
  - extractor.py -> "which source/. commands are here?"
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict

from .detector import ScriptDetector
from .extractor import SourceExtractor, RawSource


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


class PathResolver:
    """Resolves a raw source path relative to the importing script."""

    @staticmethod
    def resolve(source_file: Path, raw_path: str) -> Optional[Path]:
        source_path = Path(raw_path)
        if source_path.is_absolute():
            candidate = source_path
        else:
            candidate = source_file.parent / source_path
        candidate = candidate.resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
        return None


class ShellScriptParser:
    """Parses shell scripts into ShellScript objects."""

    def __init__(self):
        self._extractor = SourceExtractor()
        self._detector = ScriptDetector()
        self._resolver = PathResolver()

    def parse(self, file_path: Path) -> ShellScript:
        script = ShellScript(path=file_path.resolve())
        text = self._read_text(file_path)
        if text is None:
            return script

        for raw in self._extractor.extract(text):
            resolved = None
            if not raw.is_dynamic:
                resolved = self._resolver.resolve(file_path, raw.raw_path)
            script.sources.append(SourceStatement(
                raw_path=raw.raw_path,
                resolved_path=resolved,
                line_number=raw.line_number,
                is_dynamic=raw.is_dynamic,
            ))
        return script

    @staticmethod
    def _read_text(file_path: Path) -> Optional[str]:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except (OSError, IOError):
            return None


_PARSER = ShellScriptParser()


def parse_shell_script(file_path: Path) -> ShellScript:
    return _PARSER.parse(file_path)


def scan_directory(directory: Path) -> Dict[Path, ShellScript]:
    scripts: Dict[Path, ShellScript] = {}
    for root, _dirs, files in os.walk(directory):
        root_path = Path(root)
        for filename in files:
            file_path = root_path / filename
            if ScriptDetector.is_shell_script(file_path):
                script = parse_shell_script(file_path)
                scripts[script.path] = script
    return scripts
