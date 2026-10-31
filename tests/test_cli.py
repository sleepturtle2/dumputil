import os

import pytest

from dumputil import cli
from dumputil.engines import DumpError

INI = """\
[DEFAULT]
pg_db = app
pg_password_var = MY_PG_PW
secrets = secrets.env

[local]
pg_bin = bin/pg
pg_port = 5432

[dev]
pg_bin = /usr/lib/postgresql/17/bin
"""


def _repo(tmp_path):
    (tmp_path / "dumputil.ini").write_text(INI)
    (tmp_path / "secrets.env").write_text('export MY_PG_PW="s3cret"\n# comment\n')
    return tmp_path


def test_find_config_walks_up(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert cli.find_config() == repo / "dumputil.ini"


def test_find_config_explicit_and_env(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    assert cli.find_config(str(repo / "dumputil.ini")) == repo / "dumputil.ini"
    monkeypatch.setenv("DUMPUTIL_CONFIG", str(repo / "dumputil.ini"))
    assert cli.find_config() == repo / "dumputil.ini"
    with pytest.raises(DumpError, match="not found"):
        cli.find_config(str(repo / "nope.ini"))


def test_profile_inherits_default_resolves_paths_and_passwords(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.delenv("MY_PG_PW", raising=False)
    p = cli.load_profile("local", repo / "dumputil.ini")
    assert p["pg_db"] == "app" and p["pg_port"] == "5432"
    assert p["pg_bin"] == str((repo / "bin/pg").resolve())
    assert p["secrets"] == str((repo / "secrets.env").resolve())
    assert os.environ["PGPASSWORD"] == "s3cret"

    d = cli.load_profile("dev", repo / "dumputil.ini")
    assert d["pg_bin"] == "/usr/lib/postgresql/17/bin"


def test_no_profile_gives_defaults_only(tmp_path):
    repo = _repo(tmp_path)
    p = cli.load_profile(None, repo / "dumputil.ini")
    assert p["pg_db"] == "app" and "pg_bin" not in p


def test_missing_profile_or_config(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(DumpError, match="not in"):
        cli.load_profile("prod", repo / "dumputil.ini")
    assert cli.load_profile(None, None) == {}
    with pytest.raises(DumpError, match="no dumputil.ini"):
        cli.load_profile("dev", None)
