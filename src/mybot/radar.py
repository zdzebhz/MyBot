"""AI-first discovery, explainable ranking and delivery-independent collection."""
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter
from dataclasses import replace
from pathlib import Path
from urllib.request import Request, urlopen

from . import pool
from .openbiliclaw import BridgeError, decode_json_output

QUERIES = (
    "AI 大模型 产品 更新", "AI 工具 使用体验", "AI 开源 项目 Demo",
    "AI 编程 Claude Code 技巧", "AI Agent MCP 工作流", "AI 办公 自动化",
    "AI 视频 图像 创作 教程", "大模型 RAG 部署 踩坑", "AI 独立开发 冷门工具",
    "AI Prompt 提示词 实践", "多模态 语音 模型", "AI 评测 局限 经验",
)
CATEGORIES = {
    "tutorial": ("教程","入门","指南","教学","tutorial"),
    "workflow": ("工作流","自动化","workflow"),
    "experience": ("踩坑","实践","经验","实测","评测","局限"),
    "project": ("开源","github","demo","框架","插件"),
    "tool": ("工具","网站","产品","应用","tool"),
    "news": ("发布","更新","融资","新闻","收购","release","上线"),
}
STRONG = ("AI","人工智能","大模型","LLM","ChatGPT","OpenAI","Claude","DeepSeek","Gemini",
          "Qwen","机器学习","深度学习","生成式","智能体","多模态","提示词","RAG","ComfyUI",
          "Stable Diffusion","Midjourney","AI编程","MCP")
QUALITY = ("教程","代码","开源","复现","测试","评测","步骤","实战","经验","踩坑","对比","局限","workflow","github","demo")
FIELDS = ("title","source_platform","content_id","bvid","content_url","author_name","up_name",
          "published_at","published_label","body_text","description","reason","confidence",
          "topic_label","pool_topic_label","topic_key","temporal_class","temporal_state",
          "discovery_lane","discovery_query","like_count","favorite_count","view_count")


def classify(item):
    from .assessment import current
    if current(item):
        return item["assessment"]["category"]
    text = (str(item.get("title",""))+" "+str(item.get("description",""))).casefold()
    for category,words in CATEGORIES.items():
        if any(w in text for w in words):
            return category
    return "other"


