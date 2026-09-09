"""SMTP outbox. Unknown delivery outcome never silently retries."""
import json
import os
import smtplib
import ssl
from datetime import timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime

from . import pool
from .digest import render_markdown, utc_now


def credentials(settings):
    path = settings.state_file.parent / "email-secret.json"
    secret = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    sender = settings.email_from or os.environ.get("MYBOT_SMTP_USER","") or secret.get("user","")
    password = os.environ.get("MYBOT_SMTP_PASSWORD","") or secret.get("password","")
    if not sender or not password or not settings.email_to:
        raise ValueError("邮件尚未配置：设置 email.from / email.to；SMTP 授权码放入 MYBOT_SMTP_PASSWORD 或 .data/mybot/email-secret.json 的 password 字段。")
    return sender,password


def send(settings,result, smtp_factory=smtplib.SMTP_SSL):
    sender,password=credentials(settings)
    if not result.items:
        return {"status":"empty"}
    day=result.generated_at.astimezone(timezone(timedelta(hours=8))).date().isoformat()
    delivery_id="radar-"+day
    # Persist exact batch BEFORE networking, serialize competing sends.
    with pool.connect(settings) as db:
        db.execute("BEGIN IMMEDIATE")
        previous=db.execute("SELECT status FROM outbox WHERE id=?",(delivery_id,)).fetchone()
        if previous:
            return {"status":previous[0],"id":delivery_id,"already_exists":True}
        db.execute("INSERT INTO outbox VALUES(?,?,?,?,?)",
            (delivery_id,"sending",json.dumps(result.items,ensure_ascii=False),utc_now().isoformat(),""))
    message=EmailMessage()
    message["From"]=sender
    message["To"]=settings.email_to
    message["Subject"]="AI 信息雷达 · "+day
    message["Date"]=format_datetime(utc_now())
    message["Message-ID"]="<"+delivery_id+"@mybot.local>"
    message.set_content(render_markdown(result))
    state="failed"
    try:
        with smtp_factory(settings.smtp_host,settings.smtp_port,context=ssl.create_default_context(),timeout=30) as smtp:
            smtp.login(sender,password)
            state="uncertain"
            refused=smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            # QUIT failures after accepted DATA must not turn accepted into failed.
            state="sent"
    except (smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused,smtplib.SMTPDataError,
            smtplib.SMTPAuthenticationError) as exc:
        state="failed"
        error=type(exc).__name__
    except Exception as exc:
        error=type(exc).__name__
    else:
        error=""
    with pool.connect(settings) as db:
        db.execute("UPDATE outbox SET status=?,error=? WHERE id=?",(state,error,delivery_id))
        if state=="sent":
            for item in result.items:
                db.execute("UPDATE items SET sent_at=? WHERE key=?",(utc_now().isoformat(),item["_mybot_key"]))
    if state!="sent":
        raise RuntimeError("邮件投递状态："+state+"；错误："+error+"。为防重复，当天不会自动重试，请检查 outbox。")
    return {"status":state,"id":delivery_id,"count":len(result.items)}
