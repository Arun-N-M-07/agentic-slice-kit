# Project Report: Notes Tutor on the agentic slice kit

Status: pushes 1 to 3 are on GitHub (commits `7e9b4af`, `025517a`, `e12fc7f`). Pushes 4 and 5 are built and
tested locally but not yet committed; each item below is marked with which it is. This report says what
exists, how it was checked, and what is not done.
`docs/PORT-CHECKLIST.md` is the row-by-row record; this file is the readable summary.

## 1. What this is

A study helper for blind and low-vision students. A student asks a question about their own notes
and gets an answer that is checked against those notes before they see it. A small tutor step then
explains the answer and asks one check question.

It is built on the kit's spine (`slice/`): an append-only run record in SQLite, a runner that moves a
run through states, token and attempt budgets, and one LLM client. Everything specific to this
problem is in `demo/notes/`, and the command line is `scripts/notes.py`.

Most of the design and several modules are adapted from the team's earlier project (Netra, built
before the event). Each adapted module says so in its docstring, and `docs/PORT-CHECKLIST.md` lists
what was adapted and what is new.

## 2. How an answer is made

1. **Retrieve.** The question is searched against the student's notes. Search is hybrid: keyword rank
   (BM25) and embedding rank fused with reciprocal rank fusion. This exists because embeddings alone
   ranked the right note fifth of five for one real question. (Push 4 adds access filtering before ranking,
   for uploaded notes.)
2. **Draft.** A model writes an answer that must cite the passages it used, or state that the notes
   do not cover the question.
3. **Check the evidence (code).** The evidence ledger verifies that every citation is a passage that
   was really retrieved. Code blocks bad citations without spending a model call.
4. **Gate (model).** A second model judges whether the cited passages support the claims. It can
   block with specific objections and send the draft back for revision.
5. **Stop rules.** A draft that repeats itself, or runs out of attempts or budget, stops with a plain
   message instead of looping.
6. **Tutor.** After a passed answer, the Tutor writes an explanation and a check question. The correct
   answer is stored privately and graded by code, not by a model. Multiple choice is preferred,
   because exact-match short answers marked correct paraphrases wrong.

The answer is never taken away if the Tutor fails: the answer stays, without the explanation.

## 3. What is implemented

