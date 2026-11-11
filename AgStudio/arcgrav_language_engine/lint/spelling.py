"""Offline English spelling over conservative canonical prose spans only."""
from functools import lru_cache
from pathlib import Path
import re
from threading import Lock
from typing import Iterable, Protocol
import unicodedata

from ..recognition import SourceSpan

SPELLING_MESSAGES = {
    'AG-SPELLING': 'Possible English misspelling',
    'AG-SPELLCHECK-UNAVAILABLE': 'English spellcheck is unavailable; install AgStudio/gui/requirements.txt and restart AgStudio.',
}
_WORD = re.compile(r"[^\W\d_]+(?:[\u0300-\u036f]+[^\W\d_]*)*(?:['’][^\W\d_]+)*", re.UNICODE)
_RUN = re.compile(r'\S+')
_CALL = re.compile(r'\b\w+\(')
_ASSIGNMENT = re.compile(r'(?<!\S)[A-Za-z_]\w*(?:\.\w+)*\s*(?::=|=(?!=))')
_CAMEL = re.compile(r'[a-z][A-Z]')
_DOTTED = re.compile(r'\w[.:]\w')
_CACHE_SIZE = 8192


# Small, reviewed supplement for the editor's technical prose; not an acronym
# exemption or a replacement for the packaged English dictionary.
TECHNICAL_WORDS = frozenset("""
api apis arcgrav agstudio backtick backticks backticked codepoint codepoints
config configs dataclass dataclasses dataset datasets deserialize deserialized
deserialization deterministic encodings github hashmap hashmaps iterable iterables
json jsonl lexer lexers llm llms lookup lookups metadata namespace namespaces
newline newlines offline openai plaintext pseudocode reachability refactor
refactored refactoring regex runtime runtimes serialize serialized serialization
spellcheck spellchecker subtree subtrees tokenizer tokenizers tokenization tuple
tuples unhashable utf validator validators whitespace wildcard wildcards workflow
workflows yaml
""".split())


def normalize_vocabulary_word(word):
    """Accept a single prose token, never patterns, phrases or file paths."""
    if not isinstance(word, str) or not 1 <= len(word) <= 128 or _WORD.fullmatch(word) is None:
        return None
    return _normalize(word)


def _vocabulary_words(value):
    if not isinstance(value, (list, tuple)) or len(value) > 20000:
        return frozenset()
    return frozenset(word for item in value
                     if (word := normalize_vocabulary_word(item)) is not None)


def _in_vocabulary(word, words):
    return word in words or (word.endswith("'s") and word[:-2] in words)


class WordLookup(Protocol):
    """Recognition boundary; analyzers need no correction-generation capability."""

    def spell(self, word: str) -> bool: ...


class SuggestionProvider(Protocol):
    """Explicit correction boundary, invoked only by a requesting consumer."""

    def suggest(self, word: str) -> Iterable[str]: ...


def _recognized(lookup: WordLookup, word: str) -> bool:
    # Keep exact supplemental vocabulary's productive possessives.
    return bool(lookup.spell(word) or
                (word.endswith("'s") and lookup.spell(word[:-2])))


def _ranked_corrections(provider: SuggestionProvider, word: str):
    return tuple(dict.fromkeys(candidate for candidate in provider.suggest(word)
                               if candidate))[:5]


def _load_checker():
    """Load native Hunspell with our fixed, licensed US-English resource pair."""
    try:
        from hunspell import Hunspell
        checker = Hunspell('en_US', hunspell_data_dir=str(Path(__file__).with_name('dictionaries')),
                           system_encoding='UTF-8')
        # Exact words only: no inherited affix flags or broad acronym exemption.
        for word in sorted(TECHNICAL_WORDS):
            if checker.add(word) != 0:
                raise ValueError('Could not load AgStudio technical vocabulary')
        if not checker.spell('hello') or checker.spell('zzzxxyyqq'):
            raise ValueError('Invalid Hunspell dictionary')
        return checker
    except (ImportError, OSError, ValueError):
        return None


# Load only the fixed installed resource, once on demand. Imports, parse-only
# work and disabled spellcheck never initialize the dictionary. None records a
# missing/broken installation so enabled checks report Info without retrying.
_UNINITIALIZED = object()
_CHECKER = _UNINITIALIZED
_CHECKER_LOCK = Lock()
_LOOKUP_LOCK = Lock()


def _get_checker():
    global _CHECKER
    if _CHECKER is _UNINITIALIZED:
        with _CHECKER_LOCK:
            if _CHECKER is _UNINITIALIZED:
                _CHECKER = _load_checker()
    return _CHECKER


def _normalize(word):
    return unicodedata.normalize('NFC', word).replace('’', "'").casefold()


@lru_cache(maxsize=_CACHE_SIZE)
def _known(word):
    checker = _get_checker()
    if checker is None:
        return False
    with _LOOKUP_LOCK:
        return _recognized(checker, word)


@lru_cache(maxsize=_CACHE_SIZE)
def _suggestions(word):
    # Bound input length and returned results; retain Hunspell's own ranking.
    if len(word) > 32:
        return ()
    checker = _get_checker()
    if checker is None:
        return ()
    with _LOOKUP_LOCK:
        return _ranked_corrections(checker, word)


