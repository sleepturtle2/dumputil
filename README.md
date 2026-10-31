# dumputil

Exact schema and content diff of two database dumps. PostgreSQL and Neo4j. Offline wherever the
dump format allows. Python ≥ 3.9, standard library only.

Dump files are not diffable as they are: `pg_dump` writes rows in heap order, so two dumps of the
same data differ byte-for-byte; a Neo4j `.dump` is a compressed binary store that only Neo4j can
read. dumputil turns each dump into normalised text once and compares that.

```
$ dumputil pg diff db-dump/30-09/app.dump db-dump/17-10/app.dump
== schema ==
--- db-dump/30-09/app.dump
+++ db-dump/17-10/app.dump
@@ -231,2 +231,3 @@
-    pct numeric
+    pct numeric,
+    shareholders bigint
== content ==
--- edge.has_company_financials_y2021: -119 +119
< I|0|20MICRONS	I|2|PaymentsOfLeaseLiabilities~0	2021-03-31	month	3	4	2021	0
> I|0|20MICRONS	I|2|PaymentsOfLeaseLiabilities~0	2021-03-31	month	3	4	2021	-1950000
...
31 identical, 5 differ
```

## Install

```
pipx install git+https://github.com/sleepturtle2/dumputil
# or, without installing
python3 -m dumputil --help
```

Engine tools come from your own installation: `pg_dump`/`pg_restore` for PostgreSQL,
`neo4j-admin`/`cypher-shell` for Neo4j. Point a profile at them or have them on `PATH`.

## Commands

```
dumputil [--profile NAME] [--output text|json] [-q] [--rows N] <engine> <op> ...

dumputil pg  dump   --out DIR [--db NAME]        pg_dump -Fc → DIR/<db>.dump + SHA256
dumputil pg  diff   A B                          .dump (custom/dir/tar) or plain .sql; no server
dumputil neo export --out DIR [--dump NAME]      live db → DIR/<dump>.txt sidecar
dumputil neo dump   --out DIR [--database NAME]  neo4j-admin dump + check + SHA256 (db stopped)
dumputil neo diff   A.dump B.dump [--no-load]    diff via sidecars
dumputil configure  [--profile NAME]             write ~/.config/dumputil/config
```

Diff flags: `--schema-only`, `--data-only`, `--table GLOB`, `--ignore-table GLOB` (repeatable),
`--rows N` sample size per table per side, `--output json`, `-q` exit code only.

Exit codes: `0` identical, `1` differences, `2` error. Use `-q` as a CI gate.

## How content is compared

- **Content** is a multiset per table (pg) or per section (neo): order ignored, duplicates counted.
  One side is streamed against the other, so memory is one dump's text, not two.
- **Schema** is a positional unified diff of normalised DDL.
- **PostgreSQL** normalisation: owners and grants dropped (`--with-owner`, `--with-acl` keep them),
  `SET` headers, `\restrict` tokens and `-- Dumped …` version comments stripped. Archive formats go
  through `pg_restore -f -`; plain SQL is read directly.
- **Neo4j**: the diff reads a text sidecar `X.dump.txt` next to each dump, written by `neo export`
  while the database is up. Sidecar sections: constraints and indexes; one line per node property
  `labels, key, prop, value`; one line per relationship property `a.key, type, b.key, prop, value`.
  `neo_node_key` (default `uid`) names the identity property. If a dump has no sidecar, `neo diff`
  loads it into a throwaway instance (temp dir, loopback bolt on `neo_scratch_port`, auth off),
  exports, and writes the sidecar back so the next diff is instant. `--no-load` disables that.

Taking a Neo4j dump is two ops around your own stop/start, because the export needs the db up and
`neo4j-admin dump` needs it down:

```
dumputil neo export --out DIR      # db up
<stop neo4j>
dumputil neo dump   --out DIR      # db down
<start neo4j>
```

## Profiles

`~/.config/dumputil/config` (INI). `[default]` plus `[profile NAME]` sections, aws-cli style.
`diff` ops need no profile unless the engine binaries are off `PATH`.

```ini
[default]
pg_bin             = /usr/lib/postgresql/17/bin
pg_host            = localhost
pg_port            = 5432
pg_user            = postgres
pg_db              = app
pg_password_var    = PG_SUPER_PASSWORD
neo4j_home         = /opt/neo4j
neo4j_conf         = /etc/neo4j
neo4j_uri          = bolt://localhost:7687
neo4j_user         = neo4j
neo4j_password_var = NEO4J_SUPER_PASSWORD
neo_node_key       = uid
neo_scratch_port   = 17687
java_home          =
secrets            = /etc/app/secrets.env
```

Passwords never go in config or on the command line. `secrets` is a `KEY=VALUE` env file sourced
at start; `*_password_var` names the variable in it, which dumputil copies to `PGPASSWORD` /
`NEO4J_PASSWORD` for the engine tools. `~/.pgpass` works too.

## Limitations

- One dump's text is held in memory (roughly 3× its plain-text size). Fine for a few GB; beyond
  that, a per-table hash pre-pass is on the roadmap.
- Row-level, not cell-level: a changed row prints as one `<` and one `>` line.
- Neo4j property values containing newlines break the one-line-per-property format.
- Neo4j Community has one user database, so the scratch load runs one dump at a time.
- Linux and macOS. Windows untested.

## Roadmap

Cell-level diff for tables with a primary key · per-table hash pre-pass for very large dumps ·
MySQL/MariaDB, SQLite, MongoDB engines · Neo4j via the bolt driver for hosts without cypher-shell.

## License

Apache-2.0.
