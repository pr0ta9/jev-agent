# jev-agent

A personal-assistant backend where a decision model chooses, code acts, and a language model writes only when prose
is the product. The decision model is [TypeSafe](https://typesafe.ai) Jev; the writer is Mercury 2.5 (or a Codex
model); the persona is Nyx, a fictional assistant with a tsundere voice. This is a proof of concept.

## The idea

Most agents let one generative model do everything: decide the next step, call tools, judge whether it is done,
and write the answer. That makes every step slow, costly and hard to audit, and it puts control flow inside a prompt.

jev-agent splits the work:

- **Pneuma (the decision layer, TypeSafe Jev)** answers typed multiple-choice questions with calibrated confidence,
  about 0.6 seconds per round: should the web be searched, does a habit fit, does this reply cover each point the
  user asked, is the request satisfied. It never writes text.
- **Code** turns confident answers into actions, runs tools in parallel, and owns every loop, budget and stop.
- **Psyche (Mercury 2.5, or Codex Luna)** writes replies from the evidence and renders them in Nyx's voice. It runs
  blind: no tools, no web.
- **Nous is the strong side, and its models are whatever the task needs.** When nothing is confident or a checked
  aspect of the answer is still missing, Jev dispatches a full agent (Codex, `DISPATCH_MODEL`, Luna by default) that
  does its own research, writes only inside its own folder under `vault/work/`, and has no timeout; the harder calls
  go to `NOUS_MODEL` (GPT-6 Astra in `.env.example`). Both can be set to any model that suits the work. The harness
  picks up the answer and files; memory and habits stay the harness's.
- **Habits** are learned from accepted runs: a drafted workflow is promoted only after a later run reproduces it,
  then replays with no model choosing steps.

