"""Extraction layer: locate `source` / `.` commands in a token stream.

Single responsibility: given bash text, produce a list of RawSource records
(raw path, line number, dynamic flag). Path resolution is NOT done here.

Strategy (layered, defensive):
  1. Try an optional bashlex AST pass (soft dependency). When bashlex is
     importable AND the script parses cleanly, the AST gives high-recision
     command identification.
  2. Otherwise fall back to a robust token-driven extractor that walks the
     ShellLexer token stream, splits it into command segments on operators
     and control keywords, strips leading VAR=value assignments, and treats
     the first remaining word as the command name.

The fallback never raises, which is essential for legacy scripts that contain
syntax errors (bashlex would refuse to parse them).
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from .lexer import ShellLexer, Token, WORD, OP, NEWLINE


@dataclass
class RawSource:
    raw_path: str
    line_number: int
    is_dynamic: bool = False


_SOURCE_COMMANDS = {'source', '.'}

_COMMAND_TERMINATORS = {
    ';', '&&', '||', '|', '&', '(', ')', '{', '}',
    '<<', '<<-',
}

_CONTROL_KEYWORDS = {
    'if', 'then', 'else', 'elif', 'fi',
    'for', 'do', 'done', 'while', 'until',
    'case', 'esac', 'function', 'in',
}

_ASSIGNMENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
_DYNAMIC_RE = re.compile(r'[$({`\\]')


def _strip_quotes(path_str: str) -> str:
    s = path_str.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or
                       (s[0] == "'" and s[-1] == "'")):
        inner = s[1:-1]
        if '"' not in inner and "'" not in inner:
            return inner
    return s


class SourceExtractor:
    """Extracts `source`/`.` statements from bash text."""

    def __init__(self):
        self._lexer = ShellLexer()

    def extract(self, text: str) -> List[RawSource]:
        results = self._try_bashlex(text)
        if results is not None:
            return results
        return self._extract_from_tokens(text)

    def _try_bashlex(self, text: str) -> Optional[List[RawSource]]:
        try:
            import bashlex  # type: ignore
        except ImportError:
            return None
        try:
            tree = bashlex.parse(text)
        except Exception:
            return None
        try:
            return self._collect_from_bashlex_ast(tree, text)
        except Exception:
            return None

    def _collect_from_bashlex_ast(self, nodes, text: str) -> List[RawSource]:
        results: List[RawSource] = []
        for node in nodes:
            self._walk_bashlex(node, text, results)
        return results

    def _walk_bashlex(self, node, text: str, results: List[RawSource]):
        node_kind = getattr(node, 'kind', None)

        if node_kind == 'command' or node_kind == 'compound':
            parts = getattr(node, 'parts', None) or []
            words = [p for p in parts if getattr(p, 'kind', None) == 'word']
            if words:
                cmd_name = _bashlex_word_text(words[0], text)
                if cmd_name in _SOURCE_COMMANDS and len(words) >= 2:
                    arg = _bashlex_word_text(words[1], text)
                    raw = _strip_quotes(arg)
                    if raw:
                        results.append(RawSource(
                            raw_path=raw,
                            line_number=text.count('\n', 0, words[1].pos) + 1,
                            is_dynamic=bool(_DYNAMIC_RE.search(raw)),
                        ))

        for attr in ('parts', 'list', 'body', 'pipestatus',
                     'command', 'condition', 'then', 'else'):
            child = getattr(node, attr, None)
            if child is None:
                continue
            children = child if isinstance(child, list) else [child]
            for c in children:
                if hasattr(c, 'kind'):
                    self._walk_bashlex(c, text, results)

    def _extract_from_tokens(self, text: str) -> List[RawSource]:
        tokens = self._lexer.tokenize(text)
        results: List[RawSource] = []
        at_command_start = True
        idx = 0
        total = len(tokens)

        while idx < total:
            token = tokens[idx]

            if token.kind == OP and token.value in _COMMAND_TERMINATORS:
                at_command_start = True
                idx += 1
                continue

            if token.kind == NEWLINE:
                at_command_start = True
                idx += 1
                continue

            if token.kind == WORD and token.value in _CONTROL_KEYWORDS:
                at_command_start = True
                idx += 1
                continue

            if at_command_start and token.kind == WORD:
                if _ASSIGNMENT_RE.match(token.value):
                    idx += 1
                    continue

                at_command_start = False
                if token.value in _SOURCE_COMMANDS:
                    idx += 1
                    arg_token = self._next_word_token(tokens, idx, total)
                    if arg_token is not None:
                        raw = _strip_quotes(arg_token.value)
                        if raw:
                            results.append(RawSource(
                                raw_path=raw,
                                line_number=arg_token.line,
                                is_dynamic=bool(_DYNAMIC_RE.search(raw)),
                            ))
                        idx += 1
                    continue

                idx += 1
                continue

            idx += 1

        return results

    @staticmethod
    def _next_word_token(tokens: List[Token], idx: int,
                         total: int) -> Optional[Token]:
        j = idx
        while j < total:
            t = tokens[j]
            if t.kind == WORD:
                return t
            if t.kind in (OP, NEWLINE):
                return None
            j += 1
        return None


def _bashlex_word_text(word_node, text: str) -> str:
    start = getattr(word_node, 'pos', None)
    end = getattr(word_node, 'end', None)
    if start is None or end is None:
        return ''
    return text[start:end]
