"""Neo4j — the .dump is a binary store archive only Neo4j can read, so content lives in a text sidecar
(X.dump.txt) exported with cypher-shell while the db is up. Diff reads sidecars only; a dump without one
is loaded into a throwaway scratch instance to produce it."""
import datetime
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import DumpError, check, run, sha256_file, tool
from .. import diff

NAME = "neo"
SIDECAR_VERSION = 1

# {key} = node identity property (profile neo_node_key, default uid). One line per property so map
# key order can never show up as a difference; a property-less relationship prints one line with k=''.
QUERIES = {
    "schema": ["SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties RETURN *;",
               "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, owningConstraint RETURN *;"],
    "nodes": ["MATCH (n) UNWIND keys(n) AS k RETURN labels(n), n.`{key}`, k, n[k];"],
    "rels": ["MATCH (a)-[r]->(b) UNWIND keys(r) + CASE WHEN size(keys(r)) = 0 THEN [''] ELSE [] END AS k "
             "RETURN a.`{key}`, type(r), b.`{key}`, k, r[k];"],
}

_SCRATCH_CONF = """\
server.directories.data={tmp}/data
server.directories.logs={tmp}/logs
server.directories.run={tmp}/run
server.directories.import={tmp}/import
server.bolt.listen_address=127.0.0.1:{port}
server.http.enabled=false
dbms.security.auth_enabled=false
"""


def add_ops(ops):
    e = ops.add_parser("export", help="live db → DIR/<dump>.txt sidecar (schema, nodes, rels as text)")
    e.add_argument("--out", required=True, metavar="DIR")
    e.add_argument("--dump", default="neo4j.dump", metavar="NAME",
                   help="dump file the sidecar belongs to (default neo4j.dump)")
    e.set_defaults(func=_export_op)

    d = ops.add_parser("dump", help="neo4j-admin database dump into DIR (db must be stopped), SHA256 alongside")
    d.add_argument("--out", required=True, metavar="DIR")
    d.add_argument("--database", default="neo4j")
    d.set_defaults(func=_dump_op)

    f = ops.add_parser("diff", help="diff two dumps via their sidecars; a missing sidecar is built by loading "
                                    "the dump into a scratch instance")
    diff.add_args(f)
    f.add_argument("--no-load", action="store_true", help="fail instead of loading a dump without sidecar")
    f.set_defaults(func=lambda args, profile: diff.run(schema, text, args, profile))


def _export_op(args, profile):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(export(profile, out / (args.dump + ".txt")))
    return 0


def _dump_op(args, profile):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    admin = tool(profile, "neo4j_home", "bin/neo4j-admin")
    env = _env(profile)
    check([admin, "database", "dump", args.database, "--to-path", str(out), "--overwrite-destination=true"], env=env)
    check([admin, "database", "check", args.database, "--from-path", str(out)], env=env)
    target = out / f"{args.database}.dump"
    print(f"{sha256_file(target)}  {target}")
    return 0


def _env(profile, conf=None):
    env = dict(os.environ)
    conf = conf or profile.get("neo4j_conf")
    if conf:
        env["NEO4J_CONF"] = str(conf)
    if profile.get("java_home"):
        env["JAVA_HOME"] = profile["java_home"]
    if profile.get("neo4j_user"):
        env["NEO4J_USERNAME"] = profile["neo4j_user"]
    return env


# ── sidecar ──
def export(profile, sidecar, uri=None):
    """Writes the sidecar for the db at uri (default profile neo4j_uri). Returns the path."""
    key = profile.get("neo_node_key", "uid")
    if not re.fullmatch(r"\w+", key):
        raise DumpError(f"neo_node_key {key!r}: letters, digits, underscore only")
    cs = [tool(profile, "neo4j_home", "bin/cypher-shell"), "-a", uri or profile.get("neo4j_uri", "bolt://localhost:7687"),
          "--format", "plain"]
    env = _env(profile)
    version = list(run(cs + ["CALL dbms.components() YIELD versions RETURN versions[0];"], env=env))[-1].strip('"')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write(f"# dumputil neo v{SIDECAR_VERSION} neo4j={version} key={key} at={stamp}\n")
        for section, qs in QUERIES.items():
            f.write(f"# {section}\n")
            for l in sorted(run(cs, "\n".join(q.format(key=key) for q in qs), env=env)):
                f.write(l + "\n")
    return sidecar


