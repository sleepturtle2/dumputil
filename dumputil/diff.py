"""Engine-agnostic comparison: positional diff for schema text, multiset diff for content."""
import difflib
import fnmatch
import json
import sys
from collections import Counter
from pathlib import Path

from .engines import DumpError


def add_args(p):
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--schema-only", action="store_true")
    p.add_argument("--data-only", action="store_true")
    p.add_argument("--table", action="append", default=[], metavar="GLOB",
                   help="only groups (tables / sections) matching GLOB; repeatable")
    p.add_argument("--ignore-table", action="append", default=[], metavar="GLOB",
                   help="skip groups matching GLOB; repeatable")


def multiset_diff(a, b):
    """a, b: iterables of (group, line). Returns {group: (removed Counter, added Counter)} for every
    group seen. Order-insensitive, duplicates counted. One pass each; only A is held in memory."""
    left, added = {}, {}
    for g, l in a:
        left.setdefault(g, Counter())[l] += 1
    for g, l in b:
        c = left.get(g)
        if c is not None and c[l] > 0:
            c[l] -= 1
        else:
            added.setdefault(g, Counter())[l] += 1
    return {g: (+left.get(g, Counter()), +added.get(g, Counter()))
            for g in sorted(set(left) | set(added))}


def schema_diff(a, b, name_a, name_b):
    return list(difflib.unified_diff(a, b, name_a, name_b, n=1, lineterm=""))


def _filter(items, include, exclude):
    for g, l in items:
        if include and not any(fnmatch.fnmatch(g, pat) for pat in include):
            continue
        if any(fnmatch.fnmatch(g, pat) for pat in exclude):
            continue
        yield g, l


def report(schema, content, rows, output, out=sys.stdout):
    """schema: list of unified-diff lines or None (skipped); content: multiset_diff result."""
    if output == "json":
        groups = {g: {"removed": sum(rem.values()), "added": sum(add.values()),
                      "sample_removed": sorted(rem.elements())[:rows],
                      "sample_added": sorted(add.elements())[:rows]}
                  for g, (rem, add) in content.items() if rem or add}
        json.dump({"schema": schema, "groups": groups}, out, indent=2)
        out.write("\n")
        return
    if schema is not None:
        out.write("== schema ==\n")
        out.write("\n".join(schema) + "\n" if schema else "identical\n")
    if content:
        out.write("== content ==\n")
        same = 0
        for g, (rem, add) in content.items():
            if not rem and not add:
                same += 1
                continue
            out.write(f"--- {g}: -{sum(rem.values())} +{sum(add.values())}\n")
            for l in sorted(rem.elements())[:rows]:
                out.write(f"< {l}\n")
            for l in sorted(add.elements())[:rows]:
                out.write(f"> {l}\n")
        out.write(f"{same} identical, {len(content) - same} differ\n")


def run(schema_fn, text_fn, args, profile):
    """The diff op every engine shares. Exit code: 0 identical, 1 differ."""
    a, b = Path(args.a), Path(args.b)
    for p in (a, b):
        if not p.exists():
            raise DumpError(f"{p}: no such file")
    schema = None
    if not args.data_only:
        schema = schema_diff(schema_fn(a, profile, args), schema_fn(b, profile, args), str(a), str(b))
    content = {}
    if not args.schema_only:
        content = multiset_diff(_filter(text_fn(a, profile, args), args.table, args.ignore_table),
                                _filter(text_fn(b, profile, args), args.table, args.ignore_table))
    differs = bool(schema) or any(rem or add for rem, add in content.values())
    if not args.quiet:
        report(schema, content, args.rows, args.output)
    return 1 if differs else 0
