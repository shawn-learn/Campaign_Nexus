"""A small, safe condition DSL for story edges (docs/11 §14.4, FR-4.3).

Predicates over campaign state — flags, quest and NPC status — parsed to a closed AST and
evaluated by a tree-walker. **Never ``eval``**: the only callables are the whitelisted
accessors ``flag(...)``, ``quest(...).status``, ``npc(...).status``/``.location``.

Grammar (recursive descent):

    expr        := or_expr
    or_expr     := and_expr ('or' and_expr)*
    and_expr    := not_expr ('and' not_expr)*
    not_expr    := 'not' not_expr | comparison
    comparison  := value (('==' | '!=' | '<' | '<=' | '>' | '>=') value)?
    value       := literal | accessor | '(' expr ')'
    literal     := NUMBER | STRING | 'true' | 'false' | 'null'
    accessor    := 'flag' '(' STRING ')'
                 | 'quest' '(' STRING ')' '.' 'status'
                 | 'npc' '(' STRING ')' '.' ('status' | 'location')

An empty condition is always true (an unconditional edge).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

_TOKEN = re.compile(
    r"""\s*(?:
        (?P<num>-?\d+(?:\.\d+)?)
      | (?P<str>'[^']*'|"[^"]*")
      | (?P<op><=|>=|==|!=|<|>)
      | (?P<punct>[().,])
      | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    )""",
    re.VERBOSE,
)
_KEYWORDS = {"and", "or", "not", "true", "false", "null"}
_ACCESSORS = {"flag", "quest", "npc"}


class ConditionError(ValueError):
    """A condition that does not parse — surfaced to the GM at save time."""


class StoryContext(Protocol):
    """What the evaluator may read. Implemented by the story service against the DB."""

    def flag(self, key: str) -> Any: ...
    def quest_status(self, quest_id: str) -> str | None: ...
    def npc_status(self, npc_id: str) -> str | None: ...
    def npc_location(self, npc_id: str) -> str | None: ...


# --------------------------------------------------------------------------- #
# Tokenizer
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Tok:
    kind: str
    value: str


def _tokenize(src: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    pos = 0
    while pos < len(src):
        if src[pos].isspace():
            pos += 1
            continue
        match = _TOKEN.match(src, pos)
        if match is None or match.end() == pos:
            raise ConditionError(f"unexpected character at {pos!r}: {src[pos:pos + 8]!r}")
        pos = match.end()
        if match.lastgroup == "num":
            tokens.append(_Tok("num", match.group("num")))
        elif match.lastgroup == "str":
            tokens.append(_Tok("str", match.group("str")[1:-1]))
        elif match.lastgroup == "op":
            tokens.append(_Tok("op", match.group("op")))
        elif match.lastgroup == "punct":
            tokens.append(_Tok("punct", match.group("punct")))
        else:
            name = match.group("name")
            tokens.append(_Tok("kw" if name in _KEYWORDS else "name", name))
    return tokens


# --------------------------------------------------------------------------- #
# AST — plain tuples: (op, ...). Kept data-only so it is trivially serializable/testable.
# --------------------------------------------------------------------------- #
Ast = tuple[Any, ...]


class _Parser:
    def __init__(self, tokens: list[_Tok]) -> None:
        self._toks = tokens
        self._i = 0

    def _peek(self) -> _Tok | None:
        return self._toks[self._i] if self._i < len(self._toks) else None

    def _next(self) -> _Tok:
        tok = self._peek()
        if tok is None:
            raise ConditionError("unexpected end of condition")
        self._i += 1
        return tok

    def _expect(self, kind: str, value: str | None = None) -> _Tok:
        tok = self._next()
        if tok.kind != kind or (value is not None and tok.value != value):
            raise ConditionError(f"expected {value or kind}, got {tok.value!r}")
        return tok

    def parse(self) -> Ast:
        node = self._or()
        if self._peek() is not None:
            raise ConditionError(f"trailing tokens: {self._peek().value!r}")  # type: ignore[union-attr]
        return node

    def _or(self) -> Ast:
        node = self._and()
        while (t := self._peek()) and t.kind == "kw" and t.value == "or":
            self._next()
            node = ("or", node, self._and())
        return node

    def _and(self) -> Ast:
        node = self._not()
        while (t := self._peek()) and t.kind == "kw" and t.value == "and":
            self._next()
            node = ("and", node, self._not())
        return node

    def _not(self) -> Ast:
        t = self._peek()
        if t and t.kind == "kw" and t.value == "not":
            self._next()
            return ("not", self._not())
        return self._comparison()

    def _comparison(self) -> Ast:
        left = self._value()
        t = self._peek()
        if t and t.kind == "op":
            self._next()
            return ("cmp", t.value, left, self._value())
        return left

    def _value(self) -> Ast:
        tok = self._next()
        if tok.kind == "num":
            return ("lit", float(tok.value) if "." in tok.value else int(tok.value))
        if tok.kind == "str":
            return ("lit", tok.value)
        if tok.kind == "kw" and tok.value in ("true", "false", "null"):
            return ("lit", {"true": True, "false": False, "null": None}[tok.value])
        if tok.kind == "punct" and tok.value == "(":
            node = self._or()
            self._expect("punct", ")")
            return node
        if tok.kind == "name" and tok.value in _ACCESSORS:
            return self._accessor(tok.value)
        raise ConditionError(f"unexpected token {tok.value!r}")

    def _accessor(self, name: str) -> Ast:
        self._expect("punct", "(")
        arg = self._expect("str").value
        self._expect("punct", ")")
        if name == "flag":
            return ("flag", arg)
        # quest(...) / npc(...) require a '.field'
        self._expect("punct", ".")
        field = self._expect("name").value
        if name == "quest":
            if field != "status":
                raise ConditionError(f"quest has no field '{field}' (only .status)")
            return ("quest_status", arg)
        if field not in ("status", "location"):
            raise ConditionError(f"npc has no field '{field}' (only .status/.location)")
        return ("npc_status" if field == "status" else "npc_location", arg)


def parse(source: str) -> Ast | None:
    """Parse to an AST. ``None`` for a blank condition (always-true edge)."""
    src = (source or "").strip()
    if not src:
        return None
    return _Parser(_tokenize(src)).parse()


def validate(source: str) -> str | None:
    """Return an error message if the condition doesn't parse, else ``None``."""
    try:
        parse(source)
    except ConditionError as exc:
        return str(exc)
    return None


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
_CMP = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def _eval(node: Ast, ctx: StoryContext) -> Any:
    op = node[0]
    if op == "lit":
        return node[1]
    if op == "flag":
        return ctx.flag(node[1])
    if op == "quest_status":
        return ctx.quest_status(node[1])
    if op == "npc_status":
        return ctx.npc_status(node[1])
    if op == "npc_location":
        return ctx.npc_location(node[1])
    if op == "not":
        return not _truthy(_eval(node[1], ctx))
    if op == "and":
        return _truthy(_eval(node[1], ctx)) and _truthy(_eval(node[2], ctx))
    if op == "or":
        return _truthy(_eval(node[1], ctx)) or _truthy(_eval(node[2], ctx))
    if op == "cmp":
        left, right = _eval(node[2], ctx), _eval(node[3], ctx)
        try:
            return _CMP[node[1]](left, right)
        except TypeError:
            return False  # comparing incomparable types → simply false, never an error
    raise ConditionError(f"unknown node {op!r}")  # pragma: no cover


def _truthy(value: Any) -> bool:
    return bool(value)


def evaluate(source: str, ctx: StoryContext) -> bool:
    """Evaluate a condition against campaign state. A blank condition is always true."""
    ast = parse(source)
    if ast is None:
        return True
    return _truthy(_eval(ast, ctx))
