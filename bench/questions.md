# Benchmark: acceptance set, rubric and standings

Current as of 2026-09-24. Earlier versions (regex-scored runs, the first baselines, the old digest format) are in git
history of the development repository and are superseded by what follows.

## 1. The acceptance set (DESIGN.md §15)

| row | message | check |
|---|---|---|
| python313, fiber, etias, rudeus | the four `query` strings in checklists.json | facts (see §2); every tool run follows a passed pneuma answer in its round |
| file | "summarise this file" + bench/sample.txt | attachment fills the slot with no ladder question; reply present |
| picture | "which file is that picture from December?" | reply names a file or ask lists candidates; never a fabricated file |
| operation | with vault/ops/espn.md open: "research Future Rudeus in Mushoku Tensei" | the gate does not attach to espn |
| etias-note-1 | "find the current ETIAS start date and save it as a note", no habit | digest then write_note; `--accept` drafts a habit |
| etias-note-2 | same, `--withhold-tools`, not accepted | dispatch event; the agent's files all under `vault/work/<trace id>/`; reply present |
| etias-note-3 | same, plain, then `--accept` | the draft reproduces this run and is promoted |
| etias-note-4 | same, plain | habit event, no dispatch; less time than row 2 |

The etias-note rows are the learning loop end to end: draft, verify by reproduction, promote, replay. Accept compares
tools and order, non-prose slot values and prose source steps; values a generator proposed are not compared.

**Current design (nous as a dispatched agent), three runs:** file, picture, operation and etias-note-2 pass every time;
etias-note-1, 3 and 4 fail every time. In those plain runs Jev leaned the right way (search 0.53 to 0.62, save the
note 0.65 to 0.86) but under the 0.70 bar, so the round had no confident move and the request was dispatched; a
dispatched run is never drafted or verified as a habit, so nothing was learned. Dispatching on every no-move is a
deliberate choice; asking Jev "can the catalog's tools finish this?" before dispatching is the alternative.
**Before dispatch** (nous planning), all eleven rows passed in five release runs. `bench/run.py` prints NO for
question rows whose regex smoke test falls under its floor; the regex under-counts paraphrase and is not the score.

## 2. How the four questions are scored

The rubric is Google AI Mode's own answer to the same question, captured 2026-09-23 (bench/reference-google.md).
Google is the rubric, not a competitor. **Essential** items are the ones that directly answer a sub-question the user
asked, at the detail needed to act on it: 29 in total (python313 7, fiber 6, ETIAS 7, Rudeus 9). Every reply is read
and scored by hand (bench/hand-scores.json, `google.essential`); paraphrase counts, a fact stated wrongly does not.
Where Google itself is wrong or stale, the item is the topic Google covered, graded against the sources. One scorer,
the author's side, did all scoring; treat single-point differences as noise.

Every agent runs isolated. Codex runs with `--ignore-user-config` in an empty directory; Claude Code runs with
`--setting-sources local --strict-mcp-config` in an empty directory. Nyx's questions run with a vault cleared of
notes, habits and fixture files and with no recent turns, so no answer sees an earlier one.

## 3. Standings on the four questions

| agent | essential /29 | seconds, 4 questions | cost at list | searched |
|---|---:|---:|---:|---|
| Codex Luna (gpt-5.6-luna) | 29 | 210 | $0.79 | 8 to 12 times per question |
| Codex Sol | 29 | 298 | $4.44 | 6 to 14 |
| Claude Fable (2026-09-23) | 29 | 438 | $3.48 | on 2 of 4 (by turn count) |
| Codex Astra | 29 | 630 | $11.62 | 6 to 18 |
| **Nyx, current (expert checklist on), run 1** | 27 | 104 | $0.24 | one digest per question; python313 dispatched to the agent (53 s) |
| Nyx, expert checklist on, run 2 | 23 | 90 | about $0.10 | one fiber dispatch (19 s) |
| Nyx, expert checklist on, run 3 | 15 | 62 | about $0.05 | ETIAS: search engines rate-limited, Nyx asked to retry |
| Nyx, dispatch without the checklist, run 1 | 23 | 52 | $0.05 | one digest per question; no dispatch |
| Nyx, dispatch without the checklist, run 2 | 22 | 50 | $0.05 | one digest per question; no dispatch |
| Nyx, dispatch without the checklist, run 3 | 22 | 46 | $0.05 | one digest per question; no dispatch |
| Nyx, Mercury writes all, before dispatch, run 2 | 25 | 47 | $0.05 | one digest per question |
| Nyx, Mercury writes all, before dispatch, run 3 | 24 | 63 | $0.03 | one digest per question |
| Nyx, Mercury writes all, before dispatch, run 1 | 19 | 55 | $0.03 | fiber: search engines rate-limited, Nyx asked to retry |
| Nyx, Mercury + Sol nous | 24 | 105 | $0.63 | one digest per question |
| Nyx, Mercury + Astra nous | 23 | 176 | $1.68 | one digest per question |
| Claude Sonnet (2026-09-23) | 22 | 75 | $0.34 | once; the Rudeus answer is fabricated |
| Claude Haiku | 20 | 72 | $0.19 | once; ran with an appended instruction to answer general questions, since without it Claude Code refused two as off-topic |

