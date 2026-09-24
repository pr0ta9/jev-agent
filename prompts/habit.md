Turn this trace of one completed request into a habit: a fixed workflow that replays the same tool calls for the
same kind of message with no reasoning in between. Output only YAML with keys id, status (always draft), trigger
(2-4 short phrasings of the message), steps (the tool calls in order). Each slot gets exactly one binding:
{literal: "..."} for a value that never changes, {span: "..."} for a value that is a substring of the message,
{step: N} for the text of an earlier step's output, {prose: {tier: [psyche|nous, low|medium|high], sources: [N...]}}
for a slot the trace shows was written by a writer from earlier step outputs. Use the tool names and slots exactly
as the trace shows. No prose outside the YAML. The exact shape, with the step key `tool` and the slot key `slots`:

id: example-habit
status: draft
trigger: ["phrasing one", "phrasing two"]
steps:
  - tool: digest
    slots: {query: {span: "words taken from the message"}}
  - tool: write_note
    slots:
      title: {literal: "A fixed title"}
      content: {prose: {tier: [psyche, high], sources: [0]}}

TRACE:
{{trace}}
