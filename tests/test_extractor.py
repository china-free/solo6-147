"""Unit tests for the rewritten lexer + extractor (recall improvement)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shell_dep.lexer import ShellLexer, Token, WORD, OP, NEWLINE
from shell_dep.extractor import SourceExtractor, RawSource
from shell_dep.parser import parse_shell_script


def _extract_paths(text: str):
    return [r.raw_path for r in SourceExtractor().extract(text)]


class TestShellLexer(unittest.TestCase):
    def test_simple_word_split(self):
        tokens = ShellLexer().tokenize("source foo.sh\n")
        words = [t.value for t in tokens if t.kind == WORD]
        self.assertIn('source', words)
        self.assertIn('foo.sh', words)

    def test_comment_at_command_boundary(self):
        tokens = ShellLexer().tokenize("echo hi # source not_a_cmd.sh\n")
        words = [t.value for t in tokens if t.kind == WORD]
        self.assertNotIn('not_a_cmd.sh', words)

    def test_comment_inside_double_quotes_kept(self):
        tokens = ShellLexer().tokenize('source "a#b.sh"\n')
        words = [t.value for t in tokens if t.kind == WORD]
        self.assertEqual(words, ['source', '"a#b.sh"'])

    def test_single_quote_no_expansion(self):
        tokens = ShellLexer().tokenize("echo '$HOME/x.sh'\n")
        words = [t.value for t in tokens if t.kind == WORD]
        self.assertEqual(words[1], "'$HOME/x.sh'")

    def test_dollar_paren_kept_in_word(self):
        tokens = ShellLexer().tokenize("source $(dirname $0)/x.sh\n")
        words = [t.value for t in tokens if t.kind == WORD]
        self.assertEqual(words[1], '$(dirname $0)/x.sh')

    def test_line_numbers_tracked(self):
        tokens = ShellLexer().tokenize("\n\nsource x.sh\n")
        source_tok = [t for t in tokens if t.kind == WORD and t.value == 'source'][0]
        self.assertEqual(source_tok.line, 3)

    def test_heredoc_body_skipped(self):
        text = "cat <<EOF\nsource not_real.sh\nEOF\nsource real.sh\n"
        tokens = ShellLexer().tokenize(text)
        words = [t.value for t in tokens if t.kind == WORD]
        self.assertIn('real.sh', words)
        self.assertNotIn('not_real.sh', words)


class TestSourceExtractorRecall(unittest.TestCase):
    """The core goal: previously-missed patterns must now be extracted."""

    def test_source_inside_if_then(self):
        text = "if [ -f c.sh ]; then\n  source ./c.sh\nfi\n"
        self.assertIn('./c.sh', _extract_paths(text))

    def test_env_var_prefix_source(self):
        text = "DEBUG=1 VERBOSE=1 source ./utils.sh\n"
        self.assertIn('./utils.sh', _extract_paths(text))

    def test_inline_command_then_source(self):
        text = 'echo "loading"; source ./config.sh\n'
        self.assertIn('./config.sh', _extract_paths(text))

    def test_conditional_and_chain(self):
        text = "[ -r ./u.sh ] && source ./u.sh\n"
        self.assertIn('./u.sh', _extract_paths(text))

    def test_source_in_for_loop(self):
        text = "for m in config; do source ./${m}.sh; done\n"
        paths = _extract_paths(text)
        self.assertIn('./${m}.sh', paths)

    def test_command_substitution_arg_dynamic(self):
        text = 'source "$(dirname "$0")/lib/utils.sh"\n'
        results = SourceExtractor().extract(text)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].is_dynamic)

    def test_dot_after_env_var(self):
        text = "ROOT_DIR=. . ./lib/config.sh\n"
        self.assertIn('./lib/config.sh', _extract_paths(text))

    def test_source_in_brace_group(self):
        text = "{ source ./lib/utils.sh; }\n"
        self.assertIn('./lib/utils.sh', _extract_paths(text))

    def test_no_false_positive_dot_in_path(self):
        text = "./deploy.sh --flag=value\n"
        self.assertEqual(_extract_paths(text), [])

    def test_no_false_positive_source_in_string(self):
        text = 'echo "do not source this.sh please"\n'
        self.assertEqual(_extract_paths(text), [])

    def test_no_false_positive_in_heredoc(self):
        text = "cat <<EOF\nsource heredoc_fake.sh\nEOF\nsource real.sh\n"
        paths = _extract_paths(text)
        self.assertIn('real.sh', paths)
        self.assertNotIn('heredoc_fake.sh', paths)

    def test_multiple_sources_recalled(self):
        text = (
            "source ./a.sh\n"
            "if true; then source ./b.sh; fi\n"
            "X=1 source ./c.sh\n"
        )
        paths = _extract_paths(text)
        self.assertEqual(set(paths), {'./a.sh', './b.sh', './c.sh'})

    def test_line_numbers_correct(self):
        text = "\n\nsource ./deep.sh\n"
        results = SourceExtractor().extract(text)
        self.assertEqual(results[0].line_number, 3)

    def test_pipeline_does_not_drop_first_source(self):
        text = "source ./first.sh | grep x\n"
        self.assertIn('./first.sh', _extract_paths(text))


class TestParserIntegration(unittest.TestCase):
    """Ensure the public parse API still works end-to-end."""

    def test_parse_complex_sources_file(self):
        test_dir = Path(__file__).parent.parent / "test_scripts"
        script_path = test_dir / "complex_sources.sh"
        script = parse_shell_script(script_path)

        raw_paths = [s.raw_path for s in script.sources]
        self.assertIn('./lib/config.sh', raw_paths)
        self.assertIn('./lib/utils.sh', raw_paths)
        self.assertIn('./lib/${mod}.sh', raw_paths)
        self.assertGreaterEqual(
            raw_paths.count('./lib/config.sh') + raw_paths.count('./lib/utils.sh'),
            3,
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