def read(sidecar):
    """Yields (section, line). Rejects a sidecar written by another format version."""
    with open(sidecar, encoding="utf-8") as f:
        head = f.readline().rstrip("\n")
        if not head.startswith(f"# dumputil neo v{SIDECAR_VERSION} "):
            raise DumpError(f"{sidecar}: unsupported sidecar header {head!r}")
        section = None
        for l in f:
            l = l.rstrip("\n")
            if l.startswith("# "):
                section = l[2:]
            elif section:
                yield section, l


def _sidecar(path, profile, args):
    sc = Path(str(path) + ".txt")
    if not sc.exists():
        if args.no_load:
            raise DumpError(f"{sc}: missing; run `dumputil neo export`, or drop --no-load to build it from the dump")
        print(f"dumputil: no sidecar for {path}, loading it into a scratch neo4j", file=sys.stderr)
        _scratch_export(Path(path), sc, profile)
    return sc


def schema(path, profile, args):
    return [l for s, l in read(_sidecar(path, profile, args)) if s == "schema"]


def text(path, profile, args):
    for s, l in read(_sidecar(path, profile, args)):
        if s != "schema":
            yield s, l


# ── scratch instance ──
def _scratch_export(dump, sidecar, profile):
    home = profile.get("neo4j_home")
    if not home:
        raise DumpError("neo4j_home not set in profile; needed to load a dump that has no sidecar")
    port = int(profile.get("neo_scratch_port", "17687"))
    with tempfile.TemporaryDirectory(prefix="dumputil-neo-") as tmp:
        tmp = Path(tmp)
        for d in ("dumps", "conf", "data", "logs", "run", "import"):
            (tmp / d).mkdir()
        os.symlink(dump.resolve(), tmp / "dumps" / "neo4j.dump")
        (tmp / "conf" / "neo4j.conf").write_text(_SCRATCH_CONF.format(tmp=tmp, port=port))
        for name in ("server-logs.xml", "user-logs.xml"):
            src = Path(home) / "conf" / name
            if src.exists():
                shutil.copy(src, tmp / "conf" / name)
        env = _env(profile, conf=tmp / "conf")
        log_path = tmp / "console.log"
        with open(log_path, "w") as log:
            load = subprocess.run([os.path.join(home, "bin/neo4j-admin"), "database", "load", "neo4j",
                                   "--from-path", str(tmp / "dumps"), "--overwrite-destination=true"],
                                  env=env, stdout=log, stderr=subprocess.STDOUT)
            if load.returncode != 0:
                raise DumpError("neo4j-admin load failed:\n" + _tail(log_path))
            srv = subprocess.Popen([os.path.join(home, "bin/neo4j"), "console"], env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
            try:
                _wait_bolt(srv, port, log_path, timeout=180)
                export(profile, sidecar, uri=f"bolt://127.0.0.1:{port}")
            finally:
                srv.terminate()
                try:
                    srv.wait(60)
                except subprocess.TimeoutExpired:
                    srv.kill()


def _tail(log_path, n=20):
    return "".join(log_path.read_text(errors="replace").splitlines(True)[-n:])


def _wait_bolt(srv, port, log_path, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if srv.poll() is not None:
            raise DumpError("scratch neo4j exited:\n" + _tail(log_path))
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                time.sleep(2)
                return
        except OSError:
            time.sleep(1)
    raise DumpError(f"scratch neo4j did not open bolt port {port} within {timeout}s")
