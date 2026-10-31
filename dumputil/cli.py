import argparse
import configparser
import os
import sys
from pathlib import Path

from . import __version__
from .engines import DumpError, neo, pg

"""dumputil <engine> <op> [flags] — argparse tree, profiles, one failure boundary, exit codes."""

ENGINES = {pg.NAME: pg, neo.NAME: neo}

CONFIG_NAME = "dumputil.ini"

PATH_KEYS = ("pg_bin", "neo4j_home", "neo4j_conf", "java_home", "secrets")

PASSWORD_VARS = {"pg_password_var": "PGPASSWORD", "neo4j_password_var": "NEO4J_PASSWORD"}


def find_config(explicit=None):
    """--config, else $DUMPUTIL_CONFIG, else dumputil.ini in cwd or any parent. None when absent."""
    given = explicit or os.environ.get("DUMPUTIL_CONFIG")
    if given:
        p = Path(given)
        if not p.is_file():
            raise DumpError(f"{p}: config file not found")
        return p
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / CONFIG_NAME).is_file():
            return d / CONFIG_NAME
    return None


def load_profile(name, config):
    """Section `name` of the ini (its [DEFAULT] keys included); [DEFAULT] alone when name is None."""
    if config is None:
        if name:
            raise DumpError(f"profile {name!r} requested but no {CONFIG_NAME} found")
        return {}
    cp = configparser.ConfigParser()
    cp.read(config)
    if name is None:
        profile = dict(cp.defaults())
    elif name in cp:
        profile = dict(cp[name])
    else:
        raise DumpError(f"profile {name!r} not in {config} (have: {', '.join(cp.sections()) or 'none'})")
    for key in PATH_KEYS:
        if profile.get(key):
            profile[key] = str((config.parent / Path(profile[key]).expanduser()).resolve())
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


def build_parser():
    p = argparse.ArgumentParser(prog="dumputil",
                                description="Exact schema and content diff of database dumps.",
                                epilog="exit codes: 0 identical, 1 differences, 2 error")
    p.add_argument("--version", action="version", version=f"dumputil {__version__}")
    p.add_argument("--config", metavar="FILE",
                   help=f"ini file (default: $DUMPUTIL_CONFIG, else {CONFIG_NAME} in cwd or a parent)")
    p.add_argument("--profile", metavar="NAME", default=os.environ.get("DUMPUTIL_PROFILE"),
                   help="ini section to use (default: $DUMPUTIL_PROFILE, else [DEFAULT] keys only)")
    p.add_argument("--output", choices=("text", "json"), default="text")
    p.add_argument("-q", "--quiet", action="store_true", help="no report, exit code only")
    p.add_argument("--rows", type=int, default=20, metavar="N", help="rows printed per table per side (default 20)")
    sub = p.add_subparsers(dest="engine", required=True, metavar="<engine>")
    for name, mod in ENGINES.items():
        ep = sub.add_parser(name, help=(mod.__doc__ or name).split(" — ")[0])
        ops = ep.add_subparsers(dest="op", required=True, metavar="<op>")
        mod.add_ops(ops)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        profile = load_profile(args.profile, find_config(args.config))
        return args.func(args, profile)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"dumputil: {e}", file=sys.stderr)
        return 2