### Push 1: foundation, draft, ledger, gate (pushed)
- Three hand-written study notes (Ohm's law, electrical power, series circuits) in `demo/notes/corpus/`.
  They deliberately do not cover parallel circuits or transistors, so "the notes do not cover this"
  is a case that can be tested.
- Six fixed questions (`questions.py`) with expected outcomes, and scripted replies (`canned.py`,
  `stub.py`) for offline, free runs. Scripted replies are labelled as such; they are not model output.
- Schemas (`schema.py`), prompts (`prompts/`), the evidence ledger (`ledger.py`) and the flow
  (`flow.py`) with injected model, search and clock so the whole state machine is testable.
- Untrusted-text guard: retrieved text and file names are escaped and the prompts state that data is
  not instructions.

### Push 2: stop rules, Tutor, validation, evaluation (pushed)
- Stop rules, and the Tutor (`tutor.py`) with a private answer record, deterministic grading and a
  scoped hand-off from the notes run.
- `validate.py`: runs the fixed questions and reports checks per question. `evaluate.py`: paired
  comparison of two reports (regressions, improvements, model calls, warnings).
  `probes.py`: feeds the gate deliberately wrong drafts to see whether it blocks them (live only).
- Commands in `scripts/notes.py`: `validate`, `ask`, `probe-gate`, `compare`, `replay`, `token`, `serve`.

### Push 3: sessions, API, tester page, persistence, hybrid retrieval, gate probe (pushed)
- Accounts and hashed access tokens; sessions with a version number; idempotent requests (a replay
  returns the first result and does not advance the version); a request that reuses an id with
  different content is refused; another account's session looks like "not found".
- Cancel is checked before each model call and again at commit, and a cancelled result is discarded.
- No database transaction is held open during model calls. Forward-only, checksummed migrations.
- Per-account hourly rate limit, because live questions spend the team's capped key.
- JSON API under `/v1/sessions` and a no-JavaScript tester page (`/` and `/ask`). Security
  headers, `SameSite=Strict` `HttpOnly` cookies, same-origin form check, size-limited forms, errors
  that never echo input or exception text, model output escaped in pages.

### Push 4: job queue, uploads, read-aloud (built, not yet pushed)
- **Job queue** (`jobs.py`): leases, attempt counted at claim, fenced writes, checkpointed stages,
  exponential backoff with jitter, dead-letter and cancel, heartbeat thread. Handlers are safe to run
  more than once.
- **Uploads** (`sources.py`): text and Markdown notes stored as versions. A staged ingestion job
  (validate, parse, chunk, embed, activate) can be retried without repeating finished stages. A session
  stays on the versions it started with; a deleted source disappears at once and its passages are
  purged by a job. Search only returns passages the asking account may see; the three sample notes are
  visible to everyone and cannot be deleted. Uploads work in live mode only.
- **Read-aloud** (`describe.py`): tables and simple equations are turned into text a screen reader can
  speak, and added to the notes without changing the original.
- The `/sources` page lets a signed-in user paste notes, see their state and delete them. `serve --live`
  starts the background worker.
- Retrieval takes an allowed set of passages and filters before ranking, so a passage the asker may not
  see cannot influence the order of one they may.
- The ask page now tells the user an answer can take up to half a minute.

## 4. How it was checked

- **Tests:** 401 tests pass locally (`python -m pytest tests`), across 16 `tests/test_notes_*.py` files.
  The pushed commits contain 12 of those files; the job queue, uploads, read-aloud and tracing tests
  (4 files) are in pushes 4 and 5. None call a model or spend the team key: the CLI tests force an empty key.
- **Mutation checks:** for several modules (jobs, describe, earlier ones) the code was deliberately
  broken to see whether the tests noticed. Weak tests found this way were strengthened. This has **not**
  been done for `sources.py` or `tracing.py`.
- **Real models:** the live path was tried a few times through the page and the command line, at a total
  cost of a few cents. Observed answer time was 10.7 s and 29.3 s in two samples. That is three samples,
  not a benchmark.
- **Real browser:** the tester page was used in a browser for sign-in, asking, the check question,
  and a deliberately injected instruction in a note (ignored).
- **Real embeddings:** the sources tests use the kit's real embeddings to show that another account's
  notes are never returned, including on an exact keyword match, and that deleted notes cannot be found.

Model policy used: stub for everyday work; OpenRouter (fallback off, model recorded) only for checks
that need a real model; Gemini or Groq only for optional stress tests.

## 5. Where things are

| Path | What |
|---|---|
| `demo/notes/flow.py`, `ledger.py`, `schema.py`, `prompts/` | draft, evidence check, gate |
| `demo/notes/tutor.py` | explanation, check question, grading |
| `demo/notes/retrieval.py`, `corpus.py`, `corpus/` | hybrid search and the sample notes |
| `demo/notes/sessions.py`, `service.py`, `api.py` | accounts, sessions, service, HTTP and page |
| `demo/notes/jobs.py`, `sources.py`, `describe.py` | job queue, uploads, read-aloud (push 4, not yet pushed) |
| `demo/notes/tracing.py` | sanitized traces and AX exporter (push 5, not yet pushed) |
| `demo/notes/validate.py`, `evaluate.py`, `probes.py` | validation and evaluation tooling |
| `scripts/notes.py` | command line: validate, ask, probe-gate, compare, replay, token, serve |
| `tests/test_notes_*.py` | the tests |
| `docs/PORT-CHECKLIST.md` | row-by-row status, including what was adapted |

## 6. How to run it

```bash
python -m pytest tests                          # all tests, no model calls
python scripts/notes.py validate                # fixed questions on scripted replies (free)
python scripts/notes.py token --name tester1    # issue an access code (shown once)
python scripts/notes.py serve                   # tester page, offline demonstration
python scripts/notes.py serve --live            # real models (spends the team key), uploads, worker
```

