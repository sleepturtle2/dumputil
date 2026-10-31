import argparse

import pytest

from dumputil.engines import DumpError, neo

SIDECAR = """\
# dumputil neo v1 neo4j=5.26.10 key=uid at=2026-10-31T00:00:00Z
# schema
"instance_uid", "UNIQUENESS", "NODE", ["Instance"], ["uid"]
# nodes
["Instance"], "I|0|A", "cat", 0
["Instance"], "I|0|A", "uid", "I|0|A"
# rels
"I|0|A", "CHILD_OF", "I|0|B", "", NULL
"""


def test_read_sections(tmp_path):
    sc = tmp_path / "neo4j.dump.txt"
    sc.write_text(SIDECAR)
    items = list(neo.read(sc))
    assert items[0] == ("schema", '"instance_uid", "UNIQUENESS", "NODE", ["Instance"], ["uid"]')
    assert [s for s, _ in items] == ["schema", "nodes", "nodes", "rels"]


def test_schema_and_text_use_sidecar_next_to_dump(tmp_path):
    dump = tmp_path / "neo4j.dump"
    dump.write_bytes(b"DZV1")
    (tmp_path / "neo4j.dump.txt").write_text(SIDECAR)
    args = argparse.Namespace(no_load=True)
    assert neo.schema(dump, {}, args) == ['"instance_uid", "UNIQUENESS", "NODE", ["Instance"], ["uid"]']
    assert [s for s, _ in neo.text(dump, {}, args)] == ["nodes", "nodes", "rels"]


def test_missing_sidecar_with_no_load_fails(tmp_path):
    dump = tmp_path / "neo4j.dump"
    dump.write_bytes(b"DZV1")
    with pytest.raises(DumpError, match="missing"):
        neo.schema(dump, {}, argparse.Namespace(no_load=True))


def test_unknown_version_rejected(tmp_path):
    sc = tmp_path / "x.txt"
    sc.write_text("# dumputil neo v99 ...\n# nodes\nfoo\n")
    with pytest.raises(DumpError, match="unsupported"):
        list(neo.read(sc))


def test_queries_format_key():
    assert "n.`uid`" in neo.QUERIES["nodes"][0].format(key="uid")
    assert "a.`eid`" in neo.QUERIES["rels"][0].format(key="eid")