def _technical_spans(node, source):
    """Shield whole technical runs even when syntax split them across tokens."""
    text = node.span.extract(source)
    spans = []
    quotes = {q.start - node.span.start: q.end - node.span.start for q in node.quoted_spans}

    def quoted(offset):
        return any(start <= offset < end for start, end in quotes.items())

    def balanced_end(start, opening, closing):
        depth, end = 1, start + 1
        while end < len(text) and depth:
            if end in quotes:
                end = quotes[end]
                continue
            depth += (text[end] == opening) - (text[end] == closing)
            end += 1
        return end

    for run in _RUN.finditer(text):
        value = run.group()
        if (any(c.isdigit() or c in '_@/\\=<>[]{}|~$*' for c in value)
                or _CAMEL.search(value) or _DOTTED.search(value)
                or value.startswith(('.', '--'))):
            spans.append(SourceSpan(node.span.start + run.start(), node.span.start + run.end()))
    for assignment in _ASSIGNMENT.finditer(text):
        start = node.span.start + assignment.start()
        if not quoted(assignment.start()):
            spans.append(SourceSpan(start, node.span.end))
            break
    # Malformed bracket/code groups may not receive a complete typed symbol.
    # Their contents are still not confidently ordinary prose.
    group_end = 0
    for opening in re.finditer(r'[\[{<]', text):
        if opening.start() < group_end or quoted(opening.start()):
            continue
        closing = {'[': ']', '{': '}', '<': '>'}[opening.group()]
        group_end = balanced_end(opening.start(), opening.group(), closing)
        spans.append(SourceSpan(node.span.start + opening.start(), node.span.start + group_end))
    # Calls with spaced arguments are code, unlike parenthesized prose.
    call_end = 0
    for call in _CALL.finditer(text):
        if call.start() < call_end or quoted(call.start()):
            continue
        end = balanced_end(call.end() - 1, '(', ')')
        spans.append(SourceSpan(node.span.start + call.start(), node.span.start + end))
        call_end = end
    merged = []
    for span in sorted(spans, key=lambda s: s.start):
        if merged and span.start <= merged[-1].end:
            merged[-1] = SourceSpan(merged[-1].start, max(span.end, merged[-1].end))
        else:
            merged.append(span)
    return merged


def ordinary_words(tree, source):
    """Yield exact words only inside text tokens, never reparse lines as prose."""
    from .semantics import uncertain_symbol_bodies
    uncertain = uncertain_symbol_bodies(tree)
    protected = []
    for node in tree.nodes:
        inherited = any(protected[link] for link in (node.parent, node.section)
                        if link is not None and link < node.id)
        blocked = inherited or node.recovered or node.indent is None or uncertain[node.id]
        protected.append(blocked)
        if 'literal' in node.kind or node.kind.startswith('markdown_fence_'):
            continue
        meaningful = [t for t in node.tokens if t.kind not in ('indentation', 'whitespace', 'newline')]
        if blocked:
            continue
        shields = _technical_spans(node, source)
        shield_index = 0
        for token in node.tokens:
            if token.kind != 'text':
                continue
            for match in _WORD.finditer(token.text):
                span = SourceSpan(token.span.start + match.start(), token.span.start + match.end())
                while shield_index < len(shields) and shields[shield_index].end <= span.start:
                    shield_index += 1
                if (len(match.group()) <= 128
                        and not (shield_index < len(shields) and shields[shield_index].start < span.end)):
                    yield node.id, span


def suggestions_for_word(original):
    """Explicit correction request, never called by diagnostic analysis.

    Hosts must invoke this only in response to the editor-word right-click
    interaction. Recognition and diagnostic verification do not need it.
    """
    if _get_checker() is None:
        return ()
    suggestions = _suggestions(_normalize(original))
    if original.isupper():
        return tuple(s.upper() for s in suggestions)
    if original.istitle():
        return tuple(s.capitalize() for s in suggestions)
    return suggestions


def spelling_spans(tree, source, *, enabled=True, vocabulary=()):
    """Reconstruct exact, independently admissible spelling evidence and messages."""
    if not enabled:
        return {}
    result = {}
    # Accepted vocabulary is independent of backend availability, while the
    # same built-in terms are also registered in native Hunspell for suggestions.
    accepted = TECHNICAL_WORDS | _vocabulary_words(vocabulary)
    for node_id, span in ordinary_words(tree, source):
        original = span.extract(source)
        word = _normalize(original)
        if _in_vocabulary(word, accepted):
            continue
        if _get_checker() is None:
            return {('AG-SPELLCHECK-UNAVAILABLE', node_id, span): SPELLING_MESSAGES['AG-SPELLCHECK-UNAVAILABLE']}
        # Hunspell encodes capitalization rules (for example Unicode). Keep
        # case for dictionary lookup; vocabulary matching remains casefolded.
        if _known(unicodedata.normalize('NFC', original).replace('’', "'")):
            continue
        result[('AG-SPELLING', node_id, span)] = f'Possible English misspelling: {original}'
    return result
