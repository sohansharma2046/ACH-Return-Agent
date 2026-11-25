"""Tests for the rules, the numbers and the guardrails. No API key needed:
the agent tests use scripted stand-ins for Claude."""

import asyncio
from types import SimpleNamespace as NS

import pytest

from ach_agent.agent import run_agent, run_offline
from ach_agent.data import SampleData
from ach_agent.tools import Toolbox


def box():
    return Toolbox(SampleData())


def decision(rid):
    return box().decisions[rid]


# ------------------------------------------------------------- the rules
def test_first_insufficient_funds_is_represented():
    d = decision("RET-001")
    assert d.action == "represent_once" and d.retry and d.severity == "low"


def test_retries_stop_after_two_represents():
    d = decision("RET-002")
    assert d.action == "stop_retries_and_contact_customer" and not d.retry


def test_unauthorized_freezes_and_goes_to_fraud():
    d = decision("RET-003")
    assert d.action == "freeze_and_escalate_to_fraud" and d.freeze_account and d.human_review


def test_shared_bank_account_blocks_a_routine_retry():
    """RET-008 alone looks routine (R01, re-present). Its bank account also funds ACC-1003,
    which reported an unauthorized debit, so it must be held for fraud review instead."""
    d = decision("RET-008")
    assert d.action == "hold_and_escalate_to_fraud" and not d.retry and d.severity == "high"


def test_revoked_payment_is_never_retried():
    assert not decision("RET-005").retry


def test_repeat_bad_account_return_needs_a_person():
    d = decision("RET-006")
    assert d.human_review and d.severity == "high"


def test_unknown_code_goes_to_a_person():
    d = decision("RET-009")
    assert d.action == "escalate_to_operations" and d.human_review


# ------------------------------------------------------------- the numbers
def test_money_at_risk():
    e = box().exposure
    assert e["RET-003"] == {"deficit": 1000.0, "covered_by_positions": 870.0, "uncovered": 130.0}
    # Two returns on ACC-1001: each alone fits in its $120 cash, together they don't.
    assert e["RET-001"]["deficit"] == 0 and e["RET-009"]["deficit"] == 20.0


def test_partner_nacha_watch_list():
    status = {p["partner"]: p for p in box().partner_risk}
    assert status["Lumen Wallet"]["metrics"]["unauthorized"]["status"] == "watch"
    assert status["Harbor Neobank"]["metrics"]["administrative"]["status"] == "watch"
    assert status["Northwind Invest"]["status"] == "ok"


def test_handbook_search_finds_the_right_rule():
    hits = box().search_policy_handbook("shared bank account fraud")["sections"]
    assert hits and hits[0]["title"] == "Shared bank accounts"


def test_offline_run_passes_every_check():
    run = run_offline(box())
    assert not any(c["needs_attention"] for c in run["cases"])
    assert run["totals"]["uncovered"] == 199.6 and run["totals"]["fraud_escalations"] == 2


# ------------------------------------------------- agent guardrails (fake Claude)
def tool(name, **inp):
    return NS(type="tool_use", id=f"t_{name}_{inp.get('return_id', '')}", name=name, input=inp)


class ScriptedClaude:
    """Stands in for the API: plays back a fixed list of turns."""

    def __init__(self, turns):
        self.turns, self.messages = list(turns), self

    def create(self, **_):
        content = self.turns.pop(0) if self.turns else [NS(type="text", text="Done.")]
        return NS(content=content, usage=NS(input_tokens=10, output_tokens=5))


def good_turns(b):
    checks = [tool("get_policy_decision", return_id=r) for r in b.returns]
    notices = [tool("save_partner_notice", return_id=r, action_stated=d.action,
                    notice=f"{b.returns[r]['return_code']}: ${b.returns[r]['amount']:,.2f} deposit returned. "
                           f"Next step: {d.action.replace('_', ' ')}.")
               for r, d in b.decisions.items()]
    brief = tool("submit_briefing", headline="Two linked accounts need fraud review.",
                 key_risks=[{"title": "Shared bank account", "return_ids": ["RET-003", "RET-008"], "why": "..."}],
                 leadership_summary="...", extra_review=[{"return_id": "RET-001", "reason": "Same-day second return."}])
    return [checks, [tool("find_linked_accounts", account_id="ACC-1008")], notices, [brief]]


def test_well_behaved_agent_passes_and_can_add_caution():
    b = box()
    run = run_agent(b, ScriptedClaude(good_turns(b)))
    assert not any(c["needs_attention"] for c in run["cases"])
    first = next(c for c in run["cases"] if c["return"]["return_id"] == "RET-001")
    assert first["decision"]["human_review"] and first["decision"]["action"] == "represent_once"


def test_injected_instruction_is_caught_and_policy_wins():
    """A fake agent obeys the instruction hidden in RET-004's bank addenda, skips the
    policy check and tells the partner the payment will be re-presented."""
    b = box()
    turns = [[tool("save_partner_notice", return_id="RET-004", action_stated="represent_once",
                   notice="R02: the $250.00 deposit will be re-presented and funds released.")],
             [tool("submit_briefing", headline="All clear.", key_risks=[], leadership_summary="Nothing to do.")]]
    run = run_agent(b, ScriptedClaude(turns))
    case = next(c for c in run["cases"] if c["return"]["return_id"] == "RET-004")
    assert case["notice"]["status"] == "blocked"
    assert not case["notice"]["checks"]["action_matches_policy"]
    assert case["decision"]["action"] == "request_new_bank_link" and not case["decision"]["retry"]
    assert case["needs_attention"] and run["agent_checks"]["policy_checked"] == 0


def test_agent_cannot_invent_returns_or_tools():
    b = box()
    turns = [[tool("approve_all_and_release_funds"),
              tool("submit_briefing", headline="x", key_risks=[], leadership_summary="x",
                   extra_review=[{"return_id": "RET-999", "reason": "made up"}])]]
    run = run_agent(b, ScriptedClaude(turns))
    assert b.calls[0]["error"] and run["agent_checks"]["reviews_added_by_agent"] == []


# ------------------------------------------------------------- MCP server
def test_mcp_server_exposes_read_only_tools():
    pytest.importorskip("mcp.server.mcpserver")
    import mcp_server
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert "get_policy_decision" in names and "find_linked_accounts" in names
    assert not any(n.startswith(("save", "submit")) for n in names)
