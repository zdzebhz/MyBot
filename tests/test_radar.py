from __future__ import annotations

import json
import smtplib
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mybot import pool
from mybot.assessment import signature, current, validate
from mybot.digest import DigestResult, load_sent, mark_sent
from mybot.radar import rank, build, diversify_embeddings
from mybot.mail import send
from mybot.worker import due
from test_digest import make_settings

NOW = datetime(2026,9,9,9,tzinfo=timezone.utc)


def item(key="BV1234567890", title="AI 大模型实战教程与开源工作流"):
    return dict(source_platform="bilibili",bvid=key,title=title,
                content_url="https://www.bilibili.com/video/"+key,
                published_at=(NOW-timedelta(days=180)).isoformat())


def assessed(value, ai=0.9, quality=0.8, category="tutorial"):
    value=dict(value)
    value["assessment"]=dict(signature=signature(value),ai=ai,value=quality,category=category,reason="提供可操作的 AI 实践教程")
    return value


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings=make_settings(Path(self.tmp.name))

    def test_evergreen_six_months_old_eligible(self):
        ranked,_=rank([assessed(item())],self.settings,set(),now=NOW)
        self.assertEqual(len(ranked),1)

    def test_reason_cannot_inject_ai_relevance(self):
        raw=item(title="普通旅行经历")
        raw["reason"]="AI 大模型 Agent MCP"
        self.assertEqual(rank([raw],self.settings,set(),now=NOW)[0],[])

    def test_incidental_ai_and_low_value_are_filtered(self):
        for raw in [assessed(item(),ai=0.3),assessed(item(),quality=0.2)]:
            self.assertEqual(rank([raw],self.settings,set(),now=NOW)[0],[])

    def test_model_category_overrides_product_keyword_for_news(self):
        news=assessed(item(title="AI 产品发布"),category="news")
        ranked,_=rank([news],self.settings,set(),now=NOW)
        self.assertEqual(ranked[0]["_mybot_category"],"news")
        self.assertLess(ranked[0]["_mybot_score_parts"]["freshness"],0.01)

    def test_news_freshness_greater_weight_than_tutorial(self):
        raw=item()
        raw["published_at"]=NOW.isoformat()
        a=rank([assessed(raw,category="news")],self.settings,set(),now=NOW)[0][0]
        b=rank([assessed(raw)],self.settings,set(),now=NOW)[0][0]
        self.assertGreater(a["_mybot_score_parts"]["freshness"],b["_mybot_score_parts"]["freshness"])

    def test_interest_is_bounded_and_no_popularity_boost(self):
        a=assessed(item())
        b=dict(a,confidence=1000000,view_count=999999999)
        ra=rank([a],self.settings,set(),now=NOW)[0][0]
        rb=rank([b],self.settings,set(),now=NOW)[0][0]
        self.assertAlmostEqual(rb["_mybot_score"]-ra["_mybot_score"],3)

    def test_canonical_urls_tracking_and_xhs_aliases(self):
        a=item()
        b=dict(a,content_url=a["content_url"]+"?spm_id_from=123")
        self.assertEqual(pool.canonical_key(a),pool.canonical_key(b))
        a=dict(source_platform="xiaohongshu",content_url="https://www.xiaohongshu.com/explore/aabb11?xsec_token=x")
        b=dict(a,content_url="https://www.xiaohongshu.com/discovery/item/aabb11?utm_source=y")
        self.assertEqual(pool.canonical_key(a),pool.canonical_key(b))

    def test_pool_preserves_first_seen_read_and_sent(self):
        raw=item()
        pool.ingest(self.settings,[raw],"2026-01-01")
        with pool.connect(self.settings) as db:
            db.execute("UPDATE items SET sent_at='2026-01-02',read_at='2026-01-02'")
        pool.ingest(self.settings,[raw],"2026-09-09")
        self.assertEqual(pool.candidates(self.settings),[])
        self.assertEqual(pool.candidates(self.settings,True)[0]["first_discovered_at"],"2026-01-01")

    def test_cross_platform_title_already_sent_excluded(self):
        a=item()
        b=dict(a,source_platform="xiaohongshu",content_url="https://www.xiaohongshu.com/explore/abcdef")
        pool.ingest(self.settings,[a,b],NOW.isoformat())
        with pool.connect(self.settings) as db:
            db.execute("UPDATE items SET sent_at=? WHERE key=?",(NOW.isoformat(),pool.canonical_key(a)))
        self.assertEqual(pool.candidates(self.settings),[])

    def test_new_old_content_preview_does_not_mark_sent(self):
        pool.ingest(self.settings,[assessed(item())],NOW.isoformat())
        with patch("mybot.radar.diversify_embeddings",side_effect=lambda s,r,l:(r[:l],{})):
            self.assertEqual(len(build(self.settings,now=NOW).items),1)
            self.assertEqual(len(build(self.settings,now=NOW).items),1)
        with pool.connect(self.settings) as db:
            self.assertIsNone(db.execute("SELECT sent_at FROM items").fetchone()[0])

    def test_unassessed_or_changed_metadata_cannot_ship(self):
        raw=assessed(item())
        raw["title"]+="修改"
        self.assertFalse(current(raw))
        pool.ingest(self.settings,[raw],NOW.isoformat())
        with patch("mybot.radar.diversify_embeddings",side_effect=lambda s,r,l:(r,{})):
            result=build(self.settings,now=NOW)
        self.assertEqual(result.items,[])
        self.assertIn("pending_assessment",result.errors)

    def test_sent_ledger_keeps_old_entries_and_corruption_fails(self):
        mark_sent(self.settings.state_file,[dict(item_key="old")],NOW-timedelta(days=400))
        mark_sent(self.settings.state_file,[dict(item_key="new")],NOW)
        self.assertIn("old",load_sent(self.settings.state_file))
        self.settings.state_file.write_text("{broken",encoding="utf-8")
        with self.assertRaises(ValueError):
            load_sent(self.settings.state_file)

    def test_assessment_validation_rejects_missing_nan_injected_id(self):
        good=dict(id="x",ai=.9,value=.8,category="tutorial",reason="教程")
        self.assertIn("x",validate(dict(items=[good]),{"x"}))
        for rows in [[],[dict(good,id="y")],[dict(good,ai=float("nan"))],[dict(good,ai=True)],[dict(good,category="execute")]]:
            with self.assertRaises(ValueError):
                validate(dict(items=rows),{"x"})

    def test_embedding_failure_is_visible_and_bounded(self):
        ranked=rank([assessed(item())],self.settings,set(),now=NOW)[0]
        with patch("mybot.radar.urlopen",side_effect=TimeoutError) as opener:
            result,errors=diversify_embeddings(self.settings,ranked,10)
        self.assertEqual(len(result),1)
        self.assertIn("embedding",errors)
        self.assertEqual(opener.call_count,1)

    def test_local_read_only_and_unknown_key_rejected(self):
        raw=item()
        pool.ingest(self.settings,[raw],NOW.isoformat())
        pool.mark_read(self.settings,pool.canonical_key(raw),NOW.isoformat())
        self.assertEqual(pool.candidates(self.settings),[])
        with self.assertRaises(ValueError):
            pool.mark_read(self.settings,"missing",NOW.isoformat())

    def test_worker_clock_durable_and_throttled(self):
        self.assertTrue(due(self.settings,"test",NOW,3600))
        self.assertFalse(due(self.settings,"test",NOW+timedelta(minutes=30),3600))
        self.assertTrue(due(self.settings,"test",NOW+timedelta(hours=1),3600))


