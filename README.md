
Exact schema and content diff of two database dumps. 
Currently supports Postgres and Neo4J. 


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
dumputil [--config FILE] [--profile NAME] [--output text|json] [-q] [--rows N] <engine> <op> ...

dumputil pg  dump   --out DIR [--db NAME]        pg_dump -Fc → DIR/<db>.dump + SHA256
dumputil pg  diff   A B                          .dump (custom/dir/tar) or plain .sql; no server
dumputil neo export --out DIR [--dump NAME]      live db → DIR/<dump>.txt sidecar
dumputil neo dump   --out DIR [--database NAME]  neo4j-admin dump + check + SHA256 (db stopped)
dumputil neo diff   A.dump B.dump [--no-load]    diff via sidecars
```

Diff flags: `--schema-only`, `--data-only`, `--table GLOB`, `--ignore-table GLOB` (repeatable),
`--rows N` sample size per table per side, `--output json`, `-q` exit code only.

Exit codes: `0` identical, `1` differences, `2` error. Use `-q` as a CI gate.

## Configuration

One `dumputil.ini` committed at the root of the repo that owns the dumps. Found from the current
directory or any parent (like `.git`); or `--config FILE` / `$DUMPUTIL_CONFIG`. Nothing under
`~/.config`. `diff` ops need no config unless the engine binaries are off `PATH`.

Sections are profiles: `--profile dev` / `$DUMPUTIL_PROFILE` picks `[dev]`; `[DEFAULT]` keys apply to
every profile and are what you get with no `--profile`. Path keys (`pg_bin`, `neo4j_home`,
`neo4j_conf`, `java_home`, `secrets`) resolve relative to the ini, so a repo can point at its own
vendored engines. Full example: [`dumputil.example.ini`](dumputil.example.ini).

```ini
[DEFAULT]
pg_db              = app
pg_user            = postgres
pg_password_var    = PG_SUPER_PASSWORD
neo4j_uri          = bolt://localhost:7687
neo4j_user         = neo4j
neo4j_password_var = NEO4J_SUPER_PASSWORD
neo_node_key       = uid
neo_scratch_port   = 17687
secrets            = /etc/app/secrets.env

[local]
pg_bin     = /Library/PostgreSQL/17/bin
pg_port    = 5432
neo4j_home = lib/neo4j/5.26
neo4j_conf = ../data/db/neo4j-conf
java_home  = lib/jdk/21/darwin-arm64

[dev]
pg_bin     = /usr/lib/postgresql/17/bin
neo4j_home = /opt/neo4j/current
```

Passwords never go in the ini or on the command line. `secrets` is a `KEY=VALUE` env file outside
the repo, sourced at start; `*_password_var` names the variable in it, which dumputil copies to
`PGPASSWORD` / `NEO4J_PASSWORD` for the engine tools. `~/.pgpass` works too.

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