The current design and "Mercury writes all" share the release default (`PSYCHE_PROVIDER=mercury`, `NOUS_SCOPE=planning`): Mercury 2.5 writes
every reply and nous only plans. Costs are list prices from tokens: Jev $0.042 per million input tokens (the only
Jev price we have), Mercury $0.04/$0.15, Luna $1/$6, Sol $5/$30, Astra $10/$50; Claude runs are what Claude Code
reports. Nyx's cost includes the Jev calls inside jev-digest (about 200k input tokens per digest), which earlier
versions of this table left out. Per-question rows: `python bench/baselines.py none`.

Without the expert checklist no question was dispatched: Jev judged every aspect covered, including Python's
limitations, whose two missing facts the digest never showed (§4). With it (`EXPECT_CHECK=1`, the release default),
psyche lists what an expert answer must settle and Jev checks the reply against each item; python313 went to the
agent in three of six runs and scored 7 of 7 each time, against 3 to 5 without. A dispatch, when it happens, costs 38 to 67 s and
about $0.15 to $0.27 of Codex Luna (twelve measured on the note rows). The honest reading: Nyx answers in 46 to 63
seconds for a few cents, three to thirteen times faster than the full
agents and 16 to 390 times cheaper, and gives up four to five essential facts of 29 to do it. A small
full agent (Codex Luna) gets every fact for $0.79 in 210 seconds.

## 4. Where Nyx loses facts

Traced from each reply back to the evidence the writer received:

- **Not in the evidence (digest).** Python's `-X gil`/`PYTHON_GIL` switch and C extensions turning the GIL back on
  are missed in every run: the digest ranks the Python 3.14 free-threading page first and shows about 1,500 tokens,
  and neither fact is in what it shows. "Experimental" appears only inside a sample command's output.
- **In the evidence, dropped by the writer (system).** Rudeus learning of Eris's love only after her death (four of
  five runs), fruit and whole grains in the fibre list (Astra), "not a visa" or the 30 countries (ETIAS, three runs).
- **Search failure.** One fiber question got no search results twice because SearXNG's engines were rate-limited;
  Nyx said so and offered a retry instead of answering from nothing.

The fact check added on 2026-09-24 (each representative passage of each aspect is a verification question; a
dropped one gets one rewrite at the same tier) recovered "not a visa" and the 30 countries in one ETIAS run and
rescued an empty Mercury draft in another; it cannot recover facts the digest does not show.

## 5. Variance and caveats

- Four questions, one scorer, one run per baseline and five for Nyx. This is a proof of concept, not a benchmark
  result to generalise from.
- Search is the largest source of variance: the digest took 3 to 13 seconds per question, and heavy benchmarking
  rate-limits public search engines behind SearXNG.
- Nyx rows scored before 2026-09-24 (27 to 28 of 29) ran with recent turns and notes from earlier rows in context
  and with the old digest format; they are not comparable with the table above.
- ETIAS timing is contested across sources (official Q4 2026 versus reporting that 2026 is off); either is accepted.

## 6. What was learned, in order

1. Regex fact checks under-count paraphrase; scoring moved to reading every reply by hand.
2. Baselines must run isolated from the machine's configuration: a Claude run that carried a global CLAUDE.md, and
   Codex runs that carried user plugins, both changed time and cost (Codex Sol went from 554 s to 298 s isolated).
3. Google AI Mode's answer replaced a hand-written checklist as the rubric, then was pruned to essentials.
4. Astra composing was 95 percent of Nyx's cost; `NOUS_SCOPE=planning` removes it at small fact cost.
5. Aspect-level verification passes replies that drop sub-facts; passage-level checks catch some, not all.
6. Benchmark isolation matters for the system under test too: recent turns and vault notes leaked answers between
   rows until both were cleared per question.
7. Writers must be blind by construction: `codex exec` searches the web unless told not to, and a discarded
   non-blind rewrite once replaced a passing draft.

## 7. Reproducing

```
python bench/run.py                 # full acceptance set with the current .env
python bench/run.py questions       # the four questions only
python bench/one.py etias           # one question
python bench/baselines.py luna      # one isolated baseline: sol | astra | luna | sonnet | fable | haiku; "none" refreshes the table
python bench/report.py OUT.html "Label=bench/results-x.txt" ...
```

Configuration is by environment: `PSYCHE_PROVIDER=codex|mercury`, `NOUS_MODEL=gpt-6-astra|gpt-5.6-sol`,
`NOUS_SCOPE=all|planning`. Result files and traces are ignored by git; hand scores live in bench/hand-scores.json.
