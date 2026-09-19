#!/usr/bin/env python3
"""Run and validate the notes slice.

    python scripts/notes.py validate                    # stub: scripted replies, free, proves wiring
    python scripts/notes.py validate --tutor            # ...and the Tutor turn for answered questions
    python scripts/notes.py validate --live --label a   # REAL models on OpenRouter: spends the team key
    python scripts/notes.py ask "your question" --live  # one live question, with a readable transcript
    python scripts/notes.py compare out/a.json out/b.json
    python scripts/notes.py replay <run_id> --db out/a.db

Without --live nothing here calls a model, uses the network, or costs anything. With --live it
uses the OPENROUTER_API_KEY in .env and the kit's embedding search, so run it where the kit's
environment is (the Codespace). Live runs turn the fallback model off (--allow-fallback keeps
it) and run the gate on SLICE_ESCALATION_MODEL (--gate default uses the draft model).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slice import runner
from slice.config import settings as load_settings
from slice.store import Store

from demo.notes import evaluate
from demo.notes.corpus import ingest_notes
from demo.notes.flow import build_flow
from demo.notes.questions import QUESTIONS
from demo.notes.validate import LiveNotReady, live_settings, run_validation, transcript

OUT = Path("out")


def cmd_validate(args) -> int:
    label = args.label or ("stub" if not args.live else time.strftime("live-%Y%m%d-%H%M%S"))
    only = args.only.split(",") if args.only else None
    n = len([q for q in QUESTIONS if not only or q.id in only])
    if args.live:
        print(f"LIVE run '{label}': {n} question(s), about 2 to 6 model calls each, on your OpenRouter key.")
    else:
        print(f"STUB run '{label}': scripted replies, no model is called. This proves wiring, not model behavior.")
    try:
        report = run_validation(live=args.live, settings=load_settings(), db_path=OUT / f"notes-{label}.db",
                                label=label, only=only, gate=args.gate,
                                allow_fallback=args.allow_fallback, with_tutor=args.tutor)
    except LiveNotReady as e:
        print(f"cannot run live: {e}", file=sys.stderr)
        return 2
    (OUT / f"notes-{label}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = evaluate.report_markdown(report)
    (OUT / f"notes-{label}.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {OUT}/notes-{label}.json, .md and .db")
    return 0 if report["summary"]["failed"] == 0 and report["summary"]["not_evaluable"] == 0 else 1


def cmd_ask(args) -> int:
    if not args.live:
        print("ask needs --live (there is no scripted reply for free text). "
              "Use `validate` for the offline demonstration.", file=sys.stderr)
        return 2
    try:
        settings = live_settings(load_settings(), allow_fallback=args.allow_fallback)
        from slice.llm import complete
        db = OUT / f"notes-ask-{time.strftime('%H%M%S')}.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        store = Store(str(db))
        ingest_notes(store)
    except (LiveNotReady, ImportError) as e:
        print(f"cannot run live: {e}", file=sys.stderr)
        return 2
    run_id = store.create_run("notes")
    store.append(run_id, "input", {"text": args.text}, produced_by="system")
    gate_model = settings.escalation_model if args.gate == "escalation" else None
    runner.advance(store, run_id, build_flow(call=complete, gate_model=gate_model), settings)
    print("\n".join(transcript(store, run_id)))
    print(f"\nrun {run_id}   replay: python scripts/notes.py replay {run_id} --db {db}")
    return 0


def cmd_compare(args) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    cmp = evaluate.compare_reports(baseline, candidate)
    print(evaluate.comparison_markdown(cmp, baseline["label"], candidate["label"]))
    return 1 if cmp["regressions"] else 0


def cmd_replay(args) -> int:
    store = Store(args.db)
    print("\n".join(transcript(store, args.run_id)))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Run and validate the notes slice.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def live_options(sp):
        sp.add_argument("--live", action="store_true", help="use the real models (spends the OpenRouter key)")
        sp.add_argument("--gate", choices=["escalation", "default"], default="escalation",
                        help="which model judges drafts in a live run")
        sp.add_argument("--allow-fallback", action="store_true",
                        help="keep the fallback model on (off by default so a live run tests one model)")

    v = sub.add_parser("validate", help="run the fixed questions and report")
    live_options(v)
    v.add_argument("--label", help="name for the report files")
    v.add_argument("--only", help="comma-separated question ids")
    v.add_argument("--tutor", action="store_true", help="also run the Tutor for answered questions")
    v.set_defaults(func=cmd_validate)

    a = sub.add_parser("ask", help="one live question with a transcript")
    live_options(a)
    a.add_argument("text")
    a.set_defaults(func=cmd_ask)

    c = sub.add_parser("compare", help="paired comparison of two reports")
    c.add_argument("baseline")
    c.add_argument("candidate")
    c.set_defaults(func=cmd_compare)

    r = sub.add_parser("replay", help="print a stored run")
    r.add_argument("run_id")
    r.add_argument("--db", required=True)
    r.set_defaults(func=cmd_replay)

    args = p.parse_args()
    OUT.mkdir(exist_ok=True)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
