"""`sieve vault ...` — Obsidian wiring for the knowledge base and for an engagement."""
from __future__ import annotations

import argparse
import os
from typing import Any

from . import kb_store, vault
from .config import load_config
from .state import Engagement


def cmd_init(args: argparse.Namespace) -> int:
    eng = Engagement.find()
    cfg = load_config(eng.root if eng else None)
    root = cfg.path("kb.vault")
    n_vec, n_cards = vault.init_kb_vault(root)
    print(f"knowledge vault ready: {root}\n  {n_vec} vector note(s), {n_cards} card(s) linked\n"
          "Open that folder in Obsidian (Open folder as vault) — the graph clusters cards by class and domain.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    eng = Engagement.require()
    out = args.out or eng.path("vault")
    counts = vault.export_engagement(eng, out)
    cfg = load_config(eng.root)
    kb_root = cfg.path("kb.vault")
    if os.path.isdir(kb_root):
        vault.write_engagement_stub(kb_root, eng, counts)
    print(f"engagement vault: {out}\n  " + ", ".join(f"{v} {k}" for k, v in counts.items()) +
          f"\nOpen it in Obsidian; start at {eng.load()['id']}.md.")
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("vault", help="Obsidian wiring: knowledge vault and engagement graph")
    vs = p.add_subparsers(dest="vcmd", required=True)

    q = vs.add_parser("init", help="scaffold ~/.sieve/kb as an Obsidian vault and link every card")
    q.set_defaults(func=cmd_init)

    q = vs.add_parser("export", help="write this engagement as a linked note graph (default .sieve/vault/)")
    q.add_argument("--out")
    q.set_defaults(func=cmd_export)
