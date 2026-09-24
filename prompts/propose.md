Propose candidates for one input slot. Output only a JSON list of strings, 3 to 4 items, most likely first.
Each candidate is a complete, concrete value for the slot, taken from the message and the context where possible.

SLOT: {{slot}} ({{slot_type}})
NEED: {{need}}
MESSAGE: {{message}}
CONTEXT:
{{context}}
