# jev-agent — Design

Status: design baseline of 2026-09-22, revised after the second design session (naming §1, the round §3, the
ladder §4.4, the gate §4.7, psyche and nous §7, persona §14, proof of concept §15, code structure §16) and again
during the proof, where every rule added carries the trace that forced it. The §15 proof is implemented in `soma/`
and its acceptance set passes (docs/STATUS.md, bench/questions.md). Everything measured before the proof was
measured against v1 (private), the jev-digest package ([github.com/pr0ta9/jev-digest](https://github.com/pr0ta9/jev-digest)) or standalone harnesses; the source files
are listed in §12 so a claim can be checked before it is built on.

v2 is a new backend. It keeps what v1 got right (one continuous Nyx identity, durable memory, deterministic habits,
permission gates on dangerous tools) and replaces the control architecture: a decision model chooses, code executes,
and generators write only when prose is the product. The persona is new (§14): nothing from v1's identity files is
carried over, because v2 is written to be open-sourced.

---

## 0. Why a new project

Three reasons, all from the 2026-09-21/22 measurements:

1. **The control loop was the cost, not the tools.** Nyx's answers matched the best agents on facts but took 69 to 444 s.
   The time was a classifier written as prose (2 to 10 s, six timeouts in fifty-two calls), a model deciding one tool call
   per turn, a per-page summarizer (15 to 45 s per page), and budgets that ended runs before they finished. Replacing the
   web tools alone cut a 444 s turn to 128 s; the remaining 100 s was a writer writing.
2. **Judgment lived in prompts.** Whether a message continues an operation, whether a run should stop, which tool to use,
   what to keep in context: every one of these was a sentence in a system prompt that a generative model obeyed or did
   not. The Rudeus research request attached itself to the ESPN Fantasy operation because a prompt said "if this
   continues one of these, call attach_operation", and nothing checked.
3. **Legacy weight.** v1 carries three generations of naming (skills, tools, meta tools, habits, recipes), historical
   docs that contradict the code, and switches nobody remembers. v2 starts with one glossary (§1) and one control loop
   (§3), and copies from v1 only what §10 lists.

---

## 1. Glossary (fixed before any code)

The three model roles and the whole are named after the Greek tripartite person: three parts, one body. None ranks
above another in sequence; only pneuma has authority over decisions.

| Term | Meaning in v2 | Not to be called |
|---|---|---|
| **σῶμα, soma** | The whole system: the code (controller, resolvers, tools, store) and the three model roles below. The Python package is `soma`. | "the app", "the agent" |
| **πνεῦμα, pneuma** | The decision layer: TypeSafe Jev answering typed questions (Choice, Score, Noul) with calibrated confidence. It judges, gates and verifies; it never writes text. The only part consulted every round. | "classifier", "router LLM", "L2" |
| **ψυχή, psyche** | The small writer and the voice: renders reply, ask and end in Nyx's register, fills short slots, proposes candidates for the ladder. Never plans, never decides. | "L3", "Luna", "Nyx model" |
| **νοῦς, nous** | The full-capability agent, dispatched when the no-move predicate of §4.1 holds or when a checked aspect stays missing (§4.6): a Codex session with its own web search, writing only in its work folder. Also a composer when the fill table of §7 selects it. Never faces the user, holds nothing between calls, never writes memory or habits. | "L4", "Senpai", "subagent", "executor" |
| **Controller** | The code loop in §3: gate once, then rounds of decide → run → fold, then present. Owns all control flow, budgets and side effects. | "cascade", "L1–L4" |
| **State** | The typed, explicit record of a request: the message, recent turns, attachments, resolved references, tool results, decisions taken. Everything a decision sees is in state. | "context window", "prompt" |
| **Resolver** | Deterministic code that turns a vague reference into candidates: file filters, memory retrieval, autocomplete, the operations roster. | — |
| **Tool** | A capability with typed inputs and outputs, run by code: the digest, file read and list, notify, shell. A tool's inputs are slots. | "executor" (v1's word for the L4 subagent), "skill" |
| **Slot** | One typed input of a tool or habit, filled by the ladder (§4.4): attachments, the user's words, autocomplete, the resolver, a generator's proposals, then ask. | "parameter" in prompts |
| **Digest** | The read primitive: search + fetch + judged passages with sources, one round (`jev-digest`). The only web read. | "web_search"/"browse" as separate loops |
| **Habit** | A verified, versioned fixed workflow of tool calls with typed bindings; replayed with no model deciding steps. Its slots are filled like a tool's. | "recipe" (a recipe is guidance, not a habit) |
| **Operation** | A long-lived unit of work with its own state, timeline and effects. Long-term by design (§6). Attached or opened only at the gate (§4.7). | "task", "agent" |
| **Exits** | The three ways a request ends: **reply** (satisfied, something to say), **ask** (the user decides, always from concrete options), **end** (nothing to say). Psyche renders all three; end renders nothing. "Clarify" in this document means taking the ask exit. | "ask_user" free text |
| **Nyx** | The single user-facing persona, new for v2 (§14), defined in `prompts/voice.md` and rendered by psyche over whatever wrote. | — |

Rule: a word from the right-hand column is never the name of a v2 concept in code, docs or logs. Describing v1 with
v1's own words is fine.

---

## 2. Principles

1. **The decision layer decides; code owns control flow; generators are tools.** No generative model chooses the next
   step, decides whether to stop, or judges relevance. Those are typed questions with calibrated answers. When
   nothing is confident, or the evidence cannot cover what was asked, pneuma's answers dispatch the request to a full
   agent (nous); the agent's answer is a result that pneuma verifies like any draft, not a decision.
2. **Anchor every question.** Each question's target is fixed by state or by an earlier round's answer, never by a
   sibling question in the same request. Questions in one request are independent and cannot coordinate; asking them to
   produced the field-decoherence loops of the first graph experiment. Code enumerates; the model judges.
3. **The state is the parameter.** Tools take state: the user's own words as the first search, the
   URLs from a previous result for fetch, the raw message and recent turns for memory retrieval, typed bindings for
   habits. The decision layer routes pieces of state to tools; it never authors a string.
4. **Judge outcomes, not intentions.** Whether a passage answers an aspect is an easier and more reliable question than
   whether a query will find it. Cheap actions (local search, fetch) run speculatively in parallel; the decision layer
   judges what came back.
5. **Confidence gates every branch.** Confident answers act; unconfident ones escalate: to a stronger method, or to the
   user as a clarify with options. Thresholds are per decision and recorded with it.
6. **One second per decision round.** A round is one request to the decision layer (0.2 to 0.8 s measured) plus the
   parallel resolvers it needed. Psyche and nous are tools with their own time; their duration is not a control cost.
7. **Describe at ingestion.** Files are captioned or OCR'd when they arrive, attachments and operations are indexed like
   memory, so later references ("that picture from December") are text problems for a resolver.
8. **Explicit state, no compaction.** Context for a generator is selected per request from state (§4.2); nothing is
   summarized away permanently.
9. **Learning is separate from the foreground.** A request completes with current assets; habit drafting, verification
   and promotion run afterwards on observed evidence. First success never activates anything.
10. **Permissions are code.** Dangerous tools check policy before running; no role, prompt or model declaration
    grants approval.

---

## 3. The control loop

```
request ──► state      = ingest(message, attachments)     # files described by name and text
            state      = fold(state, fetch(state))        # vault, all in parallel: memory, habits, tool snippets, ops roster, files
            state      = gate(state)                      # ONCE: attach to an open operation, open a new one, or neither (§4.7)
loop (≤ N rounds, each ≤ ~1 s):
    answers = decide(state)                               # ONE pneuma request: the triage questions (§4.1)
    actions = plan(answers)                               # code: every confident YES is one action; conflicts resolved by rule
    results = run_concurrently(actions)                   # replay habit · run tool (slots filled first, §4.4) · psyche or nous writes · no move: dispatch nous
    state   = fold(state, results)                        # typed; decisions and confidences recorded
    if done(answers, state) or state.ask: break           # §4.6: done is code; ask is set by run when a slot or a check fails
present(state)   ──► psyche renders reply, ask (with options) or end (silent)
record(state)                                             # the trace and the turn; drafting waits for --accept (§4.8)
```

- The gate runs once, before the first round. Nothing after it can attach to or open an operation (user ruling
  2026-09-22); a dispatched agent cannot open one, §13.
- `decide` is a single request per round. It may hold dozens of questions; each is anchored on state.
- `plan` is code. A question's answer maps to exactly one effect. Conflicts are resolved by rules written down here,
  not by asking the model to reconcile. A habit that fits wins over a tool for the same need.
- `run_concurrently` is where parallelism lives: every YES runs at once. Dependent steps are the next round. A habit
  and a tool both fill their slots (§4.4) before they run; a slot the ladder cannot fill ends the round in ask.
- A round is one decide request. A request that runs k dependent tool steps takes k+1 rounds, the last confirming
  done; a dispatch is one round, however long the agent takes.
- `fold` writes typed results and the decisions that produced them into state, so the next round is anchored on them
  and so the trace can be replayed.
- Rounds are bounded by count and by wall time, and the stop decision is itself a question in `decide` ("is the
  request satisfied by what is in state?"), never a token budget cutting a generator off mid-sentence.

---

## 4. The decision catalog

Each entry: what is asked, over what candidates, what code does with the answer.

### 4.1 Triage (every round)
One request, every question anchored on state and independent of its siblings: per fetched habit, "does habit H fit
this request?" (Noul); per tool candidate, "run tool A now?" (Noul); "is prose needed?" with its reach and exposure
(two Scores, §7); "does the message name its subject?" (Noul, §4.4); and the done questions (§4.6). Code turns the
answers into actions: a confident habit replays, slots first; confident tools run at once; prose goes to psyche or
nous by the fill table; if nothing is confident, the request is dispatched to nous. Replaces the v1 classifier (a generative
call, 2–10 s) with one ~0.3 s request. There is no "decision task" branch: a pure choice is candidates, pneuma picks,
psyche says it. Decision versus generation is a property of a step, never of the request. One more Choice rides in
the request, "what does the message need first" (STATE, WEB, VAULT, WRITE): measured on 2026-09-22, the per-tool
"run digest now?" hovered at 0.59 to 0.92 on plain fact questions and sometimes said NO, while the mutually
exclusive framing is sharp; code adds the one tool a confident WEB or VAULT implies when no per-tool answer passed.
A request dispatches at most once, and a second no-move takes the ask exit. (Until 2026-09-24 nous proposed a
typed plan of catalog tool calls instead; it was replaced because a plan can only reach what the catalog reaches.)
A replayed habit is the whole request and ends it, since "does the habit fit" stays YES and
would replay it every round (measured: six replays in 128 s); so does a tool that wrote prose, such as a saved note,
since the note is the answer and a reply prose on top cost 8 s per note task. A tool call
whose name and inputs already ran this request is dropped: with the "still needs the web" answer staying YES after a
digest, the same query ran six times on one request, and identical repeats also trip SearXNG into "no search
results". If every action in a round was such a repeat, the loop writes from what it has. An empty action list is a no-move whatever the
answers said, because a guard may have dropped the only tool pneuma passed. A tool with a prose slot waits until
something is in state to write from. A tool with a file
slot runs only with an attachment or a confident VAULT answer, because a stray RUN on a nutrition question once
ended in "which file?". A confident WRITE answer implies `write_note` the way WEB implies the digest. Writing from the user's words alone needs a confident STATE answer to "what does the message
need first", not a "reach: words" answer, which let fact questions be answered from nothing. The no-move predicate is
one function in `questions.py`: no habit-fits YES, no run-tool-now YES, and no runnable prose fill, where a prose
fill is runnable only when every point it must address (§4.6) has a covering passage in state or its reach is from
the user's own words. Stop, subject-named and the fetch filter do not count. When the predicate holds and the
request is not done, the request is dispatched to nous (§7).

### 4.2 Context selection ("what does the writer need to see")
For each candidate chunk (recent turns, memory hits, operation notes, tool results): a yes/no "does answering need this",
optionally a Score {hide, one line, summary, full}. Code assembles the generator prompt from the YES items only. This is
the whole answer to "what do you think?": no parameter exists, only selection. Also the replacement for compaction:
nothing is thrown away; each request re-selects. In the proof (§15) this is the fetch filter only: one Noul per
fetched fragment at threshold 0.5, asked inside the triage request; the writer receives the kept fragments and the
message. Recent turns are fragments under the same filter, not a fixed part of the view: unjudged, an unrelated
previous request pulled "needs the web" on a Python question from 0.88 to 0.57 and made the voice parrot the old
reply (measured 2026-09-22, `bench/probe_need.py`). The four-level Score is deferred.

### 4.3 Tool selection
Two layers, both cheap: (a) always present, a one-line snippet per tool and habit (hundreds fit); (b) on demand, the full
schema of the chosen ones. The decision is one Noul per snippet, "run tool A now?", as §4.1 states, never a single
Choice, because several may run.
Replaces both "all schemas up front" (context cost, weak choice at high cardinality) and lazy `get_tools` searches by
a generative model.

### 4.4 Slot resolution
- **Enumerable** (effort level, layer, top-N, template, operation id, generator tier): direct Choice.
- **Reference** ("that picture", "the deck from Tuesday", "my team"): code enumerates constraint candidates from the
  words (a date span → a time window, "picture" → image extensions, a name → an owner); pneuma confirms each; a
  resolver filters indexed state by the confirmed constraints; a Choice over the survivors' metadata; low confidence →
  ask with the top candidates.
- **Open field** (a search query, a filename to create): candidates first, never generation first, and the seed is
  never picked. The ladder, every rung feeding the same confidence gate, and the gate asked as one yes/no per
  candidate, never one Choice over all of them (forty near-equivalent candidates split the probability mass so
  that nothing reaches 0.7; measured 2026-09-22, and §9.5 used per-candidate judgments): (1) attachments of the
  slot's type: one match fills the slot with no question, several are judged;
  (2) the user's own words, plus spans code enumerates from the message *and from state*: quoted strings, capitalised
  runs, dates and numbers, tokens rare against the user's own index, noun chunks (segmented for Chinese), and every
  entity the resolvers matched (a memory title, the operation's goal, an attachment name, a name from recent turns),
  capped near eight; (3) autocomplete on every span at once (60–220 ms each, in parallel, cached per span), where
  pneuma judges the completions and never the seeds, so a wrong seed only yields candidates that are rejected
  (measured: planted noise OFF_TOPIC at 0.96–1.00, §9.5); (4) the resolver over the index; (5) a generator proposing
  three or four candidates, psyche or nous by the fill table (§7); (6) ask, with the top candidates as the options.
  A first search query does not walk the ladder: the user's own words are the first search (the digest kept every
  checklist fact with plain words, §5), and the ladder runs for the follow-up query once the stop question has named
  an aspect with no passage. When "does the message name its subject?" is NO, rungs 2 and 3 are skipped: the subject
  is in recent turns or an operation, or it takes a generator to name it.
- **Prose** (a document section, a slide, an email body): the slot *is* the writer's output. Pneuma chooses its inputs
  (which sources, which template or habit) and the fill table of §7 chooses the writer; the output is verified and, if
  needed, escalated as §4.6 states, at most once before ask.
- **Which rungs apply** depends on the slot's type, so no rung is a wasted call: an enumerable slot uses its fixed set
  only; a file slot uses attachments, then the resolver over the file index, then ask; a query or a name walks the
  whole ladder. A rung that needs pneuma is one more request inside the round, so "one request per round" in §2.6
  and §3 means the triage request; the ladder adds at most one request per rung taken.

### 4.5 Concurrency
One yes/no per candidate action in a single request ("run search A now?", "search B?", "open URL C?"). Code runs every
YES together. Sibling questions never coordinate; anything that depends on a result is the next round. Speculative
fan-out (asking the conditional questions for every branch in round one) trades tokens for a saved round when latency
matters more than cents.

### 4.6 Stop, budget, verification
- Stop: "is the request satisfied by what is in state?" plus "is there an aspect with no supporting passage?" Both
  confident → present. Otherwise one more round, up to the cap, then present what exists with the gap stated.
- Verification of written text: the text is folded as a result, and the next round's decide request carries one
  Score per requested point (present / partial / absent) beside the stop questions. Code then decides by rule: a point
  absent with no passage in state that covers it → a targeted fetch round; a point absent or partial while a covering
  passage is in state → one rewrite, one rung up the order in §7, at most once, then present what exists with the
  gap stated in the text, never ask. When the digest labels a passage under every missing point as a possible
  disagreement, the rewrite is skipped, since no writer can settle what the sources disagree on (the ETIAS mandatory
  date cost 19 s to learn that). Beside the points, the same round asks one Score per representative passage of each
  aspect: does the text state what this passage answers (stated / missing)? Aspect points passed replies that dropped a
  sub-fact the writer had been given (the rat in Roxy's death, the fruit in a fibre list: 10 of 16 essential-fact
  misses on 2026-09-23); a passage is the finer point. Passages marked missing go back to the writer as points for one
  rewrite at the same tier, since the writer had them and a higher tier is unavailable when nous is not a writer;
  they are never footnoted. An aspect still partial or absent after the one rewrite (or with no rewrite available)
  is dispatched to nous with the draft and the missing points when pneuma answers, in the same verifying round, that
  more research could answer it and the sources do not disagree on it (a 106 s dispatch on 2026-09-24 chased family
  fates no source records); only what the
  agent's answer still misses is footnoted. An agent that fails leaves the draft standing. A prose written before a later tool result is stale: it neither ends the request nor is presented. Done is code: a prose that passed every point ends the request on its own,
  because "satisfied" at 0.85 rarely passes and re-writing is the most expensive move the loop has (measured
  2026-09-22: six writes at 30 s each before the rule). Otherwise done is the satisfied answer AND every point
  present. The points come from state: for a digest, its aspects; for other prose, one point per slot the request
  named (the file summarised, the thing noted), "the text addresses X". With no points there is nothing to verify,
  so the prose ends the request unless pneuma is confident the request is not satisfied. Neither ends it while
  pneuma passes a tool run in the same round: a verified reply to "find X and save it as a note" still has the note
  to write (a write_note passed at 0.95 was dropped this way on 2026-09-23).
- The expert checklist (`EXPECT_CHECK`, on in the release default). The aspects come from the digest, so they cannot
  reveal what the digest never fetched: Jev marked Python's limitations covered in every run while two expected
  limitations were absent. At the first verification of a request, psyche lists what a complete, expert answer must
  settle, as 3 to 8 questions (prompts/expect.md, about 1 s); the same verifying round asks Jev, per item, whether the
  reply gives the specific answer (answered / missing / not needed). Asked only whether the reply "answers" an item,
  Jev accepted topic-level mentions; asked for the concrete thing named, it marked the gaps. Confidently missing items
  go to nous with the draft when Jev says more research could answer them, and are never footnoted. Measured
  2026-09-24: python313 went from 3 to 5 of 7 essential facts to 7 of 7 in the three of six runs where it dispatched.
- Budget: a hard cap on rounds and wall time per request, reported in the trace. No "stopped at this turn's limit"
  message appended to a half-finished answer; if the cap is hit, the answer says which aspect is missing.
- Exits: done and something to say → reply; the user must decide → ask, always with options; nothing to say → end,
  which renders nothing. Psyche renders all three.

### 4.7 Operation gate (once, before the first round)
"Does this message continue operation X?" asked once per open or legacy operation in the roster, with the message and
the operation's goal and latest note as state; attach only on a confident YES. Then "will this work outlive this
exchange?" (Noul); a confident YES opens a new operation. Neither → a plain request. Nothing after the gate can attach
or open an operation (user ruling 2026-09-22). The v1 failure (research attached to an unrelated fantasy-team
operation) is exactly the absence of the first question, and it is a regression test in the proof (§15).

### 4.8 Learning
After presentation, from the recorded trace: "was this a deterministic workflow" (Score), "did the user accept the
result" (from explicit signals only), "which steps are replayable with typed bindings". Drafts a habit; verification
against independent cases and promotion are separate, later, and never block a foreground request. Drafting is
generative and runs in a Codex session after acceptance, from an accepted trace whose steps are replayable;
verification against a second run and promotion are code; a third run must replay with no nous. Habits that go
unused or start failing are retired. In the proof, acceptance is a separate invocation, `nyx --accept <trace>`,
which marks the trace and starts drafting for it; the bench runner calls it after a row's check has passed, and no
implicit signal is inferred. Drafting is a Codex session given the accepted trace and the habit schema; it returns a
habit: trigger phrases and ordered tool steps with typed slot bindings: a literal, a span of the message, a previous
step's result, or, for a prose slot, a writer tier with its source steps. Verification is code, on the next
`--accept`: the draft reproduces that run's tool calls, same tools in the same order, every non-prose slot resolving
to the same value, every prose slot bound to the same tier and sources (its text is checked by §4.6's points as in
any run); then it is promoted, and only a promoted habit is fetched. Two relaxations, both measured 2026-09-22 on
runs that took the same path and still failed: the trace records where each slot value came from (attachment,
words, candidates, plan, proposed, resolver), and no binding is compared against a value that was a generator's
proposal, whether a psyche proposal or a nous plan value, since two proposals never repeat verbatim and the habit's
own binding is what replays (a span-bound title against a proposed "Q4 2026" retired an otherwise identical run, and
a plan-filled query did the same on 2026-09-23); and a prose binding is compared by its source
steps only, because the tier is pneuma's momentary reach and exposure answer, not part of the workflow. Each
`--accept` first verifies any pending draft against the accepted trace, then drafts from it; a trace with a dispatch does neither, since an agent session is not a replayable workflow of catalog tools. No pneuma question is asked in learning in the
proof; the three questions above are deferred. "Independent cases" in the proof means the same task run three times.

---

## 5. The read primitive: digest

`jev-digest` ([github.com/pr0ta9/jev-digest](https://github.com/pr0ta9/jev-digest), depended on as a package, not vendored) is the one web capability. It searches
(SearXNG, with a batch of queries run in parallel and merged), fetches in parallel with a 2 s cutoff and a bounded
browser second wave, splits pages into 2–4 sentence passages, and runs two decision rounds: per page, every passage gets
a relevance level and an aspect; per aspect, every kept passage is judged COVERED / ADDS / CONFLICTS against the top
three representatives. Output (`digest_evidence`, since 2026-09-23) is original text grouped by source page with its
URL, each passage labelled with the aspect it answers and "possible disagreement" where it conflicts, up to five
passages per aspect shown (about 1,500 tokens) and the rest counted but withheld; the result also carries the
representatives per aspect as data, which §4.6 verifies against. The earlier full layer (22k to 44k characters
grouped by aspect) is gone.

What it is for in v2: the `digest` tool produces one digest per confident "run digest now?" (§4.1), one round each, the first with the
user's own words and a follow-up only when the stop question names an aspect with no passage (§4.4); a reference to a
specific URL produces a single-page digest for the stated purpose. There is no "browse then summarize" loop and no per-page
generative summary. No other search or answer engine is called; the Google AI Mode row in §9.2 is a comparator, not
a method.

Measured (medians of four runs, cold cache, healthy SearXNG): 3.7–7.5 s to context; full layer kept every checklist fact
in sixteen of sixteen runs; decision-layer cost $0.004–0.017 per round; the two decision rounds take 1.2–1.9 s of that
and are flat in page count (1.6 s for 583 passages). Inside Nyx, routing the web tools through it took Rudeus from
444 s to 128 s and fiber/ETIAS from 74/69 s to 41/39 s with equal or better facts (§9.3).

Two lessons that shaped it and apply to every tool: **hand over URLs, not site names** (both coding agents opened
passages one by one to get URLs to cite until the footer listed them), and **the calling agent's habits set its time**,
so v2's controller, not the tool, must own the round count.

---

## 6. Operations and memory

**Operations are long-lived.** User ruling 2026-09-22: operations must support long-term projects; closed (legacy)
operations remain visible to the controller and to Nyx at lower priority than open ones; the open window is 72 hours.
v1 facts to reconcile before numbers are set: `IDLE_CLOSE_MINUTES = 45` auto-closed an open operation to completed after
45 idle minutes; terminal operations vanished from the roster entirely; no 48-hour constant existed anywhere, so the
observed "gone within 48 hours" came from those rules together. Deferred past the proof: how an operation leaves the
72-hour window, and whether attaching to a legacy operation reopens it.

**Roster as state.** Every request's state includes the operations roster: open first, legacy after, each with goal and
latest note. Attach is a gated decision (§4.7), never a prompt instruction.

**Effects flow back.** An operation's actions (a roster change, a scheduled job's result, a failure) are written as
typed events that (a) enter Nyx's state on the next request and (b) can trigger a notification decision ("does the
user need to hear this now?" Choice over channels). v1's cron jobs acted daily without Nyx knowing or telling the
user; the notification path is a first-class tool in v2.

**Memory** keeps v1's durable store and rebuildable index; retrieval takes the raw message and recent turns; the
decision layer judges the hits (§4.2) so a weak embedding is a recall problem, not a precision problem.

---

## 7. Psyche and nous

Both are Codex sessions started by code (`codex exec`), stateless across requests: state goes in with every call, no
resumed threads between requests. Psyche runs Luna at low effort by default; nous runs the strong Codex model. Neither
calls a tool; if facts are needed, the controller fetched them first. Inputs are assembled by §4.2 and §4.4; outputs are
verified by §4.6.

**Which one writes, and at what effort.** Taken from jev-codex-pilot, which never asks Jev "which model": Jev answers
two bounded questions and a code table maps the pair to a model and a reasoning effort. Here pneuma scores, inside the
triage request, the **reach** of the text needed and its **exposure**, and code looks up the cell:

| reach ↓ · exposure → | internal (a query, a name) | user-visible (a reply, a note) | external or irreversible (an email, a post, a command) |
|---|---|---|---|
| from the user's own words | psyche · low | psyche · low | psyche · high |
| from one thing in state | psyche · low | psyche · high | nous · medium |
| from several things in state | psyche · high | nous · medium | nous · high |

- Escalation is one rung, once, after a failed check: pneuma's per-point verification (§4.6) fails, the fill moves to
  the next entry of one ordered list, psyche·low → psyche·high → nous·medium → nous·high, and the retry runs. The
  pilot's rule verbatim: "model escalation requires repeated failed verification". Never swap the writer inside a
  composition (Almeida's KV-cache argument, §11).
- The nous cells are an exposure judgment, not a difficulty judgment, and `NOUS_SCOPE=planning` collapses them to
  psyche·high so that nous never writes. Measured 2026-09-22 (bench/questions.md): with Mercury 2.5 as psyche that
  setting lost no hand-scored facts on the four benchmark questions and brought a request down to 7 to 12 seconds.
- Effort is a rung only where the model has one. v1 already passes a reasoning-effort setting to its worker and the
  pilot drives Luna with the same setting; a psyche model without the dial collapses the table to two columns.
- Reply, ask and end are always rendered by psyche. When nous composed, psyche phrases; it does not rewrite.
- Nous is dispatched when the no-move predicate of §4.1 holds, or when a checked aspect stays missing (§4.6). It is
  a full agent: `codex exec` in `vault/work/<trace id>/` with `--sandbox workspace-write` (on Windows also
  `windows.sandbox="elevated"`, without which every command is blocked), its own web search, and prompts/dispatch.md
  as its brief: the request, kept context, results so far, and after a failed check the draft and the missing points.
  There is no timeout: an agent returns an answer or an error (full agents measured up to 442 s on one question). The
  answer is folded twice, as a tool result that later writes can cite and as the draft pneuma verifies on the same
  points; psyche renders it. Files the agent wrote are listed in the trace and indexed from `vault/work/`; the agent
  never writes memory, habits or operations, which stay the harness's. An error ends in ask ("try again" /
  "never mind"). The model is `DISPATCH_MODEL` (Luna by default; it scored 29 of 29 as a full agent on the §15
  questions) or `NOUS_MODEL` when pneuma marks the output as external or irreversible.
- Codex writers run blind. `codex exec` for psyche and for nous composing starts in an empty scratch directory with `--sandbox read-only`
  and `--json`; code reads the event stream and discards any result whose events include a command or tool call,
  recording the discard in the trace. That is the check behind "Codex touched no tool" in §15, and it is code, not a
  prompt instruction (§2.10). Web search stays on in `codex exec` even with user config ignored, so sessions also run
  with `web_search="disabled"`: Astra at high effort searched during a rewrite on 2026-09-24 and its discarded result
  would have replaced a passing draft. A discarded or empty rewrite never replaces the draft it was rewriting.
- Latency honesty: a round is a second; a composition takes what the writer takes. Process start for `codex exec` is
  measured in the proof (§15) before it is relied on.

---

## 8. Ingestion (a precondition, not a feature)

Everything a resolver can later find must be described when it arrives:

- Files and attachments: filename, EXIF/creation date, origin (camera, upload, download), a caption for images, OCR text
  for images and PDFs, all indexed with the conversation turn they arrived in.
- Conversations: episodic summaries with topic tags, plus the raw turns retrievable by time and mention.
- Operations: goal, code name, latest note, events, all searchable.
- Tools and habits: one-line snippets for §4.3 and full schemas on demand.

Cost: cheap and asynchronous. Without it, "that picture I took back in December" is unresolvable by any controller.

---

## 9. Evidence

### 9.1 Decision layer (Jev 1.13)
Choice ≤ 255 options; questions in one request are independent and answered together; 0.2–0.8 s per request measured;
$0.042 per million input tokens, output free; about 300 input tokens per question asked (each carries its passage, the
options and the aspect names). Answers are validated (choice must equal the argmax; rounded ties retried once). The
ladder experiment (`the private v1 research notes`) established anchoring: an 8-field game with
sibling fields expected to coordinate looped; anchored rounds did not.

### 9.2 Digest vs the field (one question set, 2026-09-21/22)
| System | Time to context or answer | Facts (4 questions) |
|---|---|---|
| digest, full layer | 3.4–10 s (medians 3.7–7.5) | 7/7, 8/8, 7/7, 13/13 |
| Google AI Mode (answer) | 4.5–10.5 s | 6/7, 7/8, 6/7, 11/13 |
| Claude Code native (answer) | 18–135 s | 6, 6, 6, 13 |
| Codex CLI native (answer) | 42–286 s | 6, 4, 6, 13 |
| local LLM extraction, same URLs | 12–52 s | 7, 8, 7, 5 |
| cross-encoder page rerank | 3–4 s | 3, 6, —, — |

### 9.3 Nyx (v1) with and without the digest as its web tools
| Question | Native | Web tools return the digest |
|---|---:|---:|
| fiber | 74 s, 6/8 | 41 s, 7/8 |
| etias | 69 s, 6/7 | 39 s, 4/7 (regex + a hedge on the launch date) |
| rudeus | 444 s, 12/13 | 128 s, 12/13 (27 s research, 100 s writing) |
| python313 | 92 s, 7/7 | 120 s, 7/7 (routed to the L4 writer that run) |

The SPIRE operation (v1 native L4, 2026-09-20): 58 turns, one tool call each, 1,137 s; 562 s of model time, 574 s of
tools of which 307 s were twelve page summaries at a median 31.5 s.

### 9.4 Coding agents given the digest (Claude Code, Codex)
Fewer rounds and a third of the tokens on real research; no speed-up, because their own deliberation and writing set the
clock and they re-verified until the digest carried URLs. Full tables: jev-digest's benchmark notes (not published).

### 9.5 Parameters without a generator
SearXNG autocomplete returns topic aspects in 60–220 ms (ETIAS → start date, application, 2026, visa; 老鲁迪 → 日记,
时间线). One decision request filtered 15 candidates with 5 planted noise items in 0.82 s: all noise rejected at
0.96–1.00, best picks 0.88–0.90, vague ones at 0.24–0.29 (below any gate). Cost $0.0002.
`the private v1 research notes`.

---

## 10. What v2 takes from v1, and what it leaves

**Takes:** the vault idea, durable markdown plus a rebuildable index; the habit concept with typed whole-value
bindings and draft → verify → promote; the permission model for dangerous tools; the gateway protocol shape for
clients (after the proof); SearXNG operations knowledge (jev-digest's `docker/` configuration).

**Leaves:** the identity files (SOUL/IDENTITY/USER) and every personal fact in them, since v2 is to be open-sourced
(§14); the L1–L4 cascade and its classifier; prompt-instructed decisions (attach, stop, tool choice); the browse
summarizer; compaction; token-budget wrap-ups that append "unfinished" to answers; MCP servers as a way to give Nyx
capabilities (an optional tool competes with habits and loses; capabilities are tools the controller routes to); the
three naming generations; the word "executor"; any web read that is not the digest.

**Defects recorded in v1 that v2 must not reproduce:** attach without a gate; STOPPED_EARLY after nearly every message
(budgets exceeded, wrap-up request failing on an empty tools array); scheduled jobs acting without reaching Nyx's
awareness or the user; operations auto-closing on a 45-minute idle timer.

---

## 11. Related reading and how it bears on this design

- **TypeSafe, "How to build with System One"** (docs.typesafe.ai/concepts/how-to-build-with-system-one): code owns
  control flow; narrow independent questions; confidence gating; "agent loops introduce another opportunity to go off
  the rails". This design is that doctrine applied to a personal assistant.
- **Diogo Almeida, "The Tyranny of the KV Cache" (notes, 2026-09-21).** Agrees on decomposition, tool routing over
  snippets, and query-aware filtering instead of compaction. Adds three things adopted here: do not switch generator
  tiers mid-session (§7); "meta-attention", a per-chunk show/summarize/hide decision that is §4.2 generalized to the
  whole context; explicit state shared by read-only background tasks (§6, §8). He does not propose the decision model
  planning multi-step actions; nothing there conflicts with §2.2.
- **jev-digest benchmarks and agent traces** (jev-digest's benchmark notes, not published): the evidence for §5 and for "the caller's
  habits set the time".

---

## 12. Sources for every number above

| Claim | Where |
|---|---|
| digest medians, fact counts, costs, agent tables | jev-digest benchmark notes and results (not published) |
| Nyx native vs digest-routed, SPIRE split | `the private v1 research notes` |
| classifier timing, L2/L4 facts, browse summarizer cost | `the private v1 research notes` |
| anchoring / field decoherence | `the private v1 research notes` |
| filter-merge harness (digest design) | `the private v1 research notes` |
| search latency baselines | `the private v1 research notes` |
| autocomplete + candidate filtering | `the private v1 research notes` |
| user rulings and design notes, dated | `the private v1 design notes` (2026-09-22 entries) |
| v1 constants cited (IDLE_CLOSE_MINUTES, roster, STOPPED_EARLY) | `the private v1 source`, `cascade/router.py`, `the private v1 L3 module` |

---

## 13. Decisions taken and still open

1. Decided: pneuma is Jev over HTTP. Psyche is a Codex session (`codex exec`, Luna at low effort) or Mercury 2.5
   over HTTP (`PSYCHE_PROVIDER=mercury`; measured 2026-09-22 as equal on facts at 1 to 3 s per call against a
   4.8 s Codex start floor). Nous is a dispatched Codex agent (`DISPATCH_MODEL`, Luna by default; `NOUS_MODEL`, Astra
   by default, for external output). With `NOUS_SCOPE=planning` nous never composes and psyche writes every reply;
   that is the release default.
2. Decided for the proof: the digest is a package dependency.
3. Thresholds per question class, taken from jev-codex-pilot and jevgrep and revised from traces: fetch filters 0.5
   (recall questions); habit, tool, prose-needed, subject-named and ladder Choices 0.7; attach,
   outlives-this-exchange and stop 0.85. Scores (reach, exposure, verification) take the argmax; below 0.5
   confidence, reach and exposure fall to the cheaper cell. No permission question in the proof: the reflex is code
   (§15); after the proof a shell-gate question at 0.75 may advise, and its allow never overrides the code deny-list.
   Timeouts 1.2 s per decision request; on timeout the fetch filter fails open (keep everything), and triage, gate
   and stop retry once and then take the ask exit.
4. For the proof, ask prints its options in the CLI.
5. No migration: the persona is new and the vault ships empty apart from examples.
6. Ingestion captioning is outside the proof.
7. For the proof: never. A dispatched agent writes only in its work folder and cannot open an operation.

---

## 14. Persona

Nyx is new in v2. Nothing is copied from v1's SOUL, IDENTITY or USER files, which hold personal facts. v2 is written
to be open-sourced, so `prompts/voice.md` is fictional, and the repository never contains a real person's data:
`vault/` and `traces/` are ignored by git apart from shipped examples, and keys live only in environment variables.

Register: tsundere. Terse and mildly exasperated on the surface, competent underneath, warmer when the user is actually
in trouble. The bit never costs the user anything: every fact found is stated plainly, every ask lists its options,
end says nothing rather than something cute, and Nyx never pretends not to know what she knows. The voice is a
rendering rule psyche applies over what any part wrote. It holds no instructions about tools, operations or stopping,
because those are not the voice's to decide. Memory about the user lives in the vault, fetched like anything else,
never in the persona file.

---

## 15. Proof of concept

Purpose: prove §0's thesis, that pneuma plus code can own control flow end to end with the writers as tools, at one
second per round. None of the four Jev projects examined (jarviscore-framework, jevify, jevgrep, jev-codex-pilot) does
this; each keeps a generative planner or a human click in the loop. The proof is a CLI, `nyx "message" [files]`, that
prints Nyx's reply and the path of the trace. Backend only: not built are gateway, client or any UI, embeddings,
captioning, notify channels, MCP, emotion. The project name jev-agent and the persona Nyx are the release names
(renamed 2026-09-22; no earlier name remains in the repository). The research notes §12 cites stay in the private
v1 repository; the numbers quoted in this document are the published record of them.

Status 2026-09-24: every row below passes in five release runs (Mercury writing everything three times, Mercury with
Sol, Mercury with Astra), with questions isolated from recent turns and earlier vault contents; results, the scoring
rubric and the open findings are in bench/questions.md and docs/STATUS.md.

Acceptance set, each row with the check that decides it:

| request | check |
|---|---|
| fiber, etias, rudeus, python313 (§9.3) | facts at least equal to the digest-routed v1 run; time under 41, 39, 128, 120 s; every decision in the trace is a typed pneuma answer |
| "summarise this file", one text attachment | the attachment fills `read_file`'s slot with no question; psyche writes the summary (one source, user-visible: psyche · high) |
| "which file is that picture from December?" | the resolver fills the slot from the file index (name, dates, extension), or ask lists the top candidates |
| an operation continuation | the gate attaches to the right open operation and refuses the v1 Rudeus-into-ESPN case |
| "find the current ETIAS start date and save it as a note", no habit exists | completes through `digest` then `write_note` in three rounds (§3); the note holds the date; every tool run was assented by pneuma |
| the same request with tool snippets withheld from fetch (bench switch `--withhold-tools`), so the no-move predicate holds by construction; not accepted | the request is dispatched to nous; the agent's files are all under `vault/work/<trace id>/`, where the harness finds them; a reply is presented; the run is never drafted into a habit |
| the same request a third time, plain, then `nyx --accept` | the draft from the first run reproduces this run's tool calls and is promoted (the withheld run is a different path and is never accepted) |
| the same request a fourth time | replays as a habit with no nous, faster and cheaper, with the numbers in the trace |

Tools in the proof, with their slot types (§4.4): `digest` (query: open field), `read_file` (path: file),
`list_files` (folder: file), `write_note` (title: open field; content: prose, so psyche writes it and §4.6 checks
it), each writing only under `vault/`, which is the permission reflex. Notify and shell come after the proof. Recent turns are the last six turns read from `traces/`,
which is all "session" means in the proof; an attached operation's latest note is written by present; the file index, owned by `vault.py` over `vault/files/`, holds name, dates, extension and the text of text
files, no captions; CLI attachments are copied there at ingest, which is how the bench seeds the December picture.

Build order, each step verified before the next: (1) state, trace and the pneuma client, tested offline against
recorded answers and once live; (2) the loop with reply-from-state (prose needed, no tool) and the digest, psyche
rendering, run against the four questions; (3) the ladder; (4) the vault and the gate, with the attach regression
test; (5) nous via Codex, with the `--withhold-tools` switch; (6) `--accept` and learn via Codex. Step 2 is the
thesis test and comes second on purpose.

---

## 16. Code structure

Python, one flat package, one file per box on the chart, one public function or class per file.

```
jev-agent/
  docs/DESIGN.md
  prompts/            voice.md (§14, render and propose), compose.md (writers), dispatch.md (nous), habit.md (learn's drafting)
  vault/              memory/*.md  habits/*.yaml  ops/*.md  tools/*.md  files/  work/   (git-ignored apart from examples)
  traces/             one .jsonl per request                                        (git-ignored)
  bench/              questions.md (the acceptance set), run.py
  tests/              one test_*.py per module; fixtures/ of recorded pneuma answers and recorded Codex output
  soma/
    settings.py       keys, URLs, model names, thresholds
    state.py          typed State and fold()
    trace.py          JSONL write and replay
    pneuma.py         Jev client: batch, confidence, "none", timeouts (a verdict cache comes after the proof)
    questions.py      every question the loop asks: gate, fetch filter, triage, ladder, verification, done; the fill table of §7
    vault.py          markdown notes + FTS5 index; fetch(state) → fragments with locations
    tools.py          run(name, slots) over digest, read_file, list_files, write_note; the permission reflex (writes only under vault/)
    ladder.py         fill(slot, state) → value or Ask; calls SearXNG's autocompleter directly
    psyche.py         class Psyche: render(exit), propose(); codex exec, Luna, low effort by default
    nous.py           dispatch(state) → the agent's answer and files; codex exec in vault/work/<trace id>/, stateless
    gate.py           the operation gate, once per request
    loop.py           ingest → fetch → gate → rounds → present → record
    learn.py          on --accept: verify a pending draft against this trace, promote or retire; then codex drafts from it
    cli.py            nyx "message" [files...] → reply, trace path;  nyx --accept <trace> → learn
```

| file | does | depends on |
|---|---|---|
| state.py | holds the request as typed data; fold() appends results and decisions | nothing |
| pneuma.py | asks Jev typed questions in one request, validates, gates by confidence | typesafe HTTP |
| questions.py | builds gate, fetch-filter, triage, ladder, verification and done questions from state; maps reach and exposure to a tier | state |
| vault.py | indexes notes, returns fragments with locations, never summaries | sqlite3 |
| tools.py | typed tool calls; refuses what the deny-list forbids | jev-digest, subprocess |
| ladder.py | walks the sources until pneuma is confident or asks | pneuma, questions, vault, psyche, SearXNG HTTP |
| psyche.py | speaks in Nyx's voice; proposes candidates | codex subprocess |
| nous.py | dispatches a full agent and collects its answer and files | codex subprocess |
| gate.py | attaches, opens, or neither | pneuma, questions, vault |
| loop.py | the round; owns budgets, concurrency and side effects | everything above |
| learn.py | runs on --accept; never in the foreground | codex, vault, trace |

Rules that hold the size:

- 1,600 source lines for the whole proof, tests excluded. A file past 200 lines is split only with approval.
- One public function or class per file; everything else is private.
- No decision outside `questions.py`. If a choice is not a question in that file, the system does not make it.
- No base classes, registries, plugin systems or config framework. Settings is a dataclass read from environment
  variables.
- Dataclasses, stdlib sqlite, subprocess for Codex. No agent framework; no pydantic unless the Jev SDK forces it.
- Nothing that is not in the acceptance set of §15.
- Prompts are files in `prompts/`, never strings in code. Comments only where the why is not obvious.
- Tests replay recorded pneuma answers; no mocks of our own modules.
- Nothing personal in the repository: `vault/`, `traces/` and keys stay out of git.
