# Status, 2026-09-24

DESIGN.md is the specification; this file is where the proof of concept stands against it.

## Where the proof stands

- `soma/` implements DESIGN.md §15 in 16 files and about 1,150 non-blank lines, with 89 tests (fake Jev, fake
  writers, no network).
- Nous is a dispatched full agent (Codex, `DISPATCH_MODEL`, Luna by default; the harder calls use `NOUS_MODEL`, Astra
  in `.env.example`; both can be any model the task needs) since 2026-09-24: Jev dispatches it on a no-move, and on
  an aspect still missing after the rewrite when Jev says more research could answer it. It writes only in
  `vault/work/<trace id>/`, has no timeout, and the harness records its files.
- With the release default (`PSYCHE_PROVIDER=mercury NOUS_SCOPE=planning EXPECT_CHECK=1`) the best of three runs
  scores 27 of 29 essential facts in 104 seconds for $0.24; full agents score 29 in 210 to 630 seconds for $0.79 to
  $11.62. Details, every run, method and per-miss attribution: bench/questions.md.
- Eight of eleven acceptance rows pass in every run; the three habit-learning rows fail (see Known issues). Before
  dispatch replaced planning, all eleven passed in five runs.

## Decisions recorded

1. Mercury 2.5 is a psyche provider: same facts as Codex Luna on this set, 1 to 3 seconds per call against Codex's
   4.8-second start floor.
2. `NOUS_SCOPE=planning` means nous never composes and psyche writes every reply; it is the release default.
3. Scoring is by hand against Google AI Mode's essential facts; regex checklists are a smoke test only.
4. On `--accept`, values a generator proposed are not compared against the draft's bindings.
5. Verification asks, beside each aspect, whether the reply states each representative evidence passage; a dropped
   passage gets one rewrite at the same tier (DESIGN.md §4.6).
6. Writer sessions run with web search disabled, and an empty or discarded rewrite never replaces a draft.
7. A failed web search ends in an ask ("try again" / "never mind") instead of an answer written without sources.
8. Nous is a dispatched full agent, not a planner. Every no-move dispatches (chosen knowing it stops borderline runs
   from becoming habits); a gap dispatches only when Jev says more research could answer it.
9. The expert checklist is on by default: psyche lists what a complete answer settles, Jev checks the reply against
   it, and confident gaps go to the agent (DESIGN.md §4.6).

## Known issues

- **Habit learning under dispatch.** In plain note runs Jev often leans the right way but under the 0.70 bar; the
  round has no confident move, the request is dispatched (38 to 67 s of Codex Luna), and a dispatched run is never
  learned as a habit. etias-note-1, 3 and 4 failed in all three runs for this reason. The alternative, not built:
  ask Jev "can the catalog's tools finish this?" before dispatching, and run the tools it leans toward when it says yes.
- **The checklist does not always fire.** Python's gaps went to the agent in three of six runs; in the others Jev judged
  the checklist answered and the reply kept 4 of 7.
- **Evidence coverage.** The digest shows about 1,500 tokens and withholds the rest; facts outside what it shows
  cannot be recovered (Python's `-X gil` switch and C extensions re-enabling the GIL are missed in every run). Nyx
  has no browse tool to follow the digest's "browse a URL to read more".
- **Dropped sub-facts.** Writers still drop details they were given ("he learned of Eris's love only after her
  death" in four of five runs). The passage check catches only details inside the representative passages.
- **Rewrite quality.** A same-tier rewrite told about a dropped passage sometimes pastes the passage's raw text,
  footnote markers included.
- **Search reliability.** Public engines behind SearXNG rate-limit heavy use; one of twenty release questions got
  no results.
- **Note titles.** In two of about a dozen note runs the title proposal produced no usable candidate and Nyx asked
  the user to pick a title from words of the message. Not reproduced in isolation; logged here, not fixed.
- **Habit drafts depend on the drafter.** Sol has drafted trigger phrases without the subject and a narrower query
  than the run used; both were caught by verification and the habit was not promoted.
- `soma/loop.py` is at 183 of its 200-line cap.
- Cleanup later: the ladder's "plan-proposed value" rung and learn's exemption for plan-filled values are unused since
  planning was removed.

## Open questions

1. Whether a no-move should first ask Jev if the catalog's tools can finish the request (see Known issues).
2. A compose rule to keep stated causes and mechanisms, measured on the same questions.
3. A trigger-quality rule in prompts/habit.md, rerun with Sol as the drafter.
4. A larger public question set, several runs per agent and blind scoring.
