import argparse

from dumputil.engines import pg

PLAIN = """\
--
-- PostgreSQL database dump
--

-- Dumped from database version 17.10
\\restrict abc123
SET statement_timeout = 0;
SELECT pg_catalog.set_config('search_path', '', false);

--
-- Name: t; Type: TABLE; Schema: public; Owner: alice
--

CREATE TABLE public.t (
    id integer,
    v text
);

ALTER TABLE public.t OWNER TO alice;
GRANT SELECT ON TABLE public.t TO bob;

COPY public.t (id, v) FROM stdin;
1\ta
2\tb
2\tb
\\.

\\unrestrict abc123
"""


def _write(tmp_path, body, name="d.sql"):
    p = tmp_path / name
    p.write_text(body)
    return p


def test_split_routes_rows_to_table_and_drops_copy_header():
    groups = list(pg.split(PLAIN.splitlines()))
    rows = [l for g, l in groups if g == "public.t"]
    assert rows == ["1\ta", "2\tb", "2\tb"]
    assert not any(l.startswith("COPY ") for g, l in groups if g == "schema")


def test_schema_normalises_owner_acl_and_noise(tmp_path):
    p = _write(tmp_path, PLAIN)
    args = argparse.Namespace(with_owner=False, with_acl=False)
    s = pg.schema(p, {}, args)
    assert "-- Name: t; Type: TABLE; Schema: public; Owner: -" in s
    assert "CREATE TABLE public.t (" in s
    assert not any("OWNER TO" in l or l.startswith(("GRANT", "SET ", "\\restrict", "-- Dumped")) for l in s)

    args = argparse.Namespace(with_owner=True, with_acl=True)
    s = pg.schema(p, {}, args)
    assert "ALTER TABLE public.t OWNER TO alice;" in s
    assert "GRANT SELECT ON TABLE public.t TO bob;" in s
    assert "-- Name: t; Type: TABLE; Schema: public; Owner: alice" in s


def test_text_yields_only_rows(tmp_path):
    p = _write(tmp_path, PLAIN)
    assert list(pg.text(p, {}, None)) == [("public.t", "1\ta"), ("public.t", "2\tb"), ("public.t", "2\tb")]


def test_archive_detection(tmp_path):
    assert pg._archive(_write(tmp_path, PLAIN)) is False
    custom = tmp_path / "c.dump"
    custom.write_bytes(b"PGDMP" + b"\0" * 32)
    assert pg._archive(custom) is True
    assert pg._archive(tmp_path) is True
