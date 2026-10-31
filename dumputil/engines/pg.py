"""PostgreSQL — fully offline: pg_restore turns a custom/directory/tar dump back into plain SQL without a
server; plain .sql dumps are read as-is. Content is compared per table as a multiset of COPY rows."""
import re
from pathlib import Path

from . import DumpError, check, run, sha256_file, tool
from .. import diff

NAME = "pg"

_NOISE = ("\\restrict", "\\unrestrict", "SET ", "SELECT pg_catalog.set_config", "-- Dumped")
_OWNER_COMMENT = re.compile(r"; Owner: .*$")


def add_ops(ops):
    d = ops.add_parser("dump", help="pg_dump -Fc into DIR, SHA256 alongside")
    d.add_argument("--out", required=True, metavar="DIR")
    d.add_argument("--db", help="database name (default: profile pg_db)")
    d.set_defaults(func=_dump_op)

    f = ops.add_parser("diff", help="schema + content diff of two dumps (.dump or plain .sql), no server")
    diff.add_args(f)
    f.add_argument("--with-owner", action="store_true", help="keep OWNER TO lines and owner names")
    f.add_argument("--with-acl", action="store_true", help="keep GRANT / REVOKE lines")
    f.set_defaults(func=lambda args, profile: diff.run(schema, text, args, profile))


def _dump_op(args, profile):
    db = args.db or profile.get("pg_db")
    if not db:
        raise DumpError("no database: pass --db or set pg_db in the profile")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{db}.dump"
    cmd = [tool(profile, "pg_bin", "pg_dump"), "-Fc", "-d", db, "-f", str(target)]
    for flag, key in (("-h", "pg_host"), ("-p", "pg_port"), ("-U", "pg_user")):
        if profile.get(key):
            cmd += [flag, profile[key]]
    check(cmd)
    print(f"{sha256_file(target)}  {target}")
    return 0


def _archive(path):
    """True for pg_dump custom / directory / tar formats (pg_restore input); False for plain SQL."""
    if path.is_dir():
        return True
    with open(path, "rb") as f:
        head = f.read(512)
    return head[:5] == b"PGDMP" or head[257:262] == b"ustar"


def _plain(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for l in f:
            yield l.rstrip("\n")


def _lines(path, profile, section):
    if _archive(path):
        return run([tool(profile, "pg_bin", "pg_restore"), f"--{section}-only", "-f", "-", str(path)])
    return _plain(path)


def split(lines):
    """Yields (group, line): 'schema' outside COPY blocks, the table name inside. COPY headers dropped."""
    table = None
    for l in lines:
        if table is None:
            if l.startswith("COPY ") and l.endswith(" FROM stdin;"):
                table = l[5:].split(" (")[0]
            else:
                yield "schema", l
        elif l == "\\.":
            table = None
        else:
            yield table, l


def schema(path, profile, args):
    out = []
    for g, l in split(_lines(path, profile, "schema")):
        if g != "schema" or not l or l.startswith(_NOISE):
            continue
        if not args.with_owner:
            if l.startswith("ALTER ") and " OWNER TO " in l:
                continue
            l = _OWNER_COMMENT.sub("; Owner: -", l)
        if not args.with_acl and l.startswith(("GRANT ", "REVOKE ")):
            continue
        out.append(l)
    return out


def text(path, profile, args):
    for g, l in split(_lines(path, profile, "data")):
        if g != "schema":
            yield g, l