def rank(items, settings, sent, include_seen=False, now=None):
    from .digest import utc_now, parse_datetime, keyword_score, item_key, _contains_keyword
    now = now or utc_now()
    stats = dict(received=0,duplicate=0,seen=0,too_old=0,not_ai=0)
    unique, fingerprints = {}, set()
    for raw in items:
        stats["received"] += 1
        item = dict(raw)
        key = item.get("_mybot_key") or pool.canonical_key(item)
        if key in unique:
            stats["duplicate"] += 1
            continue
        aliases={key,item_key(item)} | {str(item.get(k,"")) for k in ("bvid","content_id","item_key","content_url")}
        if not include_seen and bool((aliases-{""}) & sent):
            stats["seen"] += 1
            continue
        # An AI-flavoured recommendation reason must not make a travel video AI.
        evidence = " ".join(str(item.get(k,"") or "") for k in ("title","body_text","description"))
        hits = [w for w in dict.fromkeys(STRONG+settings.keywords) if _contains_keyword(evidence,w)]
        if not hits:
            stats["not_ai"] += 1
            continue
        from .assessment import current
        assessment = item.get("assessment", {}) if current(item) else {}
        if assessment and (assessment["ai"] < 0.65 or assessment["value"] < 0.4):
            stats["not_ai"] += 1
            continue
        fp = pool.title_fingerprint(item)
        if fp in fingerprints:
            stats["duplicate"] += 1
            continue
        fingerprints.add(fp)
        category = classify(item)
        published = parse_datetime(item.get("published_at"))
        age = max(0,(now-published).total_seconds()/86400) if published else None
        # Old content is eligible; news decays faster than reusable knowledge.
        half_life = 3 if category == "news" else 365
        freshness = (20 if category == "news" else 6) * (0.5**(age/half_life)) if age is not None else 0
        clues = [w for w in QUALITY if w in evidence.casefold()]
        relevance = min(35,25+3*len(hits))
        value = min(25,10+3*len(clues))
        if assessment:
            relevance = 35*assessment["ai"]
            value = 30*assessment["value"]
            item["reason"] = assessment["reason"]
        try:
            interest = max(0,min(1,float(item.get("confidence",0) or 0)))*3
        except (ValueError,TypeError):
            interest = 0
        exploration = 8 if item.get("discovery_lane") == "ai_search" else 3
        penalty = 12 if any(w in evidence for w in ("稳赚","日赚过万","百分百赚钱")) else 0
        parts = dict(ai=relevance,value_clues=value,freshness=round(freshness,2),
                     exploration=exploration,personal_interest=round(interest,2),hype_penalty=-penalty)
        item.update(_mybot_key=key,_mybot_matches=hits,_mybot_category=category,
                    _mybot_score=round(sum(parts.values()),2),_mybot_score_parts=parts,
                    _mybot_timestamp=published.timestamp() if published else 0)
        unique[key] = item
    # Soft category/author/source diversity. No category can block another source.
    remaining = list(unique.values())
    selected, cats, authors, sources = [], Counter(), Counter(), Counter()
    while remaining and len(selected) < settings.digest_limit:
        def utility(x):
            return (x["_mybot_score"]-cats[x["_mybot_category"]]*6
                    -authors[str(x.get("author_name") or x.get("up_name") or x["_mybot_key"])]*8
                    -sources[x.get("source_platform")]*2, x["_mybot_timestamp"],x["_mybot_key"])
        chosen=max(remaining,key=utility)
        remaining.remove(chosen)
        selected.append(chosen)
        cats[chosen["_mybot_category"]] += 1
        authors[str(chosen.get("author_name") or chosen.get("up_name") or chosen["_mybot_key"])] += 1
        sources[chosen.get("source_platform")] += 1
    return selected,stats


def collect(settings, search=True):
    from .digest import utc_now
    with pool.connect(settings) as db:
        row=db.execute("SELECT value FROM meta WHERE key='query_cursor'").fetchone()
        cursor=int(row[0]) if row else 0
        last=db.execute("SELECT value FROM meta WHERE key='last_search'").fetchone()
    from .digest import parse_datetime
    stamp=utc_now()
    if last and (stamp-parse_datetime(last[0])).total_seconds()<3600:
        search=False
    queries=[QUERIES[(cursor+i)%len(QUERIES)] for i in range(settings.queries_per_cycle)]
    request=dict(platforms=settings.platforms,queries=queries,all_queries=QUERIES,search=search)
    env=os.environ.copy()
    env.update(PYTHONUTF8="1",PYTHONIOENCODING="utf-8")
    result=subprocess.run([str(settings.openbiliclaw_python),str(Path(__file__).with_name("upstream_radar.py"))],
        input=json.dumps(request),capture_output=True,text=True,encoding="utf-8",env=env,
        cwd=settings.openbiliclaw_root,timeout=settings.bridge_timeout_seconds)
    if result.returncode:
        # No arbitrary stderr/API credential content crosses the adapter boundary.
        raise BridgeError("上游雷达适配失败；请检查固定版本接口（退出码 %s）"%result.returncode)
    data=decode_json_output(result.stdout)
    cleaned=[{k:v for k,v in r.items() if k in FIELDS} for r in data["items"]]
    accepted,stats=rank(cleaned,replace(settings,digest_limit=max(1,len(cleaned))),set(),now=stamp)
    pool.ingest(settings,accepted,stamp.isoformat())
    seen={pool.canonical_key(r) for r in data["seen"]}
    with pool.connect(settings) as db:
        for key in seen:
            db.execute("UPDATE items SET read_at=COALESCE(read_at,?) WHERE key=?",(stamp.isoformat(),key))
        if search:
            db.execute("INSERT OR REPLACE INTO meta VALUES('query_cursor',?)",(str((cursor+len(queries))%len(QUERIES)),))
            db.execute("INSERT OR REPLACE INTO meta VALUES('last_search',?)",(stamp.isoformat(),))
        report=dict(stats=stats,status=data["status"],errors=data["errors"],queries=queries if search else [],
                    collected_at=stamp.isoformat(),upstream_seen_count=len(seen))
        db.execute("INSERT OR REPLACE INTO meta VALUES('last_collection',?)",(json.dumps(report,ensure_ascii=False),))
    try:
        from .assessment import assess_pending
        report["assessed"] = assess_pending(settings)
    except Exception as exc:
        report["errors"]["assessment"] = "内容审核未完成，待审核条目不推送："+type(exc).__name__
    with pool.connect(settings) as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES('last_collection',?)",(json.dumps(report,ensure_ascii=False),))
    return report


