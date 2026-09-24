"""Turns bench result tables and their traces into one readable page: per request, what each round decided and did.

usage: python bench/report.py OUT.html LABEL=results-file [LABEL=results-file ...]
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r"^\| (\S+) \| ([\d.]+) \| (.*?) \| (yes|NO) \| (\S+\.jsonl) \|$")
# Dollars per million tokens (in, out). Jev from typesafe.ai; Mercury 2.5 from inceptionlabs.ai; the Codex models are
# OpenAI list prices as recorded in v1's usage table, shown for scale: through the ChatGPT login they are subscription use.
PRICES = {"jev": (0.042, 0.0), "mercury": (0.04, 0.15), "luna": (1.0, 6.0), "astra": (10.0, 50.0)}
SOURCE = {"words": "the user's own words", "plan": "nous's plan", "proposed": "a psyche proposal", "candidates": "autocomplete or span candidates",
          "resolver": "the file index", "attachment": "the attachment", "default": "the default", "written": "written by a writer", "habit": "the habit"}


def rows_of(results: Path) -> dict:
    out = {}
    for line in results.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line.strip())
        if m:
            out[m.group(1)] = {"seconds": float(m.group(2)), "result": m.group(3), "pass": m.group(4) == "yes", "trace": ROOT / "traces" / m.group(5)}
    return out


def tok(u: dict) -> dict:
    return {"in": u.get("input_tokens") or u.get("prompt_tokens") or 0, "cached": u.get("cached_input_tokens") or 0,
            "out": u.get("output_tokens") or u.get("completion_tokens") or 0}


def esc(s) -> str:
    return html.escape(str(s))


def cost(kind: str, u: dict) -> float:
    pin, pout = PRICES[kind]
    return (u["in"] * pin + u["out"] * pout) / 1e6


def money(x: float) -> str:
    return f"${x:.4f}" if x < 0.01 else f"${x:.3f}"


def said(a: dict) -> str:
    """One sentence for what pneuma decided in a triage request."""
    parts = []
    p = {k: v for k, v in a.items() if v["passed"]}
    tools = [k[6:] for k in p if k.startswith("tool__") and p[k]["choice"] == "RUN"]
    habits = [k[7:] for k in p if k.startswith("habit__") and p[k]["choice"] == "FITS"]
    if habits:
        parts.append(f"habit {habits[0]} fits")
    if "need" in p:
        parts.append({"WEB": "the message needs web facts", "VAULT": "it needs something from the vault", "WRITE": "it needs a note written", "STATE": "nothing more is needed"}[p["need"]["choice"]])
    if tools:
        parts.append("run " + ", ".join(tools))
    if p.get("prose", {}).get("choice") == "NEEDED":
        parts.append("text is needed" + (f", reach {a['reach']['choice'].lower()}" if "reach" in a else ""))
    pts = [k for k in a if k.startswith("point__")]
    if pts:
        present = sum(1 for k in pts if a[k]["choice"] == "PRESENT")
        parts.append(f"checked the text: {present} of {len(pts)} points present" + ("" if present == len(pts) else " (" + ", ".join(a[k]["choice"].lower() for k in pts if a[k]["choice"] != "PRESENT") + ")"))
    if p.get("satisfied", {}).get("choice") == "YES":
        parts.append("the request is satisfied")
    near = [f"{k.replace('tool__', '')} {v['choice']} at {v['confidence']:.2f}" for k, v in a.items() if not v["passed"] and (k.startswith("tool__") and v["choice"] == "RUN" or k in ("need", "prose") and v["choice"] != "NO")]
    text = "; ".join(parts) or "nothing confident"
    if near:
        text += f" · below the gate: {', '.join(near)}"
    return text


def narrate(events: list[dict]) -> dict:
    t0 = events[0]["t"]
    message = next(e["text"] for e in events if e["kind"] == "message")
    rounds, cur, pre, reply = [], None, [], None
    tot = {"jev": 0, "jev_in": 0, "jev_cost": 0.0, "w_calls": 0, "w_s": 0.0, "w_in": 0, "w_cached": 0, "w_out": 0, "w_cost": 0.0}
    prev = t0
    for e in events:
        dt, at = e["t"] - prev, e["t"] - t0
        prev = e["t"]
        k = e["kind"]
        if k == "decide":
            u = tok(e.get("usage", {}))
            tot["jev"] += 1
            tot["jev_in"] += u["in"]
            tot["jev_cost"] += cost("jev", u)
        if k == "decide" and e.get("what") == "triage":
            cur = {"n": e["round"], "at": at, "jev_s": dt, "jev_in": tok(e.get("usage", {}))["in"], "questions": e.get("questions", len(e["answers"])), "said": said(e["answers"]), "acts": []}
            rounds.append(cur)
            continue
        target = cur["acts"] if cur else pre
        if k == "gate":
            target.append({"kind": "gate", "text": f"Operation gate: {'attached to ' + e['operation'] if e.get('operation') else 'no operation attached or opened'}."})
        elif k == "fetch":
            target.append({"kind": "fetch", "text": f"Fetched {len(e['fragments'])} fragments from the vault" + (": " + ", ".join(e["fragments"][:5]) if e["fragments"] else "") + "."})
        elif k == "decide" and e.get("what") == "pick":
            fits = [f"{v['confidence']:.2f}" for v in e["answers"].values() if v["choice"] == "FITS" and v["passed"]]
            target.append({"kind": "pick", "text": f"Ladder: pneuma judged {len(e['answers'])} candidates, {len(fits)} fit" + (f" (best {max(fits)})" if fits else "") + f", {dt:.1f} s."})
        elif k == "tool":
            filled = e.get("filled") or {}
            slots = "; ".join(f"{s} = {json.dumps(v, ensure_ascii=False)[:120]} ← {SOURCE.get(filled.get(s, 'habit' if 'habit' in e else '?'), filled.get(s))}" for s, v in e["slots"].items() if s != "content")
            if "content" in e["slots"]:
                slots += f"; content ← {'the habit' if 'habit' in e else 'a writer'}"
            outcome = f"{len(e.get('points', []))} aspects, {len(e.get('text', ''))} chars back" if e["name"] == "digest" else f"{len(e.get('text', ''))} chars"
            target.append({"kind": "tool", "text": f"Ran {e['name']}{' from the habit' if 'habit' in e else ''} in {dt:.1f} s: {slots}. Result: {outcome}.", "pre": e.get("text", "")[:500] if e["name"] != "write_note" else e.get("text", "")[:500]})
        elif k == "codex":
            u = tok(e.get("usage", {}))
            model = "astra" if e["tier"][0] == "nous" else ("mercury" if "prompt_tokens" in e.get("usage", {}) else "luna")
            c = cost(model, u)
            tot["w_calls"] += 1; tot["w_s"] += e.get("seconds", 0); tot["w_in"] += u["in"]; tot["w_cached"] += u["cached"]; tot["w_out"] += u["out"]; tot["w_cost"] += c
            who = {"astra": "nous (Codex gpt-6-astra)", "luna": "psyche (Codex gpt-5.6-luna)", "mercury": "psyche (Mercury 2.5)"}[model]
            target.append({"kind": "writer", "text": f"{who} · {e['what']} at {e['tier'][1]} effort: {e.get('seconds', 0):.1f} s, {u['in']:,} tokens in ({u['cached']:,} cached), {u['out']:,} out, {money(c)} at list price."})
        elif k == "prose":
            target.append({"kind": "prose", "text": f"Text written ({'/'.join(e['tier'])}, {e['chars']} chars) to cover: {', '.join(e['points']) or 'no listed points'}.", "pre": e.get("text", "")[:700]})
        elif k == "dispatch":
            target.append({"kind": "dispatch", "text": f"Dispatched to a full agent ({e['model']}): {e.get('seconds', 0):.1f} s"
                           + (f", error: {e['error']}" if e.get("error") else f", files written: {', '.join(e.get('files') or []) or 'none'}") + "."})
        elif k == "habit":
            target.append({"kind": "habit", "text": f"Habit {e['id']} replayed its {e['steps']} steps; the request ends here."})
        elif k == "reply":
            reply = {"exit": e["exit"], "text": e["text"], "rounds": e.get("rounds"), "at": at}
    return {"message": message, "pre": pre, "rounds": rounds, "reply": reply, "tot": tot}


CSS = """
:root{--bg:#f5f6f9;--bg2:#fff;--ink:#1b1d25;--mut:#646979;--line:#d6d9e2;--acc:#2b66cc;--ok:#2e7d4f;--no:#b3261e}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#14161c;--bg2:#1c1f27;--ink:#e7e8ee;--mut:#9ba0b0;--line:#2e3240;--acc:#6f9ff2;--ok:#6cc48f;--no:#f08a80}}
:root[data-theme="dark"]{--bg:#14161c;--bg2:#1c1f27;--ink:#e7e8ee;--mut:#9ba0b0;--line:#2e3240;--acc:#6f9ff2;--ok:#6cc48f;--no:#f08a80}
body{background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:14.5px;line-height:1.55;padding-block:24px 60px;padding-inline:20px}
.wrap{max-width:900px;margin:0 auto}h1{font-size:24px;font-weight:600;margin:0 0 6px}h2{font-size:20px;font-weight:600;margin:40px 0 4px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:15px;font-weight:600;margin:18px 0 6px;color:var(--acc)}p{margin:0 0 10px}.lede{color:var(--mut)}
blockquote{margin:0 0 10px;padding:8px 12px;border-left:3px solid var(--acc);background:var(--bg2);border-radius:4px}
.sum{font-size:13px;color:var(--mut);margin:0 0 10px}.sum b{color:var(--ink)}.pass{color:var(--ok);font-weight:600}.fail{color:var(--no);font-weight:600}
ol.rounds{padding-left:22px;margin:0 0 10px}ol.rounds>li{margin-bottom:10px}ol.rounds ul{margin:4px 0 0;padding-left:18px}ol.rounds li li{margin-bottom:3px;color:var(--ink)}
.pne{font-weight:600}.k{color:var(--mut);font-size:12.5px}
pre{white-space:pre-wrap;background:var(--bg2);border:1px solid var(--line);border-radius:6px;padding:8px 10px;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;margin:4px 0 6px;max-height:200px;overflow:auto}
pre.reply{max-height:none;font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:14px;background:var(--bg2)}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0 14px}th,td{text-align:left;padding:5px 8px;border-top:1px solid var(--line);vertical-align:top}th{border-top:0;color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.03em}td.n{text-align:right;white-space:nowrap}
.tbl{overflow-x:auto}details{margin:4px 0}summary{cursor:pointer;color:var(--mut);font-size:13px}
"""


def comparison() -> list[str]:
    """Every agent on the four questions: hand-scored facts against the Google rubric, time and cost, then totals."""
    base = json.loads((ROOT / "bench/baselines.json").read_text(encoding="utf-8"))
    hand = json.loads((ROOT / "bench/hand-scores.json").read_text(encoding="utf-8"))
    g = hand["google"]
    agents = [a for a in hand["scores"] if a in base]
    head = "<tr><th>agent</th><th>essential facts</th><th>full Google rubric</th><th>seconds</th><th>model calls</th><th>tokens in (cached)</th><th>out</th><th>cost at list</th></tr>"
    out = ["<h2>Comparison</h2><p class='lede'>The four fact questions through full agents with their own web search (Codex Sol, Codex Astra, Claude Sonnet and Claude Fable, each isolated in an empty directory) and through Nyx in four configurations. "
           "The rubric is Google AI Mode's own answer to the same question (bench/reference-google.md); Google is the rubric, not a competitor. "
           "<b>Essential facts</b> are the Google items that directly answer a sub-question the user asked; <b>full Google rubric</b> is every fact Google stated, including context. Both are scored by hand; a fact stated wrongly does not count. "
           "Claude Code reports zero server searches even when the reply cites ten URLs, so its call count (turns) is the honest search signal; Nyx's call count is Jev requests plus writer calls.</p>"]
    tot = {a: {"ess": 0, "ref": 0, "seconds": 0.0, "calls": 0, "cost": 0.0, "in": 0, "out": 0} for a in agents}
    ess_n = ref_n = 0
    for key, q in g["questions"].items():
        items, e = q["items"], g["essential"][key]
        keep = set(e["keep"])
        ess_n += len(keep); ref_n += len(items)
        lis = "".join(f"<li>{'<b>' if i + 1 in keep else ''}{esc(it)}{'</b>' if i + 1 in keep else ''}{'' if i + 1 in keep else ' <span class=k>(context: ' + esc(e['dropped'].get(str(i + 1), '')) + ')</span>'}</li>" for i, it in enumerate(items))
        out.append(f"<h3>{esc(key)} · {len(keep)} essential facts of {len(items)} Google stated</h3><blockquote>{esc(base[agents[0]][key].get('query', '') or '')}</blockquote>"
                   f"<details><summary>rubric items (bold = essential)</summary><ul class='k'>{lis}</ul>{('<p class=k>Borderline: ' + esc(e['borderline']) + '</p>') if e.get('borderline') else ''}</details><div class='tbl'><table>{head}")
        for a in agents:
            r = base[a].get(key)
            es, rs = g["scores_essential"].get(a, {}).get(key), g["scores"].get(a, {}).get(key)
            if not r or es is None:
                continue
            t = tot[a]
            t["ess"] += es; t["ref"] += rs or 0; t["seconds"] += r["seconds"]; t["calls"] += r["calls"]; t["cost"] += r["cost"]; t["in"] += r["usage"]["in"]; t["out"] += r["usage"]["out"]
            out.append(f"<tr><td>{esc(a)}</td><td class='n'>{es}/{len(keep)}</td><td class='n'>{rs}/{len(items)}</td><td class='n'>{r['seconds']:.1f}</td><td class='n'>{r['calls']}</td><td class='n'>{r['usage']['in']:,} ({r['usage']['cached']:,})</td><td class='n'>{r['usage']['out']:,}</td><td class='n'>{money(r['cost'])}</td></tr>")
        out.append("</table></div>")
    out.append(f"<h3>Totals over the four questions</h3><div class='tbl'><table>{head}")
    for a in agents:
        t = tot[a]
        out.append(f"<tr><td>{esc(a)}</td><td class='n'>{t['ess']}/{ess_n}</td><td class='n'>{t['ref']}/{ref_n}</td><td class='n'>{t['seconds']:.0f}</td><td class='n'>{t['calls']}</td><td class='n'>{t['in']:,}</td><td class='n'>{t['out']:,}</td><td class='n'>{money(t['cost'])}</td></tr>")
    notes = [f"<li>{esc(a)}: {esc(hand['scores'][a]['note'])}</li>" for a in agents if hand["scores"][a].get("note")]
    notes += [f"<li>{esc(a)} misses essential facts: {esc(m)}</li>" for a, m in g.get("misses_essential", {}).items() if a in agents]
    notes += [f"<li>{esc(a)} misses on the full rubric: {esc(m)}</li>" for a, m in g.get("misses", {}).items() if a in agents]
    out.append("</table></div><ul class='k'>" + "".join(notes) + "</ul>")
    return out


def render(runs: dict[str, dict]) -> str:
    labels = list(runs)
    rows = list(runs[labels[0]])
    out = ['<title>Nyx Request Walkthroughs</title>',
           '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono&display=swap">',
           f"<style>{CSS}</style><div class='wrap'><h1>Each request, round by round</h1>",
           "<p class='lede'>For every acceptance row: the message that was sent, then one entry per round saying what pneuma (Jev) decided, what code ran with which inputs and where each input came from, what a writer produced, and finally the reply the user saw. The same request is shown once per Nyx configuration. Costs are at list price per million tokens: Jev $0.042 in; Mercury 2.5 $0.04 in and $0.15 out; Codex Luna $1 and $6, Astra $10 and $50, which through the ChatGPT login are covered by the subscription and shown for scale.</p>"]
    out += comparison()
    out.append("<h2>Overview</h2><div class='tbl'><table><tr><th>request</th>" + "".join(f"<th>{esc(l)}</th>" for l in labels) + "</tr>")
    for r in rows:
        out.append(f"<tr><td>{esc(r)}</td>" + "".join(f"<td><span class='{'pass' if runs[l][r]['pass'] else 'fail'}'>{esc(runs[l][r]['result'])}</span> · {runs[l][r]['seconds']} s · {runs[l][r]['n']['tot']['jev']} Jev calls · {runs[l][r]['n']['tot']['w_calls']} writer calls</td>" if r in runs[l] else "<td>not run</td>" for l in labels) + "</tr>")
    out.append("</table></div>")
    for r in rows:
        first = runs[labels[0]][r]["n"]
        out.append(f"<h2>{esc(r)}</h2><blockquote>{esc(first['message'])}</blockquote>")
        for l in labels:
            d = runs[l].get(r)
            if not d:
                continue
            n, t = d["n"], d["n"]["tot"]
            out.append(f"<h3>{esc(l)}</h3><p class='sum'><span class='{'pass' if d['pass'] else 'fail'}'>{esc(d['result'])}</span> · <b>{d['seconds']} s</b> · {len(n['rounds'])} rounds · Jev {t['jev']} calls, {t['jev_in']:,} tokens in, {money(t['jev_cost'])} · writers {t['w_calls']} calls, {t['w_s']:.1f} s, {t['w_in']:,} in ({t['w_cached']:,} cached), {t['w_out']:,} out, {money(t['w_cost'])} at list price</p>")
            if n["pre"]:
                out.append("<ul class='k'>" + "".join(f"<li>{esc(a['text'])}</li>" for a in n["pre"]) + "</ul>")
            out.append("<ol class='rounds'>")
            for rd in n["rounds"]:
                out.append(f"<li><span class='pne'>Round {rd['n']}</span> <span class='k'>at {rd['at']:.1f} s · pneuma {rd['jev_s']:.1f} s, {rd['questions']} questions, {rd['jev_in']:,} tokens, {money(rd['jev_in'] * PRICES['jev'][0] / 1e6)}</span><br>Pneuma: {esc(rd['said'])}.")
                if rd["acts"]:
                    out.append("<ul>")
                    for a in rd["acts"]:
                        out.append(f"<li>{esc(a['text'])}" + (f"<details><summary>show text</summary><pre>{esc(a['pre'])}</pre></details>" if a.get("pre") else "") + "</li>")
                    out.append("</ul>")
                out.append("</li>")
            out.append("</ol>")
            if n["reply"]:
                rp = n["reply"]
                out.append(f"<p class='k'>Final exit: <b>{esc(rp['exit'])}</b> after {rp['rounds']} rounds, at {rp['at']:.1f} s.</p><pre class='reply'>{esc(rp['text']) or '(nothing rendered)'}</pre>")
    out.append("</div>")
    return "\n".join(out)


def main() -> int:
    target = Path(sys.argv[1])
    runs = {}
    for arg in sys.argv[2:]:
        label, _, path = arg.partition("=")
        table = rows_of(Path(path))
        for d in table.values():
            events = [json.loads(l) for l in d["trace"].read_text(encoding="utf-8").splitlines() if l.strip()]
            d["n"] = narrate(events)
        runs[label] = table
    target.write_text(render(runs), encoding="utf-8")
    print("wrote", target, {k: len(v) for k, v in runs.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
