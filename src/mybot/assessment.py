"""Bounded and cached AI/value assessments. Fail closed for delivery."""
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from . import pool
from .openbiliclaw import decode_json_output


def signature(item):
    return hashlib.sha256(json.dumps([item.get(k, "") for k in ("title", "description", "body_text")],ensure_ascii=False).encode()).hexdigest()


def current(item):
    return item.get("assessment", {}).get("signature") == signature(item)


def validate(data, requested):
    rows = data.get("items", [])
    if not isinstance(rows, list) or len(rows) != len(requested):
        raise ValueError("Incomplete model assessment")
    output = {}
    for row in rows:
        key = row.get("id")
        if key not in requested or key in output:
            raise ValueError("Unexpected assessment id")
        for field in ("ai", "value"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (float,int)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Invalid assessment score")
        if row.get("category") not in ("news","tutorial","workflow","experience","project","tool","other"):
            raise ValueError("Invalid assessment category")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError("Missing assessment explanation")
        output[key] = {k:row[k] for k in ("ai","value","category","reason")}
        output[key]["reason"] = output[key]["reason"][:400]
    return output


def assess_pending(settings, limit=24):
    # Oldest pending first prevents popularity/score starving niche candidates.
    pending = sorted((i for i in pool.candidates(settings) if not current(i)),key=lambda i:i["first_discovered_at"])[:limit]
    assessed = 0
    for start in range(0,len(pending),12):
        batch = pending[start:start+12]
        request = [{"id":i["_mybot_key"],"title":str(i.get("title",""))[:300],
                    "description":str(i.get("description") or i.get("body_text") or "")[:1000]} for i in batch]
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        result = subprocess.run([str(settings.openbiliclaw_python),str(Path(__file__).with_name("upstream_assess.py"))],
            input=json.dumps(request,ensure_ascii=False),capture_output=True,text=True,encoding="utf-8",env=env,
            cwd=settings.openbiliclaw_root,timeout=settings.bridge_timeout_seconds)
        if result.returncode:
            raise RuntimeError("内容审核服务失败；未审核内容暂不交付（退出码 %s）" % result.returncode)
        output = validate(decode_json_output(result.stdout),{i["_mybot_key"] for i in batch})
        with pool.connect(settings) as db:
            for item in batch:
                value = output[item["_mybot_key"]]
                value["signature"] = signature(item)
                row = db.execute("SELECT payload FROM items WHERE key=?",(item["_mybot_key"],)).fetchone()
                payload = json.loads(row[0])
                if signature(payload) != signature(item):
                    continue
                payload["assessment"] = value
                db.execute("UPDATE items SET payload=? WHERE key=?",(json.dumps(payload,ensure_ascii=False),item["_mybot_key"]))
                assessed += 1
    return assessed
