"""dumputil <engine> <op> [flags] — argparse tree, profiles, one failure boundary, exit codes."""
import argparse
import configparser
import os
import sys
from pathlib import Path

from . import __version__
from .engines import DumpError, neo, pg

ENGINES = {pg.NAME: pg, neo.NAME: neo}

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "dumputil" / "config"

# Profile keys, in the order `configure` asks for them. *_password_var names the env var that holds a
# password (filled from `secrets`); the value is copied to the var the engine's own tools read.
KEYS = ("pg_bin", "pg_host", "pg_port", "pg_user", "pg_db", "pg_password_var",
        "neo4j_home", "neo4j_conf", "neo4j_uri", "neo4j_user", "neo4j_password_var",
        "neo_node_key", "neo_scratch_port", "java_home", "secrets")
PASSWORD_VARS = {"pg_password_var": "PGPASSWORD", "neo4j_password_var": "NEO4J_PASSWORD"}


def _section(name):
    return "default" if name in (None, "default") else f"profile {name}"


def load_profile(name):
    cp = configparser.ConfigParser()
    cp.read(CONFIG)
    section = _section(name)
    if name and section not in cp:
        raise DumpError(f"profile {name!r} not found in {CONFIG}")
    profile = dict(cp[section]) if section in cp else {}
    if profile.get("secrets"):
        _source(profile["secrets"])
    for key, target in PASSWORD_VARS.items():
        src = profile.get(key)
        if src and src in os.environ:
            os.environ[target] = os.environ[src]
    return profile


def _source(path):
    """KEY=VALUE env file; `export`, quotes and comments tolerated. Existing env wins."""
    for raw in Path(path).read_text().splitlines():
        l = raw.strip()
        if not l or l.startswith("#") or "=" not in l:
            continue
        if l.startswith("export "):
            l = l[7:]
        k, v = l.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _configure(args, _profile):
    cp = configparser.ConfigParser()
    cp.read(CONFIG)
    section = _section(args.profile)
    if section not in cp:
        cp[section] = {}
    print(f"profile [{section}] → {CONFIG}  (enter keeps the current value, '-' clears it)")
    for k in KEYS:
        cur = cp[section].get(k, "")
        v = input(f"  {k} [{cur}]: ").strip()
        if v == "-":
            cp[section].pop(k, None)
        elif v:
            cp[section][k] = v
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG, "w") as f:
        cp.write(f)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="dumputil",
                                description="Exact schema and content diff of database dumps.",
                                epilog="exit codes: 0 identical, 1 differences, 2 error")
    p.add_argument("--version", action="version", version=f"dumputil {__version__}")
    p.add_argument("--profile", metavar="NAME", help=f"profile section in {CONFIG} (default: [default])")
    p.add_argument("--output", choices=("text", "json"), default="text")
    p.add_argument("-q", "--quiet", action="store_true", help="no report, exit code only")
    p.add_argument("--rows", type=int, default=20, metavar="N", help="rows printed per table per side (default 20)")
    sub = p.add_subparsers(dest="engine", required=True, metavar="<engine>")
    for name, mod in ENGINES.items():
        ep = sub.add_parser(name, help=mod.__doc__.splitlines()[0])
        ops = ep.add_subparsers(dest="op", required=True, metavar="<op>")
        mod.add_ops(ops)
    c = sub.add_parser("configure", help="write a profile interactively")
    c.set_defaults(func=_configure, needs_profile=False)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        profile = load_profile(args.profile) if getattr(args, "needs_profile", True) else {}
        return args.func(args, profile)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"dumputil: {e}", file=sys.stderr)
        return 2
