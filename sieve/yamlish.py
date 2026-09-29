"""A dependency-free YAML subset: enough for sieve.yaml, pack.yaml and card frontmatter.

Supported: block maps and sequences, flow maps/sequences (single line), quoted and plain
scalars (null/bool/int/float/str), comments, literal (|) and folded (>) block scalars.
Not supported (raises YamlError): anchors, aliases, tags, multi-document streams,
multi-line flow collections. Output of `dumps` is standard YAML that PyYAML and Obsidian read.

Behaviour is identical whether or not PyYAML is installed: we never delegate to it.
"""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple


class YamlError(ValueError):
    pass


_INT = re.compile(r"[-+]?(0|[1-9][0-9]*)\Z")
_FLOAT = re.compile(r"[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?\Z")
_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "\\": "\\", "/": "/", "0": "\0"}


def _typed(s: str) -> Any:
    if s in ("", "~") or s.lower() == "null":
        return None
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if _INT.match(s):
        return int(s)
    if _FLOAT.match(s) and ("." in s or "e" in s.lower()):
        return float(s)
    return s


def _unquote_double(s: str, pos: int) -> Tuple[str, int]:
    """s[pos] == '"'. Returns (value, index after closing quote)."""
    out: List[str] = []
    i = pos + 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 1
            if i >= len(s):
                raise YamlError("dangling escape in double-quoted string")
            e = s[i]
            if e == "u":
                out.append(chr(int(s[i + 1:i + 5], 16)))
                i += 5
                continue
            if e == "x":
                out.append(chr(int(s[i + 1:i + 3], 16)))
                i += 3
                continue
            out.append(_ESC.get(e, e))
            i += 1
            continue
        if c == '"':
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise YamlError("unterminated double-quoted string")


