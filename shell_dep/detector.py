"""Detection layer: determine whether a file is a shell script.

Single responsibility: identify shell scripts by extension or shebang.
"""
from pathlib import Path


SHELL_EXTENSIONS = {'.sh', '.bash'}
SHELL_INTERPRETERS = ('bash', '/sh', ' sh', 'zsh', 'dash', 'ksh')


class ScriptDetector:
    """Identifies shell scripts by file extension or shebang line."""

    @staticmethod
    def is_shell_script(file_path: Path) -> bool:
        if ScriptDetector._has_shell_extension(file_path):
            return True
        return ScriptDetector._has_shell_shebang(file_path)

    @staticmethod
    def _has_shell_extension(file_path: Path) -> bool:
        return file_path.suffix.lower() in SHELL_EXTENSIONS

    @staticmethod
    def _has_shell_shebang(file_path: Path) -> bool:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
        except (OSError, IOError):
            return False
        if not first_line.startswith('#!'):
            return False
        return any(interp in first_line for interp in SHELL_INTERPRETERS)