Every decision, with its confidence, lands in a JSONL trace, so each run can be read back step by step. The web is
read through [jev-digest](https://github.com/pr0ta9/jev-digest), which searches, fetches and uses Jev to keep only
the passages that answer the question, with their URLs.

## Results

Four research questions (Python 3.13 free-threading, dietary fibre, the EU's ETIAS, and a Mushoku Tensei plot
question). Google AI Mode's own answer to each question is the rubric: its essential facts, the ones that directly
answer what was asked, number 29 in total. One scorer, the author, read every reply and scored it by hand; paraphrase
counts, a fact stated wrongly does not. Every agent ran isolated from local configuration.

![Key facts found against total time for Nyx and five full agents](docs/results.png)

Nyx run by Jev alone, with Mercury writing and no Codex model at all, got 25 of 29 essential facts in 47 seconds for
five cents. With nous, the Codex agent Jev dispatches for gaps, it got 27 of 29 in 104 seconds for $0.24: half the
time of the fastest agent that got all 29, for under a third of its cost.

| agent | essential facts /29 | seconds, 4 questions | cost |
|---|---:|---:|---:|
| **Nyx, Jev only** (best of three runs) | 25 | 47 | $0.05 |
| **Nyx with nous** (best of three runs; the release default) | 27 | 104 | $0.24 |
| Codex Luna | 29 | 210 | $0.79 |
| Codex Sol | 29 | 298 | $4.44 |
| Claude Fable | 29 | 438 | $3.48 |
| Codex Astra | 29 | 630 | $11.62 |
| Claude Sonnet | 22 | 75 | $0.34 |
| Claude Haiku | 20 | 72 | $0.19 |

Both Nyx variants have Jev decide every step and Mercury 2.5 write every reply. "Jev only" never calls a Codex model;
"with nous" adds the expert checklist and dispatches Codex Luna for the gaps Jev confirms. Each full agent ran once;
Claude Sonnet invented its Mushoku Tensei answer, and Claude Haiku ran with one added instruction to answer general
questions, because inside Claude Code it otherwise refused two as off-topic.

[![Nyx answering the ETIAS question](docs/media/nyx-etias.gif)](docs/media/nyx-etias.mp4)

The ETIAS question, replayed from the run's own trace: every decision Jev made, each tool call and the writer.
16.5 s, 7 of 7 essential facts, no agent needed.

[![Nyx answering the Python question with one agent dispatch](docs/media/nyx-python.gif)](docs/media/nyx-python.mp4)

The Python question: the expert checklist finds two gaps, Jev dispatches a Codex agent, and the final answer scores
7 of 7. Long waits are shortened on screen; every time shown is real. Click either replay for the full-quality video.

<details>
<summary>Every run of every configuration</summary>

| agent | essential facts /29 | seconds, 4 questions | cost |
|---|---:|---:|---:|
| Nyx with nous, run 1 | 27 | 104 | $0.24 |
| Nyx with nous, run 2 | 23 | 90 | about $0.10 |
| Nyx with nous, run 3 (search engines rate-limited on ETIAS; Nyx asked to retry) | 15 | 62 | about $0.05 |
| Nyx, Jev only, run 1 (search engines rate-limited on fibre) | 19 | 55 | $0.03 |
| Nyx, Jev only, run 2 | 25 | 47 | $0.05 |
| Nyx, Jev only, run 3 | 24 | 63 | $0.03 |
| Nyx, dispatch without the checklist, runs 1 to 3 | 23, 22, 22 | 52, 50, 46 | $0.05 each |
| Nyx, Mercury + Sol nous | 24 | 105 | $0.63 |
| Nyx, Mercury + Astra nous | 23 | 176 | $1.68 |

</details>

Costs are list prices from token counts; Claude runs are what Claude Code reports. Mercury 2.5 is priced at its
launch discount ($0.04/$0.15 per million tokens); at the standard $0.20/$0.75, each Nyx run costs under a cent more.
Four questions and one scorer is a proof of concept, not a benchmark. Method, per-question results, where each
missed fact was lost (the digest or the writer), and how to reproduce: [bench/questions.md](bench/questions.md).

Eight of the eleven acceptance rows pass in every run, including a real dispatch whose files the harness finds in
the agent's folder. The three habit-learning rows fail: on borderline rounds Jev is not confident enough to act, the
request is dispatched, and a dispatched run is never learned as a habit. Before dispatch replaced planning, all eleven
passed. See [docs/STATUS.md](docs/STATUS.md).

## Running it

You need Python 3.11+, Docker, a [TypeSafe](https://typesafe.ai) API key for Jev, an
[Inception Labs](https://www.inceptionlabs.ai) API key for Mercury 2.5, and the [Codex CLI](https://github.com/openai/codex)
logged in (nous is dispatched and habits are drafted through it).

```
git clone https://github.com/pr0ta9/jev-digest
docker compose -f jev-digest/docker/docker-compose.searxng.yml up -d     # SearXNG on port 8089, with autocomplete

git clone https://github.com/pr0ta9/jev-agent && cd jev-agent
python -m venv .venv
.venv/bin/pip install -e .[dev]            # Windows: .venv\Scripts\pip install -e .[dev]
cp .env.example .env                       # fill in TYPESAFE_API_KEY and MERCURY_API_KEY
.venv/bin/nyx "What is the EU ETIAS travel authorization?"
.venv/bin/nyx --accept traces/<trace>.jsonl     # accept a run: drafts or verifies a habit
.venv/bin/python -m pytest                 # 89 tests, no network
```

The first two lines only start the search service; jev-digest itself is installed from GitHub as a dependency.

## What is where

| path | what |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | the specification: glossary, control loop, decision catalog, slot ladder, learning, persona, and the measurement behind every rule |
| [docs/STATUS.md](docs/STATUS.md) | where the proof stands, known issues, open questions |
| `soma/` | the proof: 16 files, about 1,150 lines. `loop.py` is the round; `questions.py` holds every question Jev is asked |
| `prompts/` | the writer, dispatched-agent, expert-checklist, proposer, habit-drafter and voice prompts |
| `bench/` | the acceptance set, baseline runners, hand scores and the Google rubric |
| `tests/` | 89 tests with a fake Jev, fake writers and a fake agent |

## Status

A working proof of concept, not a product. It runs from the command line with a local vault of notes and files.
Known gaps are listed in [docs/STATUS.md](docs/STATUS.md): the digest sometimes shows the writer too little evidence,
writers still drop sub-facts they were given, and public search engines rate-limit heavy use.

## License

MIT. See [LICENSE](LICENSE).
