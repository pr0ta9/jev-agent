from soma.state import Result, State, fold


def test_fold_appends_results_and_installs_an_ask():
    s = State(message="hi")
    fold(s, [Result("tool", "digest", {"query": "q"}, {"text": "d"}, round=1),
             Result("prose", "dispatch", {}, "answer", round=1)])
    assert [r.kind for r in s.results] == ["tool", "prose"]
    fold(s, [Result("ask", "ladder", {}, {"question": "which?", "options": ["a", "b"]}, round=2)])
    assert s.ask["options"] == ["a", "b"]


def test_view_shows_only_kept_fragments_and_summarises_results():
    from soma.state import Fragment
    s = State(message="hi", fragments=[Fragment("f1", "memory", "t1", "x" * 500, "memory/a.md"),
                                       Fragment("f2", "memory", "t2", "y", "memory/b.md")], kept=["f1"])
    fold(s, [Result("tool", "digest", {"query": "q"}, {"text": "digest body"}, round=1)])
    v = s.view()
    assert [k["id"] for k in v["kept"]] == ["f1"] and len(v["kept"][0]["text"]) <= 400
    assert v["results"][0]["name"] == "digest" and "digest body" in v["results"][0]["output"]
