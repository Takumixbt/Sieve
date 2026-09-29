import json
import os
import unittest

from tests.helpers import ROOT, make_engagement, sieve, tmpdir  # noqa: F401

from sieve import frontier, hook
from sieve.config import load_config


class FrontierTests(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.d = self._t.__enter__()
        self.eng = make_engagement(self.d)
        self.cfg = load_config(self.d)

    def tearDown(self):
        self._t.__exit__(None, None, None)

    def test_add_is_idempotent(self):
        a = frontier.add(self.eng, "entry", "Vault.withdraw", pack="web3")
        b = frontier.add(self.eng, "entry", "Vault.withdraw", pack="web3")
        self.assertEqual(a, b)
        self.assertEqual(len(frontier.load(self.eng)), 1)

    def test_clean_requires_inversion_and_two_attempts(self):
        rid = frontier.add(self.eng, "entry", "Vault.deposit")
        with self.assertRaises(SystemExit) as cm:
            frontier.done_clean(self.eng, rid, "guard holds because of X", self.cfg)
        self.assertIn("only 0 attempt", str(cm.exception))
        frontier.attempt(self.eng, rid, "input", "tried zero and max amounts on deposit")
        frontier.attempt(self.eng, rid, "sibling", "compared with mint(); same share math")
        with self.assertRaises(SystemExit) as cm:
            frontier.done_clean(self.eng, rid, "guard holds because of X", self.cfg)
        self.assertIn("inversion", str(cm.exception))
        frontier.attempt(self.eng, rid, "inversion", "made totalAssets lie via donation; rounding down blocks it")
        frontier.done_clean(self.eng, rid, "share math rounds down; donation cannot zero shares", self.cfg)
        self.assertEqual(frontier.load(self.eng)[0]["status"], "done")

    def test_dead_needs_attempts_on_distinct_rungs(self):
        rid = frontier.add(self.eng, "hypothesis", "H1")
        with self.assertRaises(SystemExit) as cm:
            frontier.dead(self.eng, rid, [("input", "tried the obvious thing on the handler")], self.cfg)
        self.assertIn("not dead yet", str(cm.exception))
        # three attempts, but all on one rung: still refused
        with self.assertRaises(SystemExit):
            frontier.dead(self.eng, rid, [("input", "second variation of the input here"),
                                          ("input", "third variation of the input here")], self.cfg)
        frontier.dead(self.eng, rid, [("precedent", "no matching KB precedent for this shape"),
                                      ("layer", "checked the decoder layer separately")], self.cfg)
        row = frontier.load(self.eng)[0]
        self.assertEqual(row["status"], "dead")
        self.assertGreaterEqual(int(row["attempts"]), 5)

    def test_attempt_needs_real_note_and_known_rung(self):
        rid = frontier.add(self.eng, "entry", "x")
        with self.assertRaises(SystemExit):
            frontier.attempt(self.eng, rid, "input", "meh")
        with self.assertRaises(SystemExit):
            frontier.attempt(self.eng, rid, "vibes", "a long enough note here")

    def test_block_reasons_are_whitelisted(self):
        rid = frontier.add(self.eng, "entry", "x")
        with self.assertRaises(SystemExit):
            frontier.block(self.eng, rid, "hard", "this looks really difficult to me")
        frontier.block(self.eng, rid, "credentials", "need a second test account token for tenant B")
        self.assertEqual(frontier.load(self.eng)[0]["status"], "blocked")

    def test_next_orders_by_priority(self):
        frontier.add(self.eng, "entry", "low", prio=1)
        frontier.add(self.eng, "entry", "high", prio=5)
        self.assertEqual(frontier.next_rows(self.eng, n=1)[0]["component"], "high")

    def test_progress_hash_changes_with_work(self):
        rid = frontier.add(self.eng, "entry", "x")
        h1 = frontier.progress_hash(self.eng)
        frontier.attempt(self.eng, rid, "input", "sent a malformed request to the handler")
        self.assertNotEqual(h1, frontier.progress_hash(self.eng))


class HookTests(unittest.TestCase):
    def setUp(self):
        self._t = tmpdir()
        self.d = self._t.__enter__()
        self.eng = make_engagement(self.d)
        frontier.add(self.eng, "entry", "Vault.withdraw", pack="web3", prio=4)

    def tearDown(self):
        self._t.__exit__(None, None, None)

    def _phase(self, name):
        self.eng.set_phase(name)

    def test_init_phase_may_stop(self):
        self.assertIsNone(hook.decide(self.eng, {"last_assistant_message": "hi"}))

    def test_blocks_with_next_step_and_rows(self):
        self._phase("hunt")
        out = hook.decide(self.eng, {"last_assistant_message": "I found nothing, done."})
        self.assertEqual(out["decision"], "block")
        self.assertIn("NEXT:", out["reason"])
        self.assertIn("Vault.withdraw", out["reason"])
        self.assertIn("Do not ask permission", out["reason"])

    def test_permission_ending_is_called_out(self):
        self._phase("hunt")
        out = hook.decide(self.eng, {"last_assistant_message": "Findings so far... Would you like me to continue?"})
        self.assertIn("asking for permission", out["reason"])

    def test_permission_detector(self):
        for s in ["Shall I proceed?", "let me know if you want more", "Do you want me to run pass 2?",
                  "I'll wait for your go-ahead", "Would you like to dig into the bridge next?"]:
            self.assertTrue(hook.permission_ending(s), s)
        for s in ["Pass 2 complete. Merging findings.", "Root cause: the guard is missing."]:
            self.assertFalse(hook.permission_ending(s), s)

    def test_stalled_agent_is_released_and_recorded(self):
        self._phase("hunt")
        outs = [hook.decide(self.eng, {"last_assistant_message": "x"}) for _ in range(6)]
        blocked = [o for o in outs if o]
        self.assertGreaterEqual(len(blocked), 1)
        self.assertLess(len(blocked), 6)  # released before the loop could run away
        st = self.eng.load()
        self.assertIn("stalled", st["halt_reason"])
        # once halted the hook never blocks again
        self.assertIsNone(hook.decide(self.eng, {"last_assistant_message": "x"}))

    def test_real_work_resets_the_stall_counter(self):
        self._phase("hunt")
        rid = frontier.load(self.eng)[0]["id"]
        for i in range(8):
            frontier.attempt(self.eng, rid, "input", f"attempt number {i} with a distinct payload")
            out = hook.decide(self.eng, {"last_assistant_message": "working"})
            self.assertIsNotNone(out, f"blocked while working (iteration {i})")
        self.assertIsNone(self.eng.load()["halt_reason"])

    def test_max_blocks_cap(self):
        self._phase("hunt")
        rid = frontier.load(self.eng)[0]["id"]
        n_blocked = 0
        for i in range(200):
            frontier.attempt(self.eng, rid, "input", f"attempt number {i} with a distinct payload")
            if hook.decide(self.eng, {}) is None:
                break
            n_blocked += 1
        self.assertEqual(n_blocked, 60)
        self.assertIn("block budget", self.eng.load()["halt_reason"])

    def test_waiting_for_agents_allows_stop_until_timeout(self):
        self._phase("hunt")

        def w(st):
            st["waiting"] = {"since": 1000.0, "agents": ["a"], "pass": 1}
        self.eng.update(w)
        self.assertIsNone(hook.decide(self.eng, {}, now=1000.0 + 60 * 10))
        out = hook.decide(self.eng, {}, now=1000.0 + 60 * 60)  # 60 min > 45 min release
        self.assertIsNotNone(out)

    def test_done_engagement_never_blocks(self):
        self._phase("hunt")

        def d(st):
            st["done"] = True
        self.eng.update(d)
        self.assertIsNone(hook.decide(self.eng, {}))

    def test_heartbeat_counts_calls(self):
        self._phase("hunt")
        hook.decide(self.eng, {})
        hook.decide(self.eng, {})
        self.assertEqual(self.eng.load()["counters"]["hook_calls"], 2)

    def test_main_stop_fails_open_on_garbage(self):
        self.assertEqual(hook.main_stop("not json {{{"), 0)
        self.assertEqual(hook.main_stop(""), 0)

    def test_hook_cli_end_to_end(self):
        self._phase("hunt")
        p = sieve("hook", "stop", cwd=self.d, input_text=json.dumps({"cwd": self.d, "last_assistant_message": "done"}))
        self.assertEqual(p.returncode, 0)
        out = json.loads(p.stdout)
        self.assertEqual(out["decision"], "block")

    def test_hook_silent_outside_engagement(self):
        with tmpdir() as other:
            p = sieve("hook", "stop", cwd=other, input_text=json.dumps({"cwd": other}))
            self.assertEqual(p.returncode, 0)
            self.assertEqual(p.stdout.strip(), "")

    def test_install_is_idempotent_and_preserves_settings(self):
        home = os.path.join(self.d, "home")
        os.makedirs(os.path.join(home, ".claude"))
        with open(os.path.join(home, ".claude", "settings.json"), "w") as fh:
            json.dump({"model": "x", "hooks": {"Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "echo hi"}]}]}}, fh)
        old = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            r1 = hook.install("user", "/opt/sieve/bin/sieve")
            r2 = hook.install("user", "/opt/sieve/bin/sieve")
        finally:
            os.environ["HOME"] = old
        self.assertIn("installed", r1)
        self.assertIn("already", r2)
        s = json.load(open(os.path.join(home, ".claude", "settings.json")))
        self.assertEqual(s["model"], "x")
        cmds = [h["command"] for e in s["hooks"]["Stop"] for h in e["hooks"]]
        self.assertEqual(cmds.count("/opt/sieve/bin/sieve hook stop"), 1)
        self.assertIn("echo hi", cmds)


class CliSmoke(unittest.TestCase):
    def test_init_status_phase_gates(self):
        with tmpdir() as d:
            p = sieve("init", d, "--pack", "web3", "--quiet", check=True, cwd=d)
            self.assertIn("NEXT: Fill in the scope card", p.stdout)
            # cannot leave init without scope
            p = sieve("phase", "xray", cwd=d)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("lists nothing in scope", p.stderr)
            # --force needs a real reason, and records a waiver
            p = sieve("phase", "xray", "--force", cwd=d)
            self.assertNotEqual(p.returncode, 0)
            p = sieve("phase", "xray", "--force", "--reason", "lab run, scope filled later", cwd=d)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue(os.path.isfile(os.path.join(d, ".sieve", "waivers.tsv")))
            p = sieve("status", cwd=d, check=True)
            self.assertIn("phase=xray", p.stdout)
            self.assertIn("NEXT:", p.stdout)

    def test_banner(self):
        p = sieve("banner", check=True)
        self.assertIn("███████╗██╗███████╗██╗   ██╗███████╗", p.stdout)
        self.assertIn("what survives the sieve is real", p.stdout)

    def test_ladder_lists_rungs(self):
        p = sieve("ladder", check=True)
        for r in ("input", "inversion", "transplant", "construct", "fresh-eyes"):
            self.assertIn(r, p.stdout)

    def test_fence(self):
        with tmpdir() as d:
            make_engagement(d)
            self.assertEqual(sieve("fence", "host", "app.example.com", cwd=d).returncode, 0)
            self.assertEqual(sieve("fence", "host", "evil.com", cwd=d).returncode, 2)
            self.assertEqual(sieve("fence", "host", "127.0.0.1:8000", cwd=d).returncode, 2)


if __name__ == "__main__":
    unittest.main()