def diversify_embeddings(settings, ranked, limit):
    """Cache local bge-m3 vectors; similarity only suppresses same-batch repetition."""
    selected, vectors, warnings=[],[],{}
    for item in ranked:
        key=item["_mybot_key"]
        text=str(item.get("title",""))+" "+str(item.get("description",""))[:500]
        signature=hashlib.sha256(("bge-m3:"+text).encode()).hexdigest()
        try:
            with pool.connect(settings) as db:
                row=db.execute("SELECT vector FROM vectors WHERE key=? AND signature=?",(key,signature)).fetchone()
            if row:
                vector=json.loads(row[0])
            else:
                req=Request("http://127.0.0.1:11434/api/embed",
                    data=json.dumps(dict(model="bge-m3",input=text)).encode(),headers={"Content-Type":"application/json"})
                with urlopen(req,timeout=20) as response:
                    vector=json.load(response)["embeddings"][0]
                with pool.connect(settings) as db:
                    db.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?)",(key,signature,json.dumps(vector)))
            norm=math.sqrt(sum(v*v for v in vector))
            vector=[v/norm for v in vector] if norm else vector
            if any(len(v)==len(vector) and sum(a*b for a,b in zip(v,vector))>0.94 for v in vectors):
                continue
            vectors.append(vector)
        except Exception as exc:
            warnings["embedding"]="本地语义分组不可用，使用标题去重："+type(exc).__name__
            # One failure is enough; avoid one timeout per item.
            selected.extend(x for x in ranked if x not in selected)
            return selected[:limit],warnings
        selected.append(item)
        if len(selected)>=limit:
            break
    return selected,warnings


def build(settings, refresh=False, include_seen=False, client=None, now=None):
    from .digest import DigestResult, utc_now, load_sent
    errors={}
    if client is not None:  # Adapter seam for deterministic tests.
        items=[]
        for platform in settings.platforms:
            try:
                items.extend(client.recommend(platform,settings.fetch_per_platform,refresh))
            except BridgeError as exc:
                errors[platform]=str(exc)
    else:
        if refresh:
            try:
                errors.update(collect(settings)["errors"])
            except (BridgeError,subprocess.TimeoutExpired) as exc:
                errors["collection"]=str(exc)
        items=pool.candidates(settings,include_seen)
        from .assessment import current
        pending=sum(not current(i) for i in items)
        items=[i for i in items if current(i)]
        if pending:
            errors["pending_assessment"] = str(pending)+" 条候选待内容审核，暂不交付"
        with pool.connect(settings) as db:
            row=db.execute("SELECT value FROM meta WHERE key='last_collection'").fetchone()
        if row:
            errors.update(json.loads(row[0]).get("errors",{}))
        else:
            errors["collection"]="信息池尚未采集，请先运行 mybot collect"
    ranked,stats=rank(items,replace(settings,digest_limit=settings.digest_limit*3),
                      set(load_sent(settings.state_file)),include_seen,now)
    if client is None:
        ranked,warning=diversify_embeddings(settings,ranked,settings.digest_limit)
        errors.update(warning)
    return DigestResult(now or utc_now(),ranked[:settings.digest_limit],errors,stats)
