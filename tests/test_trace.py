from soma.trace import new_trace, read, recent_turns


def test_trace_round_trips_and_recent_turns_come_from_newest_files(root):
    t1 = new_trace(root / "traces")
    t1.write("message", text="first")
    t1.write("reply", text="one")
    t2 = new_trace(root / "traces")
    t2.write("message", text="second")
    t2.write("reply", text="two")
    events = read(t2.path)
    assert [e["kind"] for e in events] == ["message", "reply"] and "t" in events[0]
    turns = recent_turns(root / "traces", n=2)
    assert turns == [{"role": "user", "text": "second"}, {"role": "nyx", "text": "two"}]
