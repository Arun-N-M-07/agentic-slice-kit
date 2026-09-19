"""The two handlers, the domain rules, and the Flow object for the notes slice.

DRAFTING <-> GATING, with the same shape as demo/smoke/flow.py. What is ported from
the earlier project is the DESIGN: draft with citations, an evidence ledger that
code (not the model) uses to verify citations, and a gate that sends unsupported
work back. Business rules live here, in code; the model returns judgements and this
file decides what they mean.

Nothing in slice/ changes for this to run.

Two model calls per cycle at most: one draft, one gate. If the ledger already finds
a mechanical problem, the gate model is NOT called: there is nothing for it to judge
that code has not already rejected, and the call would cost tokens for no information.

Stop rules here are deliberately just the revision limit. The fuller no-progress and
budget rules are the next port; until then MAX_REVISIONS keeps the loop bounded.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from types import SimpleNamespace

from slice.llm import complete
from slice.records import RunState

from .ledger import Evidence, EvidenceLedger
from .schema import AnswerDraft, Objection, Verdict

MAX_REVISIONS = 3
"""Drafts the gate may send back before the run stops. Counted from the record
history, not from budget.attempt(): that one is a spend fence and also ticks for
malformed-reply retries, so sharing a counter silently costs a student a revision."""

TOP_K = 3
"""Passages retrieved per question. Few on purpose: every passage is tokens in both
model calls, and a wrong answer with ten passages is harder to audit than with three."""

_PROMPTS = Path(__file__).parent / "prompts"


def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def _untrusted(text: str) -> str:
    """Escape data so it cannot close the tag that marks it as data."""
    return html.escape(text, quote=False)


# ------------------------------------------------------------------ messages

def _evidence_block(evidence: list[Evidence]) -> str:
    if not evidence:
        return "VALIDATED EVIDENCE:\n- none retrieved"
    lines = ["VALIDATED EVIDENCE:"]
    for e in evidence:
        lines.append(
            f'<untrusted_evidence id="{_untrusted(e.evidence_id)}" '
            f'locator="{_untrusted(e.locator)}">{_untrusted(e.text)}</untrusted_evidence>')
    return "\n".join(lines)


def build_draft_messages(question: str, evidence: list[Evidence], prior: dict | None,
                         objections: list[dict]) -> list[dict]:
    user = [f'QUESTION:\n<untrusted_dialogue role="student">{_untrusted(question)}</untrusted_dialogue>',
            _evidence_block(evidence)]
    if prior and objections:
        user.append("YOUR PREVIOUS DRAFT:\n" + json.dumps(prior, indent=2))
        user.append("IT WAS SENT BACK. Fix each of these:\n\n" + "\n".join(
            f"- {o.get('requirement_id') or 'draft'}: {o['problem']}" for o in objections))
    return [
        {"role": "system", "content": _prompt("draft")},
        {"role": "user", "content": "\n\n---\n\n".join(user)},
    ]


def build_gate_messages(question: str, evidence: list[Evidence], draft: dict) -> list[dict]:
    user = [f'QUESTION:\n<untrusted_dialogue role="student">{_untrusted(question)}</untrusted_dialogue>',
            _evidence_block(evidence),
            "DRAFT TO JUDGE:\n" + json.dumps(draft, indent=2)]
    return [
        {"role": "system", "content": _prompt("gate")},
        {"role": "user", "content": "\n\n---\n\n".join(user)},
    ]


# ------------------------------------------------------------ ledger -> text

_EXPLAIN = {
    "no_validated_evidence_cited": "The answer cites no evidence. Cite the evidence_id of each passage you relied on.",
    "cited_evidence_not_validated": "These ids are not among the retrieved passages, so they cite nothing",
    "requirement_unresolved": "This requirement is not supported by any retrieved passage",
    "assessment_for_undeclared_requirement": "You assessed a requirement you never declared",
    "gap_stated_but_every_requirement_supported": "You stated a gap, but every requirement is marked supported",
}


def objections_from_problems(problems: list[str]) -> list[Objection]:
    """Turn the ledger's short codes into objections the drafter can act on."""
    out = []
    for code in problems:
        head, _, detail = code.partition(":")
        req, _, extra = detail.partition(":") if head == "requirement_unresolved" else (None, "", detail)
        sentence = _EXPLAIN.get(head, head)
        if head == "requirement_unresolved":
            out.append(Objection(requirement_id=req, problem=f"{sentence} ({extra})."))
        elif detail:
            out.append(Objection(problem=f"{sentence}: {detail}."))
        else:
            out.append(Objection(problem=sentence))
    return out


def _default_search(store, query: str, k: int):
    from .corpus import search_notes
    return search_notes(store, query, k=k)


# ------------------------------------------------------------------ handlers

def build_flow(call=complete, search=_default_search):
    """Return the Flow. `call` and `search` are injected so the whole state machine
    runs with canned replies and canned passages: no key, no network, no embeddings."""

    def _evidence(ctx) -> list[Evidence]:
        return [Evidence(**c) for c in ctx.latest("evidence")["passages"]]

    def handle_drafting(ctx) -> RunState:
        question = ctx.latest("input")["text"]

        if ctx.latest("evidence") is None:            # retrieve once, on the first pass
            passages = [Evidence.from_chunk(c) for c in search(ctx.store, question, TOP_K)]
            ctx.append("evidence",
                       {"passages": [vars(p) for p in passages]}, produced_by="system:retrieval")
        evidence = _evidence(ctx)

        prior = ctx.latest("draft")
        verdict = ctx.latest("verdict")
        objections = verdict["objections"] if prior and verdict and verdict["status"] == "BLOCK" else []

        draft = call(
            settings=ctx.settings, budget=ctx.budget,
            messages=build_draft_messages(question, evidence, prior, objections),
            schema=AnswerDraft, step="draft",
        )
        ctx.append("draft", draft.model_dump(), produced_by="agent:draft")
        return RunState.GATING

    def handle_gating(ctx) -> RunState:
        question = ctx.latest("input")["text"]
        evidence = _evidence(ctx)
        draft = AnswerDraft.model_validate(ctx.latest("draft"))

        ledger = EvidenceLedger()
        ledger.add_evidence(evidence)
        problems = ledger.check_draft(draft)

        if problems:
            # Code found a mechanical defect: no model call, the objection is certain.
            verdict = Verdict(status="BLOCK", objections=objections_from_problems(problems))
            ctx.append("verdict", verdict.model_dump(), produced_by="system:ledger")
        else:
            verdict = call(
                settings=ctx.settings, budget=ctx.budget,
                messages=build_gate_messages(question, evidence, draft.model_dump()),
                schema=Verdict, step="gate",
            )
            ctx.append("verdict", verdict.model_dump(), produced_by="agent:gate")

        if verdict.status == "PASS":
            return RunState.COMPLETE

        # Counted from the record, not from the budget. See MAX_REVISIONS.
        blocks = sum(1 for v in ctx.history("verdict") if v.payload["status"] == "BLOCK")
        if blocks >= MAX_REVISIONS:
            ctx.append("failure",
                       {"kind": "gate_exhausted",
                        "detail": f"Blocked {blocks} times; no revision passed."},
                       produced_by="system")
            return RunState.FAILED
        return RunState.DRAFTING

    return SimpleNamespace(
        name="notes",
        handlers={
            RunState.DRAFTING: handle_drafting,
            RunState.GATING: handle_gating,
        },
    )
