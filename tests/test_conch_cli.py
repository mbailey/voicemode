"""Tests for the ``voicemode conch`` CLI group (VM-1616).

Home isolation comes from the autouse ``isolate_home_directory`` fixture in
conftest.py, which re-pins ``Conch.LOCK_FILE`` into a per-test fake home;
``ConchQueue`` derives its paths from there, so the whole conch state is
isolated automatically. All commands are exercised through Click's
``CliRunner`` against the same on-disk state the production CLI uses.
"""

import json

import pytest
from click.testing import CliRunner

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue
from voice_mode.cli_commands.conch import conch


@pytest.fixture
def runner():
    return CliRunner()


def _register(sid, *, agent=None, mode="wait"):
    """Register a live local waiter (pid = current process)."""
    return ConchQueue.register(sid, agent=agent, mode=mode)


def _make_holder(agent="holder", sid="holder-sess"):
    """Write a live holder lock (current-process pid => get_holder sees it)."""
    Conch().acquire(agent_name=agent, session_id=sid)


# --------------------------------------------------------------------------- #
# ConchQueue.grant() — the additive helper give() relies on
# --------------------------------------------------------------------------- #

class TestGrantHelper:
    def test_grant_named_live_waiter(self):
        _register("alpha-111", agent="alpha")
        _register("beta-222", agent="beta")
        assert ConchQueue.grant("beta-222") is True
        assert ConchQueue.granted_to() == "beta-222"

    def test_grant_non_waiter_returns_false_and_writes_nothing(self):
        _register("alpha-111", agent="alpha")
        assert ConchQueue.grant("ghost-999") is False
        assert ConchQueue.granted_to() is None

    def test_grant_none_returns_false(self):
        assert ConchQueue.grant(None) is False


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #

