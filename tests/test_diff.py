import io
import json

from dumputil.diff import multiset_diff, report, schema_diff


def test_multiset_ignores_order_counts_duplicates():
    a = [("t", "x"), ("t", "y"), ("t", "y"), ("u", "1")]
    b = [("t", "y"), ("t", "x"), ("t", "y"), ("u", "1"), ("u", "1")]
    d = multiset_diff(a, b)
    assert d["t"] == ({}, {})
    assert dict(d["u"][0]) == {} and dict(d["u"][1]) == {"1": 1}


def test_multiset_removed_and_added_and_group_only_on_one_side():
    d = multiset_diff([("t", "a"), ("t", "b"), ("only_a", "z")], [("t", "b"), ("t", "c")])
    assert dict(d["t"][0]) == {"a": 1} and dict(d["t"][1]) == {"c": 1}
    assert dict(d["only_a"][0]) == {"z": 1} and dict(d["only_a"][1]) == {}
    assert list(d) == ["only_a", "t"]


def test_schema_diff_positional():
    assert schema_diff(["a", "b"], ["a", "b"], "A", "B") == []
    out = schema_diff(["a", "b"], ["a", "c"], "A", "B")
    assert "-b" in out and "+c" in out


def test_report_text_and_json():
    content = multiset_diff([("t", "a"), ("s", "k")], [("t", "b"), ("s", "k")])
    buf = io.StringIO()
    report(["--- A", "+++ B", "-x", "+y"], content, 20, "text", buf)
    text = buf.getvalue()
    assert "== schema ==" in text and "--- t: -1 +1" in text and "< a" in text and "> b" in text
    assert "1 identical, 1 differ" in text

    buf = io.StringIO()
    report(None, content, 20, "json", buf)
    doc = json.loads(buf.getvalue())
    assert doc["schema"] is None
    assert doc["groups"] == {"t": {"removed": 1, "added": 1, "sample_removed": ["a"], "sample_added": ["b"]}}