class FakeSMTP:
    sent=0
    mode="ok"
    def __init__(self,*args,**kwargs): pass
    def __enter__(self): return self
    def __exit__(self,*args):
        if self.mode=="quit_error": raise OSError()
    def login(self,*args):
        if self.mode=="auth_error": raise smtplib.SMTPAuthenticationError(535,b"no")
    def send_message(self,message):
        type(self).sent+=1
        if self.mode=="uncertain": raise OSError()
        if self.mode=="rejected": raise smtplib.SMTPDataError(550,b"no")
        return {}


class MailTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings=replace(make_settings(Path(self.tmp.name)),email_from="sender@example.com",email_to="receiver@example.com")
        self.cred=patch("mybot.mail.credentials",return_value=("sender@example.com","test-only"))
        self.cred.start()
        self.addCleanup(self.cred.stop)
        raw=assessed(item())
        pool.ingest(self.settings,[raw],NOW.isoformat())
        raw["_mybot_key"]=pool.canonical_key(raw)
        self.result=DigestResult(NOW,[raw],{},dict(received=1))
        FakeSMTP.mode="ok"
        FakeSMTP.sent=0

    def test_success_marks_only_after_acceptance_and_no_duplicate(self):
        self.assertEqual(send(self.settings,self.result,FakeSMTP)["status"],"sent")
        self.assertEqual(pool.candidates(self.settings),[])
        self.assertTrue(send(self.settings,self.result,FakeSMTP)["already_exists"])
        self.assertEqual(FakeSMTP.sent,1)

    def test_empty_has_no_outbox(self):
        self.assertEqual(send(self.settings,replace(self.result,items=[]),FakeSMTP)["status"],"empty")
        with pool.connect(self.settings) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0],0)

    def test_failures_do_not_mark_sent_and_never_auto_retry(self):
        for mode in ["auth_error","uncertain","rejected"]:
            with self.subTest(mode=mode):
                with pool.connect(self.settings) as db:
                    db.execute("DELETE FROM outbox")
                FakeSMTP.mode=mode
                with self.assertRaises(RuntimeError):
                    send(self.settings,self.result,FakeSMTP)
                self.assertEqual(len(pool.candidates(self.settings)),1)
                previous=FakeSMTP.sent
                self.assertTrue(send(self.settings,self.result,FakeSMTP)["already_exists"])
                self.assertEqual(FakeSMTP.sent,previous)

    def test_quit_failure_does_not_unmark_accepted_mail(self):
        FakeSMTP.mode="quit_error"
        self.assertEqual(send(self.settings,self.result,FakeSMTP)["status"],"sent")
        self.assertEqual(pool.candidates(self.settings),[])
