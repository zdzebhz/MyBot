"""Durable local candidate pool; sent/read state never expires automatically."""
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def title_fingerprint(item):
    title = re.sub(r"[^\w\u4e00-\u9fff]", "", str(item.get("title", "")).casefold())
    if len(title) < 12:
        title += str(item.get("content_url", "")) + str(item.get("source_platform", ""))
    return hashlib.sha256(title.encode()).hexdigest()


def canonical_key(item):
    platform = str(item.get("source_platform", "unknown"))
    url = str(item.get("content_url") or item.get("url") or "")
    if platform == "bilibili":
        match = re.search(r"BV[0-9A-Za-z]+", url or str(item.get("bvid", "")))
        if match:
            return "bilibili:" + match[0]
    if platform == "xiaohongshu":
        match = re.search(r"/(?:explore|discovery/item)/([0-9a-fA-F]+)", url)
        if match:
            return "xiaohongshu:" + match[1].lower()
    if url:
        p = urlsplit(url)
        query = [(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith(("utm_","spm","xsec_","share_"))]
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/"),urlencode(sorted(query)),""))
    value = item.get("content_id") or item.get("bvid") or item.get("item_key")
    return platform + ":" + str(value or title_fingerprint(item))


@contextmanager
def connect(settings):
    settings.pool_file.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(settings.pool_file, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS items(key TEXT PRIMARY KEY,fingerprint TEXT,payload TEXT,
        first_seen TEXT,last_seen TEXT,sent_at TEXT,read_at TEXT);
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE IF NOT EXISTS vectors(key TEXT PRIMARY KEY,signature TEXT,vector TEXT);
    CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,status TEXT,payload TEXT,created_at TEXT,error TEXT);
    """)
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def ingest(settings, items, stamp):
    with connect(settings) as db:
        for item in items:
            key = canonical_key(item)
            old = db.execute("SELECT payload FROM items WHERE key=?", (key,)).fetchone()
            merged = json.loads(old[0]) if old else {}
            merged.update({k:v for k,v in item.items() if v not in (None,"")})
            db.execute("""INSERT INTO items(key,fingerprint,payload,first_seen,last_seen) VALUES(?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,last_seen=excluded.last_seen,
            fingerprint=excluded.fingerprint""",
            (key,title_fingerprint(merged),json.dumps(merged,ensure_ascii=False),stamp,stamp))


def candidates(settings, include_seen=False):
    with connect(settings) as db:
        rows = db.execute("SELECT * FROM items").fetchall()
        excluded = {r["fingerprint"] for r in rows if r["sent_at"] or r["read_at"]}
        return [dict(json.loads(r["payload"]),_mybot_key=r["key"],first_discovered_at=r["first_seen"])
                for r in rows if include_seen or (not r["sent_at"] and not r["read_at"] and r["fingerprint"] not in excluded)]


def mark_read(settings,key,stamp):
    with connect(settings) as db:
        if db.execute("UPDATE items SET read_at=? WHERE key=?",(stamp,key)).rowcount != 1:
            raise ValueError("Unknown radar item key")