def _unquote_single(s: str, pos: int) -> Tuple[str, int]:
    out: List[str] = []
    i = pos + 1
    while i < len(s):
        c = s[i]
        if c == "'":
            if i + 1 < len(s) and s[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise YamlError("unterminated single-quoted string")


def _strip_comment(s: str) -> str:
    """Remove a trailing ` # comment`, respecting quotes."""
    q: Optional[str] = None
    i = 0
    while i < len(s):
        c = s[i]
        if q:
            if q == '"' and c == "\\":
                i += 2
                continue
            if c == q:
                if q == "'" and i + 1 < len(s) and s[i + 1] == "'":
                    i += 2
                    continue
                q = None
        else:
            if c in "\"'" and (i == 0 or s[i - 1] in " \t[{,:"):
                q = c
            elif c == "#" and (i == 0 or s[i - 1] in " \t"):
                return s[:i].rstrip()
        i += 1
    return s.rstrip()


# ---------------------------------------------------------------- flow collections

class _Flow:
    def __init__(self, s: str):
        self.s = s
        self.i = 0

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def value(self, stop: str) -> Any:
        self.ws()
        if self.i >= len(self.s):
            raise YamlError("unexpected end of flow collection")
        c = self.s[self.i]
        if c == "[":
            return self.seq()
        if c == "{":
            return self.map()
        if c == '"':
            v, self.i = _unquote_double(self.s, self.i)
            return v
        if c == "'":
            v, self.i = _unquote_single(self.s, self.i)
            return v
        j = self.i
        while j < len(self.s) and self.s[j] not in stop:
            if self.s[j] == ":" and (j + 1 >= len(self.s) or self.s[j + 1] in " \t,]}"):
                break
            j += 1
        raw = self.s[self.i:j].strip()
        self.i = j
        return _typed(raw)

    def seq(self) -> List[Any]:
        assert self.s[self.i] == "["
        self.i += 1
        out: List[Any] = []
        self.ws()
        if self.s[self.i:self.i + 1] == "]":
            self.i += 1
            return out
        while True:
            out.append(self.value(",]"))
            self.ws()
            c = self.s[self.i:self.i + 1]
            if c == ",":
                self.i += 1
                self.ws()
                if self.s[self.i:self.i + 1] == "]":
                    self.i += 1
                    return out
                continue
            if c == "]":
                self.i += 1
                return out
            raise YamlError(f"expected ',' or ']' in flow sequence near {self.s[self.i:self.i + 12]!r}")

    def map(self) -> dict:
        assert self.s[self.i] == "{"
        self.i += 1
        out: dict = {}
        self.ws()
        if self.s[self.i:self.i + 1] == "}":
            self.i += 1
            return out
        while True:
            self.ws()
            k = self.value(":,}")
            self.ws()
            if self.s[self.i:self.i + 1] != ":":
                raise YamlError("expected ':' in flow mapping")
            self.i += 1
            v = self.value(",}")
            out[k if isinstance(k, str) else str(k)] = v
            self.ws()
            c = self.s[self.i:self.i + 1]
            if c == ",":
                self.i += 1
                self.ws()
                if self.s[self.i:self.i + 1] == "}":
                    self.i += 1
                    return out
                continue
            if c == "}":
                self.i += 1
                return out
            raise YamlError("expected ',' or '}' in flow mapping")


def _parse_inline(s: str) -> Any:
    s = _strip_comment(s.strip())
    if not s:
        return None
    if s[0] in "[{":
        f = _Flow(s)
        v = f.value("")
        f.ws()
        if f.i != len(s):
            raise YamlError(f"trailing characters after flow collection: {s[f.i:]!r}")
        return v
    if s[0] == '"':
        v, j = _unquote_double(s, 0)
        if s[j:].strip():
            raise YamlError(f"trailing characters after quoted string: {s[j:]!r}")
        return v
    if s[0] == "'":
        v, j = _unquote_single(s, 0)
        if s[j:].strip():
            raise YamlError(f"trailing characters after quoted string: {s[j:]!r}")
        return v
    if s[0] in "&*!":
        raise YamlError("anchors/aliases/tags are not supported")
    return _typed(s)


def _split_key(content: str) -> Optional[Tuple[str, str]]:
    """Split `key: rest` (first unquoted `:` followed by space/EOL). None if not a mapping line."""
    if not content:
        return None
    if content[0] in "\"'":
        try:
            if content[0] == '"':
                k, j = _unquote_double(content, 0)
            else:
                k, j = _unquote_single(content, 0)
        except YamlError:
            return None
        rest = content[j:].lstrip()
        if rest.startswith(":") and (len(rest) == 1 or rest[1] in " \t"):
            return k, rest[1:].strip()
        return None
    if content[0] in "[{":
        return None
    i = 0
    while i < len(content):
        if content[i] == ":" and (i + 1 == len(content) or content[i + 1] in " \t"):
            return content[:i].strip(), content[i + 1:].strip()
        i += 1
    return None


# ---------------------------------------------------------------- block parser

class _Parser:
    def __init__(self, text: str):
        self.raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.i = 0

    @staticmethod
    def _indent(line: str) -> int:
        n = 0
        for ch in line:
            if ch == " ":
                n += 1
            elif ch == "\t":
                raise YamlError("tabs are not allowed for indentation")
            else:
                break
        return n

    def _skip(self) -> None:
        while self.i < len(self.raw):
            st = self.raw[self.i].strip()
            if st == "" or st.startswith("#"):
                self.i += 1
            else:
                break

    def _peek(self) -> Optional[Tuple[int, str]]:
        self._skip()
        if self.i >= len(self.raw):
            return None
        line = self.raw[self.i]
        return self._indent(line), line.strip()

    def parse(self) -> Any:
        pk = self._peek()
        if pk is None:
            return None
        if pk[1] == "---":
            self.i += 1
            pk = self._peek()
            if pk is None:
                return None
        v = self.block(pk[0])
        self._skip()
        if self.i < len(self.raw):
            raise YamlError(f"line {self.i + 1}: unexpected content {self.raw[self.i].strip()!r}")
        return v

    def block(self, indent: int) -> Any:
        pk = self._peek()
        if pk is None:
            return None
        ind, content = pk
        if ind < indent:
            return None
        if content == "-" or content.startswith("- "):
            return self.seq(ind)
        if _split_key(_strip_comment(content)) is not None:
            return self.map(ind)
        self.i += 1
        return _parse_inline(content)

    def child(self, parent_indent: int) -> Any:
        """Parse the nested block under a `key:` / `-` line, or None if there is none."""
        pk = self._peek()
        if pk is None:
            return None
        ind, content = pk
        if ind > parent_indent:
            return self.block(ind)
        # `key:` followed by a sequence at the same indent is legal YAML.
        if ind == parent_indent and (content == "-" or content.startswith("- ")):
            return self.seq(ind)
        return None

    def map(self, indent: int) -> dict:
        out: dict = {}
        while True:
            pk = self._peek()
            if pk is None or pk[0] != indent:
                if pk is not None and pk[0] > indent:
                    raise YamlError(f"line {self.i + 1}: bad indentation")
                break
            content = _strip_comment(pk[1])
            kv = _split_key(content)
            if kv is None:
                break
            key, rest = kv
            if key in out:
                raise YamlError(f"line {self.i + 1}: duplicate key {key!r}")
            self.i += 1
            if rest == "":
                out[key] = self.child(indent)
            elif rest[0] in "|>":
                out[key] = self.block_scalar(indent, rest)
            else:
                out[key] = _parse_inline(rest)
        return out

    def seq(self, indent: int) -> list:
        out: list = []
        while True:
            pk = self._peek()
            if pk is None or pk[0] != indent:
                if pk is not None and pk[0] > indent:
                    raise YamlError(f"line {self.i + 1}: bad indentation in sequence")
                break
            content = pk[1]
            if not (content == "-" or content.startswith("- ")):
                break
            after = content[1:]
            spaces = len(after) - len(after.lstrip(" "))
            rest = after.lstrip(" ")
            rest_nc = _strip_comment(rest)
            if rest_nc == "":
                self.i += 1
                out.append(self.child(indent))
            elif rest_nc[0] in "|>" and len(rest_nc) <= 3:
                self.i += 1
                out.append(self.block_scalar(indent, rest_nc))
            elif _split_key(rest_nc) is not None:
                col = indent + 1 + spaces
                self.raw[self.i] = " " * col + rest
                out.append(self.map(col))
            else:
                self.i += 1
                out.append(_parse_inline(rest))
        return out

    def block_scalar(self, parent_indent: int, header: str) -> str:
        style = header[0]
        chomp = "clip"
        if "-" in header[1:]:
            chomp = "strip"
        elif "+" in header[1:]:
            chomp = "keep"
        lines: List[str] = []
        block_indent: Optional[int] = None
        while self.i < len(self.raw):
            line = self.raw[self.i]
            if line.strip() == "":
                lines.append("")
                self.i += 1
                continue
            ind = self._indent(line)
            if block_indent is None:
                if ind <= parent_indent:
                    break
                block_indent = ind
            if ind < block_indent:
                break
            lines.append(line[block_indent:])
            self.i += 1
        while lines and lines[-1] == "":
            lines.pop()
        if style == "|":
            text = "\n".join(lines)
        else:
            parts: List[str] = []
            for ln in lines:
                if ln == "":
                    parts.append("\n")
                elif parts and not parts[-1].endswith("\n"):
                    parts.append(" " + ln)
                else:
                    parts.append(ln)
            text = "".join(parts)
        if chomp == "strip" or not text:
            return text
        return text + "\n"


def loads(text: str) -> Any:
    return _Parser(text).parse()


def load_file(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read())


# ---------------------------------------------------------------- dumper

_NEEDS_QUOTE_START = set("-?:,[]{}#&*!|>'\"%@`")


def _scalar(v: Any) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    needs = (
        s == ""
        or s != s.strip()
        or s[0] in _NEEDS_QUOTE_START
        or ": " in s
        or " #" in s
        or s.endswith(":")
        or "\n" in s
        or "\t" in s
        or "\r" in s
        or not isinstance(_typed(s), str)
        or s in ("---", "...")
    )
    return json.dumps(s, ensure_ascii=False) if needs else s


def _is_scalar(v: Any) -> bool:
    return not isinstance(v, (dict, list, tuple))


def _flow(v: Any) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_scalar(k)}: {_flow(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    s = _scalar(v)
    if isinstance(v, str) and any(c in s for c in ",[]{}") and not s.startswith('"'):
        return json.dumps(s, ensure_ascii=False)
    return s


def _dump(v: Any, indent: int) -> List[str]:
    pad = " " * indent
    if isinstance(v, dict):
        if not v:
            return [pad + "{}"]
        out: List[str] = []
        for k, x in v.items():
            ks = _scalar(k)
            if isinstance(x, dict):
                if not x:
                    out.append(f"{pad}{ks}: {{}}")
                else:
                    out.append(f"{pad}{ks}:")
                    out.extend(_dump(x, indent + 2))
            elif isinstance(x, (list, tuple)):
                if not x:
                    out.append(f"{pad}{ks}: []")
                elif all(_is_scalar(i) for i in x) and len(_flow(x)) <= 88:
                    out.append(f"{pad}{ks}: {_flow(x)}")
                else:
                    out.append(f"{pad}{ks}:")
                    out.extend(_dump(list(x), indent + 2))
            else:
                out.append(f"{pad}{ks}: {_scalar(x)}")
        return out
    if isinstance(v, (list, tuple)):
        if not v:
            return [pad + "[]"]
        out = []
        for x in v:
            if isinstance(x, dict) and x:
                sub = _dump(x, indent + 2)
                sub[0] = pad + "- " + sub[0][indent + 2:]
                out.extend(sub)
            elif isinstance(x, (list, tuple)) and x and all(_is_scalar(i) for i in x):
                out.append(f"{pad}- {_flow(x)}")
            elif isinstance(x, (list, tuple)) and x:
                out.append(pad + "-")
                out.extend(_dump(list(x), indent + 2))
            elif isinstance(x, dict):
                out.append(f"{pad}- {{}}")
            elif isinstance(x, (list, tuple)):
                out.append(f"{pad}- []")
            else:
                out.append(f"{pad}- {_scalar(x)}")
        return out
    return [pad + _scalar(v)]


def dumps(obj: Any) -> str:
    return "\n".join(_dump(obj, 0)) + "\n"


# ---------------------------------------------------------------- frontmatter

def split_frontmatter(text: str) -> Tuple[dict, str]:
    """`---\\nyaml\\n---\\nbody` -> (meta, body). No frontmatter -> ({}, text)."""
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}, text
    for j in range(1, len(lines)):
        if lines[j].strip() == "---":
            meta = loads("\n".join(lines[1:j])) or {}
            if not isinstance(meta, dict):
                raise YamlError("frontmatter must be a mapping")
            body = "\n".join(lines[j + 1:])
            return meta, body.lstrip("\n")
    return {}, text


def join_frontmatter(meta: dict, body: str) -> str:
    return "---\n" + dumps(meta) + "---\n\n" + body.lstrip("\n")
