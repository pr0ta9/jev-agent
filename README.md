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
- **Nous is the strong model, whichever one you configure** (`NOUS_MODEL`; GPT-6 Astra in `.env.example`). With the
  release default `NOUS_SCOPE=planning` it only plans, and only when Jev has no confident move. When nothing is
  confident or a checked aspect of the answer is still missing, Jev dispatches a full agent (Codex, `DISPATCH_MODEL`,
  Luna by default) that does its own research, writes only inside its own folder under `vault/work/`, and has no
  timeout. The harness picks up its answer and files; memory and habits stay the harness's.
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

| agent | essential facts /29 | seconds, 4 questions | cost |
|---|---:|---:|---:|
| **Nyx, release default, run 1** | 27 | 104 | $0.24 |
| **Nyx, release default, run 2** | 23 | 90 | about $0.10 |
| **Nyx, release default, run 3** | 15 | 62 | about $0.05 |
| Nyx, Mercury + Sol nous | 24 | 105 | $0.63 |
| Codex Luna | 29 | 210 | $0.79 |
| Codex Sol | 29 | 298 | $4.44 |
| Claude Fable | 29 | 438 | $3.48 |
| Codex Astra | 29 | 630 | $11.62 |
| Claude Sonnet | 22 | 75 | $0.34 |
| Claude Haiku | 20 | 72 | $0.19 |

What this shows: the three Nyx runs score 27, 23 and 15 of 29, a median of 23. At its best, Nyx gets 27 of 29
essential facts in half the time of the fastest full agent for under a third of the cost; the median run gives up six
facts to Codex Luna in under half the time for about an eighth of the cost. Run 3 scored 15 because the public search
engines behind SearXNG were rate-limited on the ETIAS question: Nyx said so and asked to retry instead of answering
from nothing, which scores 0 of 7 there. It answers from one web digest, checks its own reply against an expert's
checklist of what a complete answer needs, and hands only the gaps to a Codex agent: in runs 1 and 2, one of the four
questions each.
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
