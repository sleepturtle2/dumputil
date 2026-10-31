# Changelog

## 0.1.0 — 2026-10-31

- `pg dump`, `pg diff`: pg_dump custom/directory/tar or plain SQL; offline via pg_restore.
- `neo export`, `neo dump`, `neo diff`: text sidecar `X.dump.txt`; scratch-instance fallback.
- Repo-local `dumputil.ini` (cwd or parents, `--config`, `$DUMPUTIL_CONFIG`); `[DEFAULT]` + profile
  sections; path keys relative to the ini. `--output json`, `--quiet`, table globs.
