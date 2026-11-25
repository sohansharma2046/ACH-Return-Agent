"""Tests for the rules engine and the agent's guardrails."""

from types import SimpleNamespace as NS

from ach_agent.agent import triage_offline, triage_with_claude
from ach_agent.tools import Toolbox, load_batch


def box():
    return Toolbox(load_batch())


def decision(return_id):
    return box().get_policy_decision(return_id)


def test_first_nsf_is_represented():
    d = decision("RET-001")            # R01, clean account
    assert d["action"] == "represent_once" and d["retry"]


def test_nsf_stops_after_two_represents():
    d = decision("RET-002")            # R01, already re-presented twice
    assert d["action"] == "stop_retries_and_contact_customer" and not d["retry"]


def test_unauthorized_freezes_and_escalates():
    d = decision("RET-003")            # R10 on a 6-day-old account that already traded
    assert d["freeze_account"] and d["human_review_required"] and d["severity"] == "high"


def test_revoked_never_retries():
    assert not decision("RET-005")["retry"]   # R07


def test_repeat_return_escalates():
    d = decision("RET-006")            # second admin return in 90 days
    assert d["human_review_required"] and d["severity"] == "high"


def test_unknown_code_goes_to_a_person():
    d = decision("RET-008")            # R77 is not a real code
    assert d["action"] == "escalate_to_operations" and d["human_review_required"]


def test_offline_pipeline_passes_its_checks():
    b = box()
    for r in load_batch():
        assert not triage_offline(r, b)["needs_attention"]


class FakeClaude:
    """Scripted stand-in for the API: skips the policy and recommends a retry."""
    def __init__(self):
        self.messages = self
        self.turn = 0

    def create(self, **kw):
        self.turn += 1
        if self.turn == 1:
            return NS(content=[NS(type="tool_use", id="t1", name="save_partner_notice",
                                  input={"return_id": "RET-003", "notice": "We will retry."})])
        return NS(content=[NS(type="text", text="Looks fine.\nFINAL_ACTION: represent_once")])


def test_guardrail_catches_agent_ignoring_policy():
    b = box()
    ret = b.returns["RET-003"]
    res = triage_with_claude(ret, b, FakeClaude())
    assert res["needs_attention"]
    assert not res["checks"]["called_policy"]
    assert not res["checks"]["action_matches_policy"]
    assert res["decision"]["action"] == "freeze_and_escalate_to_fraud"   # policy still wins
