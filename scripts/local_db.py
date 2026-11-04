#!/usr/bin/env python
"""Lifecycle for the offline local Postgres sandbox.

Uses the PostgreSQL binaries bundled with the `pgserver` pip package
(installed in backend/.venv) but always starts them on a FIXED port, so
the project's DATABASE_URL stays stable across restarts. pgserver's own
get_server() picks a random port each start, which would make .env and
pytest setup churn.

Everything lives under .local/ (gitignored) and binds to 127.0.0.1 only,
so it is never exposed to the network and can be wiped by deleting .local/.

Usage (run with the backend venv python):

    backend/.venv/Scripts/python.exe scripts/local_db.py start
    backend/.venv/Scripts/python.exe scripts/local_db.py status
    backend/.venv/Scripts/python.exe scripts/local_db.py url
    backend/.venv/Scripts/python.exe scripts/local_db.py psql "select 1"
    backend/.venv/Scripts/python.exe scripts/local_db.py stop
    backend/.venv/Scripts/python.exe scripts/local_db.py reset --yes

Never point this at Neon, and never point the app's .env at real data
while using it -- it is a disposable sandbox.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

import pgserver

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL_DIR = ROOT / ".local"
PGDATA = LOCAL_DIR / "pgdata"
LOG = LOCAL_DIR / "pg.log"
BIN_DIR = pathlib.Path(pgserver.__file__).resolve().parent / "pginstall" / "bin"

HOST = "127.0.0.1"
PORT = 55432
DB_USER = "postgres"
DB_NAME = "mact_local"
TEST_DB_NAME = "mact_test"


def _exe(name: str) -> pathlib.Path:
    candidate = BIN_DIR / f"{name}.exe"
    return candidate if candidate.exists() else BIN_DIR / name


def database_url() -> str:
    return f"postgresql://{DB_USER}:@{HOST}:{PORT}/{DB_NAME}"


def _log(msg: str) -> None:
    print(f"[local-db] {msg}")


def is_initialized() -> bool:
    return (PGDATA / "PG_VERSION").exists()


def is_running() -> bool:
    if not is_initialized():
        return False
    try:
        pgserver.pg_ctl(["status"], pgdata=PGDATA)
        return True
    except subprocess.CalledProcessError:
        return False


def init() -> None:
    if is_initialized():
        return
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    _log(f"initializing cluster at {PGDATA}")
    pgserver.initdb(
        ["--auth=trust", "--auth-local=trust", "--encoding=utf8", "-U", DB_USER],
        pgdata=PGDATA,
    )


def ensure_database() -> None:
    # mact_local holds the seeded sample data; mact_test is the throwaway
    # database the pytest suite creates and truncates freely.
    for name in (DB_NAME, TEST_DB_NAME):
        try:
            pgserver.createdb(["-h", HOST, "-p", str(PORT), "-U", DB_USER, name])
            _log(f"created database {name}")
        except subprocess.CalledProcessError:
            pass


def start() -> None:
    init()
    if is_running():
        _log("already running")
    else:
        _log(f"starting on {HOST}:{PORT}")
        pgserver.pg_ctl(
            ["-w", "-o", f"-p {PORT} -h {HOST}", "-l", str(LOG), "start"],
            pgdata=PGDATA,
        )
    ensure_database()
    _log(f"ready: {database_url()}")


def stop() -> None:
    if not is_running():
        _log("not running")
        return
    _log("stopping")
    pgserver.pg_ctl(["-w", "stop"], pgdata=PGDATA)


def status() -> None:
    running = is_running()
    _log(f"{'running' if running else 'stopped'} (port {PORT}, data {PGDATA})")
    if running:
        _log(f"url: {database_url()}")


def run_psql(sql: str | None) -> None:
    cmd = [str(_exe("psql")), "-h", HOST, "-p", str(PORT), "-U", DB_USER, "-d", DB_NAME]
    if sql:
        cmd += ["-c", sql]
    sys.exit(subprocess.call(cmd))


def reset(assume_yes: bool) -> None:
    if not assume_yes:
        _log("refusing to wipe .local/pgdata without --yes")
        sys.exit(1)
    if is_running():
        stop()
    if PGDATA.exists():
        import shutil

        _log(f"deleting {PGDATA}")
        shutil.rmtree(PGDATA)
    start()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="init if needed, start server, ensure database exists")
    sub.add_parser("stop", help="stop the server (data is kept)")
    sub.add_parser("status", help="show whether the server is running")
    sub.add_parser("url", help="print the DATABASE_URL for .env")
    psql_p = sub.add_parser("psql", help="open psql, or run one SQL string")
    psql_p.add_argument("sql", nargs="?", default=None)
    reset_p = sub.add_parser("reset", help="wipe the sandbox cluster and recreate it")
    reset_p.add_argument("--yes", action="store_true", help="required; confirms the wipe")

    args = parser.parse_args()
    if args.command == "start":
        start()
    elif args.command == "stop":
        stop()
    elif args.command == "status":
        status()
    elif args.command == "url":
        print(database_url())
    elif args.command == "psql":
        run_psql(args.sql)
    elif args.command == "reset":
        reset(args.yes)


if __name__ == "__main__":
    main()
