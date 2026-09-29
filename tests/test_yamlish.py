import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from sieve import yamlish as Y  # noqa: E402

try:
    import yaml as pyyaml  # type: ignore
except ImportError:  # pragma: no cover
    pyyaml = None

DOC = """
# comment
version: 1
name: "quoted: value"
url: https://example.com/a?b=c#frag   # trailing comment
single: 'it''s'
flag: true
nothing: null
ratio: 0.75
neg: -3
version_str: 1.0.0
flow_list: [a, "b, c", 3, true]
flow_map: {x: 1, y: [1, 2], z: {k: v}}
empty_map: {}
empty_list: []
nested:
  a:
    b: deep
  list:
    - one
    - two: 2
      three: 3
    - [x, y]
    -
      inner: 1
seq_same_indent:
- p
- q
literal: |
  line one
    indented
  line three
folded: >
  folded text
  continues here

  new paragraph
strip: |-
  no trailing newline
"""


class YamlishTests(unittest.TestCase):
    def test_parse_document(self):
        d = Y.loads(DOC)
        self.assertEqual(d["version"], 1)
        self.assertEqual(d["name"], "quoted: value")
        self.assertEqual(d["url"], "https://example.com/a?b=c#frag")
        self.assertEqual(d["single"], "it's")
        self.assertIs(d["flag"], True)
        self.assertIsNone(d["nothing"])
        self.assertEqual(d["ratio"], 0.75)
        self.assertEqual(d["neg"], -3)
        self.assertEqual(d["version_str"], "1.0.0")
        self.assertEqual(d["flow_list"], ["a", "b, c", 3, True])
        self.assertEqual(d["flow_map"], {"x": 1, "y": [1, 2], "z": {"k": "v"}})
        self.assertEqual(d["empty_map"], {})
        self.assertEqual(d["empty_list"], [])
        self.assertEqual(d["nested"]["a"]["b"], "deep")
        self.assertEqual(d["nested"]["list"], ["one", {"two": 2, "three": 3}, ["x", "y"], {"inner": 1}])
        self.assertEqual(d["seq_same_indent"], ["p", "q"])
        self.assertEqual(d["literal"], "line one\n  indented\nline three\n")
        self.assertEqual(d["folded"], "folded text continues here\nnew paragraph\n")
        self.assertEqual(d["strip"], "no trailing newline")

    @unittest.skipIf(pyyaml is None, "PyYAML not installed")
    def test_matches_pyyaml_on_document(self):
        self.assertEqual(Y.loads(DOC), pyyaml.safe_load(DOC))

    def test_duplicate_key_rejected(self):
        with self.assertRaises(Y.YamlError):
            Y.loads("a: 1\na: 2\n")

    def test_tabs_rejected(self):
        with self.assertRaises(Y.YamlError):
            Y.loads("a:\n\tb: 1\n")

    def test_anchors_rejected(self):
        with self.assertRaises(Y.YamlError):
            Y.loads("a: &x 1\n")

    def test_roundtrip_random(self):
        rnd = random.Random(1337)
        words = ["alpha", "b: c", "x #y", "  pad", "true", "null", "12", "3.5", "-", "a,b", "[z]",
                 "{q}", "multi\nline", 'quote"d', "it's", "", "tab\tchar", "üñí", "1.0.0", "~", "@at"]

        def scalar():
            return rnd.choice([None, True, False, rnd.randint(-99, 99), round(rnd.random(), 3),
                               rnd.choice(words)])

        def make(depth):
            r = rnd.random()
            if depth > 3 or r < 0.35:
                return scalar()
            if r < 0.7:
                return {rnd.choice(["k", "key two", "a:b", "n", "z"]) + str(i): make(depth + 1)
                        for i in range(rnd.randint(0, 4))}
            return [make(depth + 1) for _ in range(rnd.randint(0, 4))]

        for n in range(400):
            obj = {"root": make(0)}
            text = Y.dumps(obj)
            self.assertEqual(Y.loads(text), obj, msg=f"case {n}\n{text}")
            if pyyaml is not None:
                self.assertEqual(pyyaml.safe_load(text), obj, msg=f"pyyaml case {n}\n{text}")

    def test_frontmatter(self):
        meta = {"id": "KB-1", "tags": ["a", "b"], "confidence": 80, "title": "x: y"}
        text = Y.join_frontmatter(meta, "# Body\n\ntext")
        m2, body = Y.split_frontmatter(text)
        self.assertEqual(m2, meta)
        self.assertTrue(body.startswith("# Body"))
        self.assertEqual(Y.split_frontmatter("no front matter"), ({}, "no front matter"))


if __name__ == "__main__":
    unittest.main()
