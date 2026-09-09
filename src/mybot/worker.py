"""Persistent local runner: six-hour discovery, hourly pool sync, daily delivery."""
import json
import time
from datetime import timedelta, timezone
from . import pool
from .digest import utc_now, build_digest
from .radar import collect
from .mail import send, credentials


def due(settings, key, now, interval):
    with pool.connect(settings) as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT value FROM meta WHERE key=?",(key,)).fetchone()
        if row and now.timestamp()-float(row[0]) < interval:
            return False
        db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)",(key,str(now.timestamp())))
    return True


def run(settings, once=False):
    while True:
        now=utc_now()
        if due(settings,"worker_sync_attempt",now,3600):
            search=due(settings,"worker_collect_attempt",now,6*3600)
            try:
                print(json.dumps(collect(settings,search=search),ensure_ascii=False),flush=True)
            except Exception as exc:
                print("collection failed: "+type(exc).__name__,flush=True)
        local=now.astimezone(timezone(timedelta(hours=8)))
        if (local.hour,local.minute)>=(8,30) and due(settings,"worker_mail_check",now,3600):
            with pool.connect(settings) as db:
                exists=db.execute("SELECT status FROM outbox WHERE id=?",("radar-"+local.date().isoformat(),)).fetchone()
            if not exists:
                try:
                    credentials(settings)
                    print(json.dumps(send(settings,build_digest(settings)),ensure_ascii=False),flush=True)
                except Exception as exc:
                    # No credentials or transport payload is included in logs.
                    print("email unavailable: "+type(exc).__name__+"; run mybot email-status",flush=True)
        if once:
            return
        time.sleep(30)
