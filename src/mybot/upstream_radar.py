"""Run with upstream Python. Reuse authentication, search and paced XHS producer."""
import asyncio
import html
import json
import re
import sqlite3
import sys


async def main():
    from openbiliclaw.config import load_config
    cfg = load_config()
    request = json.loads(sys.stdin.read())
    data = {"items": [], "seen": [], "status": {}, "errors": {}}
    path = cfg.data_path / "openbiliclaw.db"
    db = sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    platforms = request["platforms"]
    for platform in platforms:
        for row in db.execute("SELECT * FROM content_cache WHERE source_platform=? ORDER BY discovered_at DESC LIMIT 2000",(platform,)):
            r = dict(row)
            r["reason"] = r.pop("relevance_reason","")
            r["confidence"] = r.pop("relevance_score",0)
            r["discovery_lane"] = "upstream_pool"
            data["items"].append(r)
        # Hover/scroll/snapshot are not proof the user has read a piece.
        for row in db.execute("SELECT source_platform,content_id,url,title FROM events WHERE source_platform=? AND event_type IN ('view','click','favorite','like')",(platform,)):
            data["seen"].append(dict(row))
    if "xiaohongshu" in platforms:
        for row in db.execute("SELECT payload_json,result_json,status FROM xhs_tasks WHERE type='search' ORDER BY created_at DESC LIMIT 200"):
            payload = json.loads(row[0] or "{}")
            if payload.get("keyword") not in request["all_queries"]:
                continue
            result = json.loads(row[1] or "{}")
            for note in result.get("notes",[]):
                data["items"].append(dict(note,source_platform="xiaohongshu",
                    content_url=note.get("url",""),content_id=note.get("note_id",""),
                    discovery_lane="ai_search",discovery_query=payload.get("keyword")))
    db.close()
    if request["search"]:
        if "bilibili" in platforms:
            from openbiliclaw.bilibili.api import BilibiliAPIClient
            from openbiliclaw.bilibili.auth import resolve_runtime_cookie
            cookie = resolve_runtime_cookie(data_dir=cfg.data_path,configured_cookie=cfg.bilibili.cookie)
            client = BilibiliAPIClient(cookie=cookie,proxy=cfg.bilibili.proxy or None)
            try:
                for index,query in enumerate(request["queries"]):
                    results = await client.search(query,page_size=20,order="pubdate" if index == 0 else "totalrank")
                    for r in results:
                        bvid = r.get("bvid","")
                        data["items"].append(dict(r,title=html.unescape(re.sub("<[^>]+>","",r.get("title",""))),
                            source_platform="bilibili",content_url="https://www.bilibili.com/video/"+bvid,
                            published_at=r.get("pubdate"),body_text=r.get("description",""),
                            author_name=r.get("author",""),discovery_lane="ai_search",discovery_query=query))
                    data["status"]["bilibili_search"] = "completed" if results else "empty_or_rate_limited"
                    if client.search_cooldown_remaining() > 0:
                        data["errors"]["bilibili_search"] = "upstream cooldown; stopped"
                        break
            except Exception as exc:
                data["errors"]["bilibili_search"] = type(exc).__name__
            finally:
                await client.close()
        if "xiaohongshu" in platforms:
            from openbiliclaw.storage.database import Database
            from openbiliclaw.sources.xhs_tasks import XhsTaskQueue
            from openbiliclaw.runtime.xhs_producer import XhsTaskProducer
            database = Database(path)
            database.initialize()
            try:
                producer = XhsTaskProducer(task_queue=XhsTaskQueue(database),soul_engine=None,llm_service=None,
                    enabled=cfg.sources.xiaohongshu.enabled and cfg.scheduler.enabled,
                    daily_budget=cfg.sources.xiaohongshu.daily_search_budget,keywords_per_cycle=2)
                data["status"]["xiaohongshu_search"] = await producer.produce_if_due(keywords=request["queries"],limit=2)
            except Exception as exc:
                data["errors"]["xiaohongshu_search"] = type(exc).__name__
            finally:
                database.close()
    print(json.dumps(data,ensure_ascii=False,default=str))


if __name__ == "__main__":
    # Avoid the sibling mybot/openbiliclaw.py shadowing the installed package.
    sys.path.pop(0)
    asyncio.run(main())
