"""Lexing layer: tokenize bash text into words, operators, and newlines.

Single responsibility: convert raw shell text into a flat token stream.
The lexer is a hand-written state machine that correctly handles:
  - single and double quotes (with their distinct escaping rules)
  - backslash escapes
  - comments (# outside quotes)
  - command substitution $(...) and backticks (kept inside the word token)
  - heredocs (body skipped to avoid false-positive source detection)
  - multi-character operators (;, &&, ||, |, &, (, ), {, })

It never raises on malformed input; unrecognized characters become word
content so that legacy "祖传" scripts with syntax errors still tokenize.
"""
from dataclasses import dataclass
from typing import List


WORD = 'WORD'
OP = 'OP'
NEWLINE = 'NEWLINE'


@dataclass
class Token:
    kind: str
    value: str
    line: int


class ShellLexer:
    """State-machine tokenizer for bash text."""

    def tokenize(self, text: str) -> List[Token]:
        tokens: List[Token] = []
        i = 0
        n = len(text)
        line = 1
        pending_word: List[str] = []
        word_line = 1

        def flush_word():
            if pending_word:
                tokens.append(Token(WORD, ''.join(pending_word), word_line))
                pending_word.clear()

        while i < n:
            ch = text[i]

            if ch == '\n':
                flush_word()
                tokens.append(Token(NEWLINE, '\n', line))
                line += 1
                i += 1
                continue

            if ch == '#':
                if not pending_word:
                    i = self._skip_comment(text, i, n)
                    continue

            if ch.isspace():
                flush_word()
                i += 1
                continue

            if ch == '\\' and i + 1 < n:
                if not pending_word:
                    word_line = line
                nxt = text[i + 1]
                if nxt == '\n':
                    line += 1
                    i += 2
                    continue
                pending_word.append(nxt)
                i += 2
                continue

            if ch == "'":
                if not pending_word:
                    word_line = line
                i = self._consume_single_quote(text, i, n, pending_word)
                continue

            if ch == '"':
                if not pending_word:
                    word_line = line
                i = self._consume_double_quote(text, i, n, pending_word, line)
                continue

            if ch == '`':
                if not pending_word:
                    word_line = line
                i = self._consume_backtick(text, i, n, pending_word, line)
                continue

            if ch == '$' and i + 1 < n and text[i + 1] == '(':
                if not pending_word:
                    word_line = line
                i = self._consume_dollar_paren(text, i, n, pending_word, line)
                continue

            if ch == '$' and i + 1 < n and text[i + 1] == '{':
                if not pending_word:
                    word_line = line
                i = self._consume_dollar_brace(text, i, n, pending_word)
                continue

            op = self._match_operator(text, i, n)
            if op is not None:
                flush_word()
                tokens.append(Token(OP, op, line))
                i += len(op)
                heredoc = self._match_heredoc(tokens, text, i, n)
                if heredoc is not None:
                    i, line = heredoc
                continue

            if not pending_word:
                word_line = line
            pending_word.append(ch)
            i += 1

        flush_word()
        return tokens

    @staticmethod
    def _at_command_boundary(tokens: List[Token]) -> bool:
        if not tokens:
            return True
        last = tokens[-1]
        return last.kind in (OP, NEWLINE)

    @staticmethod
    def _skip_comment(text: str, i: int, n: int) -> int:
        while i < n and text[i] != '\n':
            i += 1
        return i

    @staticmethod
    def _consume_single_quote(text: str, i: int, n: int, word: List[str]) -> int:
        word.append("'")
        i += 1
        while i < n:
            ch = text[i]
            if ch == "'":
                word.append("'")
                return i + 1
            word.append(ch)
            i += 1
        return i

    @staticmethod
    def _consume_double_quote(text: str, i: int, n: int,
                              word: List[str], line: int) -> int:
        word.append('"')
        i += 1
        while i < n:
            ch = text[i]
            if ch == '\\' and i + 1 < n:
                word.append(ch)
                word.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                word.append('"')
                return i + 1
            if ch == '`':
                word.append('`')
                i += 1
                depth = 1
                while i < n and depth > 0:
                    c = text[i]
                    if c == '`' and depth == 1:
                        word.append('`')
                        i += 1
                        depth = 0
                        break
                    if c == '\\' and i + 1 < n:
                        word.append(c)
                        word.append(text[i + 1])
                        i += 2
                        continue
                    word.append(c)
                    i += 1
                continue
            if ch == '$' and i + 1 < n and text[i + 1] == '(':
                word.append('$(')
                i += 2
                depth = 1
                while i < n and depth > 0:
                    c = text[i]
                    if c == '(':
                        depth += 1
                    elif c == ')':
                        depth -= 1
                        if depth == 0:
                            word.append(')')
                            i += 1
                            break
                    word.append(c)
                    i += 1
                continue
            word.append(ch)
            i += 1
        return i

    @staticmethod
    def _consume_backtick(text: str, i: int, n: int,
                          word: List[str], line: int) -> int:
        word.append('`')
        i += 1
        while i < n:
            ch = text[i]
            if ch == '\\' and i + 1 < n:
                word.append(ch)
                word.append(text[i + 1])
                i += 2
                continue
            if ch == '`':
                word.append('`')
                return i + 1
            word.append(ch)
            i += 1
        return i

    @staticmethod
    def _consume_dollar_paren(text: str, i: int, n: int,
                               word: List[str], line: int) -> int:
        word.append('$(')
        i += 2
        depth = 1
        while i < n and depth > 0:
            ch = text[i]
            if ch == '\\' and i + 1 < n:
                word.append(ch)
                word.append(text[i + 1])
                i += 2
                continue
            if ch == "'":
                word.append("'")
                i = ShellLexer._consume_single_quote(text, i, n, word)
                continue
            if ch == '"':
                word.append('"')
                i = ShellLexer._consume_double_quote(text, i, n, word, line)
                continue
            if ch == '`':
                word.append('`')
                i = ShellLexer._consume_backtick(text, i, n, word, line)
                continue
            if ch == '$' and i + 1 < n and text[i + 1] == '(':
                word.append('$(')
                depth += 1
                i += 2
                continue
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    word.append(')')
                    return i + 1
            word.append(ch)
            i += 1
        return i

    @staticmethod
    def _consume_dollar_brace(text: str, i: int, n: int,
                              word: List[str]) -> int:
        word.append('${')
        i += 2
        depth = 1
        while i < n and depth > 0:
            ch = text[i]
            if ch == '\\' and i + 1 < n:
                word.append(ch)
                word.append(text[i + 1])
                i += 2
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    word.append('}')
                    return i + 1
            word.append(ch)
            i += 1
        return i

    @staticmethod
    def _match_operator(text: str, i: int, n: int):
        three = text[i:i + 3]
        if three == '<<-':
            return '<<-'
        two = text[i:i + 2]
        if two in ('&&', '||', '<<'):
            return two
        one = text[i]
        if one in (';', '|', '&', '(', ')', '{', '}'):
            return one
        return None

    @staticmethod
    def _match_heredoc(tokens: List[Token], text: str, i: int, n: int):
        if not tokens:
            return None
        last = tokens[-1]
        if last.value not in ('<<', '<<-'):
            return None
        strip_tabs = (last.value == '<<-')
        j = i
        while j < n and text[j] in (' \t'):
            j += 1
        delim_chars: List[str] = []
        if j < n and text[j] in ('"', "'"):
            quote = text[j]
            j += 1
            while j < n and text[j] != quote:
                delim_chars.append(text[j])
                j += 1
            if j < n:
                j += 1
        else:
            while j < n and (text[j].isalnum() or text[j] == '_'):
                delim_chars.append(text[j])
                j += 1
        if not delim_chars:
            return None
        delimiter = ''.join(delim_chars)
        while j < n and text[j] != '\n':
            j += 1
        if j < n:
            j += 1
        while j < n:
            end = text.find('\n', j)
            if end == -1:
                chunk = text[j:]
                next_i = n
            else:
                chunk = text[j:end]
                next_i = end + 1
            candidate = chunk.lstrip('\t') if strip_tabs else chunk
            if candidate.rstrip() == delimiter:
                return next_i, last.line + text[i:next_i].count('\n')
            j = next_i
        return n, last.line + text[i:n].count('\n')
