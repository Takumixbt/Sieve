"""`sieve vault ...`: one Obsidian vault for the knowledge base and every engagement."""
from __future__ import annotations

import argparse
import os
from typing import Any

from . import vault
from .config import load_config
from .state import Engagement


def _root(cfg: Any) -> str:
    return vault.vault_root(cfg)


def cmd_init(args: argparse.Namespace) -> int:
    eng = Engagement.find()
    cfg = load_config(eng.root if eng else None)
    root = _root(cfg)
    vault.init_root(root)
    kb = cfg.path("kb.vault")
    n_vec, n_cards = vault.init_kb_vault(kb)
    print(f"Sieve vault ready: {root}\n  knowledge base: {kb} ({n_vec} vector note(s), {n_cards} card(s) linked)\n"
          f"  engagements:    {os.path.join(root, 'Engagements')}\n"
          "Open that folder in Obsidian (Open folder as vault). Start at Sieve.md.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    cfg = load_config(eng.root)
    if args.local or args.out:
        out = args.out or eng.path("vault")
        counts = vault.export_engagement(eng, out)
        where = out
    else:
        root = _root(cfg)
        vault.init_root(root)
        kb = cfg.path("kb.vault")
        os.makedirs(kb, exist_ok=True)
        out = os.path.join(root, "Engagements", vault.namespace(eng))
        counts = vault.export_engagement(eng, out, kb_root=kb, root=root)
        where = out
    print(f"engagement notes: {where}\n  " + ", ".join(f"{v} {k}" for k, v in counts.items()) +
          f"\nOpen the vault in Obsidian; start at {eng.load()['id']}.md" +
          (f" ({counts['unprobed_invariants']} invariant(s) still unprobed: filter the graph by tag #unprobed)"
           if counts.get("unprobed_invariants") else "."))
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    eng = Engagement.find()
    print(_root(load_config(eng.root if eng else None)))
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("vault", help="the Sieve Obsidian vault: knowledge base and every engagement in one graph")
    vs = p.add_subparsers(dest="vcmd", required=True)

    q = vs.add_parser("init", help="create the vault (root note, graph colours), scaffold KB/, link every card")
    q.set_defaults(func=cmd_init)

    q = vs.add_parser("export", help="write this engagement into the vault as linked notes (Engagements/<target>/)")
    q.add_argument("--out", help="write somewhere else instead")
    q.add_argument("--local", action="store_true", help="write to .sieve/vault/ inside the target (confidential engagement)")
    q.set_defaults(func=cmd_export)

    q = vs.add_parser("path", help="print where the vault is")
    q.set_defaults(func=cmd_path)