class TestStatus:
    def test_empty(self, runner):
        result = runner.invoke(conch, ["status"])
        assert result.exit_code == 0
        assert "free" in result.output.lower()
        assert "empty" in result.output.lower()

    def test_empty_json(self, runner):
        result = runner.invoke(conch, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == {"holder": None, "queue": []}

    def test_holder_and_queue_json(self, runner):
        _make_holder(agent="cora", sid="cora-sess-abcdef")
        _register("waiter-1-aaa", agent="w1")
        _register("waiter-2-bbb", agent="w2", mode="callback")
        result = runner.invoke(conch, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["holder"]["agent"] == "cora"
        assert data["holder"]["held_seconds"] is not None
        # Ordered queue, positions 1..2, FIFO by registration.
        assert [q["position"] for q in data["queue"]] == [1, 2]
        assert data["queue"][0]["session_id"] == "waiter-1-aaa"
        assert data["queue"][1]["mode"] == "callback"

    def test_holder_human_render(self, runner):
        _make_holder(agent="cora", sid="cora-sess")
        _register("w-1", agent="dora")
        result = runner.invoke(conch, ["status"])
        assert result.exit_code == 0
        assert "cora" in result.output
        assert "dora" in result.output
        assert "#1" in result.output


# --------------------------------------------------------------------------- #
# give
# --------------------------------------------------------------------------- #

class TestGive:
    def test_give_by_session_prefix(self, runner):
        _register("alpha-111", agent="alpha")
        _register("beta-222", agent="beta")
        result = runner.invoke(conch, ["give", "beta-2"])
        assert result.exit_code == 0
        assert ConchQueue.granted_to() == "beta-222"
        assert "beta" in result.output

    def test_give_by_agent_name(self, runner):
        _register("sess-xyz-111", agent="cora")
        result = runner.invoke(conch, ["give", "cora"])
        assert result.exit_code == 0
        assert ConchQueue.granted_to() == "sess-xyz-111"

    def test_give_ambiguous_prefix_errors_without_granting(self, runner):
        _register("dup-111", agent="a")
        _register("dup-222", agent="b")
        result = runner.invoke(conch, ["give", "dup-"])
        assert result.exit_code != 0
        assert "ambiguous" in result.output.lower()
        assert ConchQueue.granted_to() is None

    def test_give_no_match_errors(self, runner):
        _register("alpha-111", agent="alpha")
        result = runner.invoke(conch, ["give", "nobody"])
        assert result.exit_code != 0
        assert ConchQueue.granted_to() is None

    def test_give_no_waiters_errors(self, runner):
        result = runner.invoke(conch, ["give", "cora"])
        assert result.exit_code != 0
        assert "no one is waiting" in result.output.lower()

    def test_grantee_acquires_others_blocked(self, runner):
        """After give, only the grantee can try_acquire (FIFO grant honoured)."""
        _register("alpha-111", agent="alpha")
        _register("beta-222", agent="beta")
        runner.invoke(conch, ["give", "beta-222"])
        # Conch is free; grant names beta. alpha must wait, beta may take it.
        assert Conch(session_id="alpha-111").try_acquire(agent_name="alpha") is False
        assert Conch(session_id="beta-222").try_acquire(agent_name="beta") is True

    def test_give_survives_holder_release(self, runner):
        """give a non-head waiter while someone holds; the holder's release must
        promote the gift target, not the head (the give-while-holding case)."""
        holder = Conch(session_id="cora-sess")
        holder.acquire(agent_name="cora")
        _register("alpha-111", agent="alpha")  # head
        _register("beta-222", agent="beta")    # gift target (behind alpha)
        result = runner.invoke(conch, ["give", "beta-222"])
        assert result.exit_code == 0
        assert ConchQueue.granted_to() == "beta-222"
        holder.release()  # full release -> grant_next; must respect the give
        assert ConchQueue.granted_to() == "beta-222"  # NOT promoted to alpha
        # Close the loop: the give-grant actively gates the next acquire.
        assert Conch(session_id="alpha-111").try_acquire(agent_name="alpha") is False
        assert Conch(session_id="beta-222").try_acquire(agent_name="beta") is True


# --------------------------------------------------------------------------- #
# bump
# --------------------------------------------------------------------------- #

class TestBump:
    def test_bump_live_holder_drops_and_promotes_head(self, runner):
        _make_holder(agent="cora", sid="cora-sess")
        _register("next-111", agent="nextagent")
        result = runner.invoke(conch, ["bump"])
        assert result.exit_code == 0
        # Holder lock cleared.
        assert Conch.get_holder() is None
        assert not Conch.LOCK_FILE.exists()
        # Head promoted as grantee.
        assert ConchQueue.granted_to() == "next-111"
        assert "nextagent" in result.output

    def test_bump_live_holder_empty_queue_frees_conch(self, runner):
        _make_holder(agent="cora", sid="cora-sess")
        result = runner.invoke(conch, ["bump"])
        assert result.exit_code == 0
        assert Conch.get_holder() is None
        assert "free" in result.output.lower()

    def test_bump_no_holder_nothing_waiting(self, runner):
        result = runner.invoke(conch, ["bump"])
        assert result.exit_code == 0
        assert "nothing to bump" in result.output.lower()

    def test_bump_stale_lock_directs_to_release(self, runner):
        # Lock file present but holder pid is dead -> get_holder() is None.
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        Conch.LOCK_FILE.write_text(json.dumps({
            "pid": 2147480000, "agent": "ghost", "session_id": "g",
            "acquired": "2020-01-01T00:00:00", "held": False,
        }))
        result = runner.invoke(conch, ["bump"])
        assert result.exit_code != 0
        assert "release" in result.output.lower()


# --------------------------------------------------------------------------- #
# release / clear
# --------------------------------------------------------------------------- #

class TestRelease:
    def test_release_when_free_is_idempotent(self, runner):
        result = runner.invoke(conch, ["release"])
        assert result.exit_code == 0
        assert "already free" in result.output.lower()

    def test_release_live_holder_requires_confirm(self, runner):
        _make_holder(agent="cora", sid="cora-sess")
        # Decline the confirmation -> aborts, lock stays.
        result = runner.invoke(conch, ["release"], input="n\n")
        assert result.exit_code != 0
        assert Conch.LOCK_FILE.exists()

    def test_release_yes_clears_lock_and_grant(self, runner):
        _make_holder(agent="cora", sid="cora-sess")
        _register("w-111", agent="w")
        ConchQueue.grant("w-111")
        result = runner.invoke(conch, ["release", "--yes"])
        assert result.exit_code == 0
        assert not Conch.LOCK_FILE.exists()
        assert ConchQueue.granted_to() is None

    def test_clear_alias_works(self, runner):
        result = runner.invoke(conch, ["clear"])
        assert result.exit_code == 0


# --------------------------------------------------------------------------- #
# wait
# --------------------------------------------------------------------------- #

class TestWait:
    def test_returns_immediately_when_already_granted(self, runner):
        _register("me-111", agent="me")
        ConchQueue.grant("me-111")
        result = runner.invoke(conch, ["wait", "--session", "me-111", "--timeout", "2"])
        assert result.exit_code == 0
        assert "your turn" in result.output.lower()

    def test_returns_when_head_and_conch_free(self, runner):
        # Only waiter, no holder -> head and free immediately.
        result = runner.invoke(conch, ["wait", "--session", "solo-111", "--timeout", "2"])
        assert result.exit_code == 0
        assert "your turn" in result.output.lower()

    def test_times_out_and_deregisters_when_not_head(self, runner, monkeypatch):
        import voice_mode.config as cfg
        monkeypatch.setattr(cfg, "CONCH_CHECK_INTERVAL", 0.02, raising=False)
        # "other" registered first => it's the head; our session is #2, blocked.
        _register("other-aaa", agent="other")
        result = runner.invoke(
            conch, ["wait", "--session", "mine-bbb", "--timeout", "0.1"]
        )
        assert result.exit_code == 1
        assert "timed out" in result.output.lower()
        # Cleaned up after itself.
        assert all(e.session_id != "mine-bbb" for e in ConchQueue.list())

    def test_head_does_not_return_while_give_grant_points_elsewhere(self, runner, monkeypatch):
        """A waiter at the head of a free conch must NOT get a false 'your turn'
        when an explicit give-grant designates a *different* session — that
        session's grant gates the next acquire, so the head can't act yet."""
        import voice_mode.config as cfg
        monkeypatch.setattr(cfg, "CONCH_CHECK_INTERVAL", 0.02, raising=False)
        _register("alpha-111", agent="alpha")   # head
        _register("gamma-222", agent="gamma")   # behind alpha
        ConchQueue.grant("gamma-222")           # operator gave it to gamma
        # Conch is free, alpha is head — but gamma holds the grant.
        result = runner.invoke(
            conch, ["wait", "--session", "alpha-111", "--timeout", "0.1"]
        )
        assert result.exit_code == 1            # timed out, no false grant
        assert "timed out" in result.output.lower()
        assert ConchQueue.granted_to() == "gamma-222"  # gamma's grant untouched

    def test_json_granted_output(self, runner):
        _register("me-111", agent="me")
        ConchQueue.grant("me-111")
        result = runner.invoke(
            conch, ["wait", "--session", "me-111", "--timeout", "2", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["granted"] is True
        assert data["session_id"] == "me-111"
