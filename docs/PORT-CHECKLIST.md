# Port checklist: earlier project (Netra) into this repo

Source: <https://github.com/The-Trinetras/netra_demo> (built before the event; see
`PRE-EVENT-ASSETS.md`). Each row is ported during the event, adapted to the kit, with
its tests. A row is ticked only when the
ported code runs and its tests pass. Anything unticked at the freeze is **not done**,
and this file says so.

Sizes are lines of source in the earlier project, before adaptation. Tests come with
their feature.

## Push 1: Foundation

- [x] Declaration (`PRE-EVENT-ASSETS.md`)
- [x] Notes corpus + retrieval (`demo/notes/`; new, not ported)
- [x] Fixed question set + scripted stub (`demo/notes/`; new, not ported)

## Push 2: The loop (`api/.../coordinator`, 14 files, 2,406 lines)

- [x] Draft step with citations (`decisions.py`, `context.py`, prompts)
- [x] Evidence ledger (`evidence_check.py`)
- [x] Gate + back-edge (`graph.py`)

## Push 3: Safety and Tutor (`coordinator`, `learning/tutor`, `learning/quiz`)

- [ ] Stop rules and budget (`limits.py`, no-progress rule)
- [ ] Untrusted-text guard (prompts, tool registry)
- [ ] Tutor step, check question, grading (`learning/tutor`, `learning/quiz`, `learning/assessment`; 24 files, 3,665 lines)

## Push 4: Live validation and evaluation (`evaluation/`)

- [ ] OpenRouter validation script (new)
- [ ] Evaluation package: dataset, rubrics, assertions, review sheet, runner (about 40 scripts, 59 cases)

## Push 5: Backend (`identity` 520, `session` 1,824, `transport` 1,488, `db` 510 lines, `shared/contracts`)

- [ ] Sessions and identity
- [ ] API and WebSocket protocol, cancel, reconnect, contracts
- [ ] Persistence and migrations

## Push 6: Pipeline (`content` 3,484, `multimedia` 6,837, `worker` 3,088 lines)

- [ ] Worker: leases, retries, outbox (`worker/jobs`, `worker/runtime`)
- [ ] Ingestion: parsing, chunking, embedding (`content`)
- [ ] Multimedia: figures, tables, equations, video (`multimedia`)

## Push 7: Tracing (`platform`, 1,429 lines)

- [ ] Tracing module
- [ ] AX exporter, verified in a real AX project (new: never finished in the earlier project)

## Push 8: Graph

- [ ] Neo4j projection, run against a real server (never run in the earlier project)
- [ ] Concept catalog (missing in the earlier project)

## Push 9: Speech (`speech`, 705 lines)

- [ ] Speech output and STOP fencing
- [ ] Voice input (disabled in the earlier project)

## Push 10: Client (`client/`, 82 C# files)

- [ ] WPF client, live mode, keyboard and NVDA behavior

## Push 11: Docs and deployment

- [ ] Architecture docs and shared contracts
- [ ] Deployment files (`infrastructure/`)

## Size check

The earlier project's Python source is about 26,000 lines (api 22,900, worker 3,100),
plus the evaluation scripts, 82 C# client files, and 116 test files. That is more than
two days of porting. Pushes 1 to 4 are the priority; the rest is best effort.
