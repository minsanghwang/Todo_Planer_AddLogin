"""계획 수정 이유·하루 완료 기록·전후 비교 테스트."""
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase

from .api import plan_snapshot
from .models import Plan, PlanVersion, Todo

KST = ZoneInfo("Asia/Seoul")


def kst(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=KST)


class PlanEditReason(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reason.user", password="Test-pw-for-unit-tests-1")
        self.client.force_login(self.user)
        self.plan = Plan.objects.create(owner=self.user, title="처음 계획", period_start=date(2026, 10, 1),
                                        period_end=date(2026, 10, 31), estimated_hours=4, success_criteria="주 3회")

    def put(self, **over):
        body = {"title": "처음 계획", "periodStart": "2026-10-01", "periodEnd": "2026-10-31",
                "successCriteria": "주 3회", "estimatedTime": 4, "topicTags": [], "reason": "이유"}
        body.update(over)
        return self.client.put(f"/api/plans/{self.plan.id}/", json.dumps(body), content_type="application/json")

    def test_edit_without_reason_is_rejected_and_nothing_changes(self):
        r = self.put(title="바꾼 계획", reason="  ")
        self.assertEqual(r.status_code, 400)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.title, "처음 계획")
        self.assertEqual(PlanVersion.objects.count(), 0)

    def test_edit_keeps_old_version_time_and_reason(self):
        r = self.put(estimatedTime=2, reason="하루에 끝내기엔 너무 길어서")
        self.assertEqual(r.status_code, 200)
        h = r.json()["history"]
        self.assertEqual(len(h), 1)                                  # 고치면 이전 버전은 정확히 1건
        self.assertEqual((h[0]["estimatedTime"], h[0]["reason"]), (4, "하루에 끝내기엔 너무 길어서"))
        self.assertTrue(h[0]["editedAt"])
        self.assertEqual(r.json()["estimatedTime"], 2)
        self.assertEqual(Plan.objects.filter(owner=self.user).count(), 1)   # 계획이 새로 늘지 않는다

    def test_save_without_any_change_is_rejected(self):
        r = self.put()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(PlanVersion.objects.count(), 0)

    def test_improvement_note_does_not_add_a_version(self):
        r = self.client.post(f"/api/plans/{self.plan.id}/notes/", json.dumps({"text": "예상 시간 늘리기"}), content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["history"], [])
        self.assertEqual(len(r.json()["improvementNotes"]), 1)


class DailyStats(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("daily.user", password="Test-pw-for-unit-tests-2")
        self.client.force_login(self.user)
        self.plan = Plan.objects.create(owner=self.user, title="P", period_start=date(2026, 10, 1), period_end=date(2026, 10, 31), estimated_hours=4)

    def done(self, when, title="t", owner=None):
        return Todo.objects.create(owner=owner or self.user, title=title, due_date=date(2026, 10, 31), status="completed", completed_at=when)

    def daily(self, change=None):
        return self.client.get("/api/daily/" + (f"?change={change}" if change else "")).json()

    def change_at(self, when, **kw):
        v = PlanVersion.objects.create(plan=self.plan, owner=self.user, snapshot=plan_snapshot(self.plan), reason="이유")
        PlanVersion.objects.filter(pk=v.pk).update(edited_at=when)   # 시각을 일부러 정해 둔다
        self.plan.estimated_hours = 2
        self.plan.save()
        return v

    def test_days_sum_average_and_hand_total(self):
        for d, n in [(6, 1), (7, 2), (8, 3), (9, 3), (10, 1)]:
            for i in range(n):
                self.done(kst(2026, 10, d, 9 + i))
        x = self.daily()
        self.assertEqual([r["count"] for r in x["days"]], [1, 2, 3, 3, 1])
        self.assertEqual((x["total"]["sum"], x["total"]["average"], x["total"]["days"]), (10, "2.0", 5))
        self.assertEqual(sum(x["total"]["values"]), x["total"]["sum"])       # 손으로 더한 값 = 화면 합계

    def test_seoul_midnight_and_missing_days(self):
        self.done(kst(2026, 10, 7, 0, 30))     # 서울 0시 30분 = 같은 날(10-07)로 센다
        self.done(kst(2026, 10, 6, 23, 50))    # 앞 날짜
        self.done(kst(2026, 10, 9, 10))        # 10-08은 기록 없음 -> 0으로 채우지 않는다
        x = self.daily()
        self.assertEqual([(r["date"], r["count"]) for r in x["days"]], [("2026-10-06", 1), ("2026-10-07", 1), ("2026-10-09", 1)])
        self.assertEqual(x["total"]["days"], 3)

    def test_rounding_is_half_up(self):
        for d, n in [(6, 1), (7, 1), (8, 1), (9, 2)]:    # 합계 5 / 4일 = 1.25
            for i in range(n):
                self.done(kst(2026, 10, d, 9 + i))
        self.assertEqual(self.daily()["total"]["average"], "1.3")

    def test_outlier_flagged_but_counted(self):
        for d, n in [(6, 1), (7, 1), (8, 1), (9, 10)]:
            for i in range(n):
                self.done(kst(2026, 10, d, 9 + i))
        x = self.daily()
        self.assertEqual([r["outlier"] for r in x["days"]], [False, False, False, True])
        self.assertEqual(x["total"]["sum"], 13)

    def test_week_start_is_monday(self):
        self.done(kst(2026, 10, 7))           # 수요일
        self.assertEqual(self.daily()["days"][0]["weekStart"], "2026-10-05")

    def test_before_after_uses_same_metric_unit_rule(self):
        for d, n in [(6, 1), (7, 2)]:
            for i in range(n):
                self.done(kst(2026, 10, d, 9 + i))
        self.change_at(kst(2026, 10, 7, 23, 0))      # 2일차 뒤, 3일차 앞
        for d, n in [(8, 3), (9, 3), (10, 1)]:
            for i in range(n):
                self.done(kst(2026, 10, d, 9 + i))
        x = self.daily()
        c = x["comparison"]
        self.assertEqual((c["before"]["days"], c["before"]["sum"], c["before"]["average"]), (2, 3, "1.5"))
        self.assertEqual((c["after"]["days"], c["after"]["sum"], c["after"]["average"]), (3, 7, "2.3"))
        self.assertEqual((c["metric"], c["unit"]), (x["metric"], x["unit"]))     # 전후가 같은 지표·단위
        self.assertEqual(c["before"]["sum"] + c["after"]["sum"], x["total"]["sum"])
        self.assertEqual([r["side"] for r in x["days"]], ["before", "before", "after", "after", "after"])
        ch = x["changes"][0]
        self.assertEqual(ch["reason"], "이유")
        self.assertTrue(ch["changedAt"])
        self.assertEqual(ch["diff"][0]["field"], "예상 시간(시간)")

    def test_change_on_morning_of_day3_counts_day3_as_after(self):
        self.done(kst(2026, 10, 6, 10))
        self.done(kst(2026, 10, 7, 10))
        self.change_at(kst(2026, 10, 8, 8, 0))        # 3일차 아침, 할 일을 하기 전
        self.done(kst(2026, 10, 8, 9))
        self.assertEqual([r["side"] for r in self.daily()["days"]], ["before", "before", "after"])

    def test_other_accounts_are_not_mixed_in(self):
        other = User.objects.create_user("daily.other", password="Test-pw-for-unit-tests-3")
        self.done(kst(2026, 10, 6), owner=other)
        self.done(kst(2026, 10, 6), title="mine")
        self.assertEqual(self.daily()["total"]["sum"], 1)
        self.client.force_login(other)
        self.assertEqual(self.client.get("/api/daily/?change=999999").status_code, 404)   # 남의/없는 변경 번호는 404
        self.assertEqual(self.daily()["total"]["sum"], 1)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/daily/").status_code, 401)


class ImportFromT06(TestCase):
    """6번 다이어리(단일 HTML)가 내보내는 JSON 모양 그대로 내 계정으로 옮겨지는지."""

    V1 = {
        "exportedAt": "2026-10-05T12:00:00.000Z",
        "topics": ["운동", "러닝"],
        "plans": [{
            "id": "id_plan1", "title": "6번 계획", "topicTags": ["운동", "러닝"], "periodStart": "2026-10-01",
            "periodEnd": "2026-10-31", "priority": 1, "successCriteria": "주 3회", "estimatedTime": 10,
            "improvementNotes": [{"id": "id_n1", "text": "예상 시간 늘리기", "addedAt": "2026-10-04T01:00:00.000Z"}],
            "history": [{"title": "6번 계획(처음)", "topicTags": ["운동"], "periodStart": "2026-10-01", "periodEnd": "2026-10-20",
                         "priority": 1, "successCriteria": "주 2회", "estimatedTime": 6, "editedAt": "2026-10-03T01:00:00.000Z"}],
            "deleted": False, "createdAt": "2026-10-01T00:00:00.000Z", "updatedAt": "2026-10-03T01:00:00.000Z",
        }, {"id": "id_plan_gone", "title": "지운 계획", "periodStart": "2026-10-01", "periodEnd": "2026-10-02",
            "estimatedTime": 1, "deleted": True}],
        "todos": [{
            "id": "id_todo1", "planId": "id_plan1", "title": "6번 할 일", "tags": ["러닝"], "periodStart": "2026-10-02",
            "dueDate": "2026-10-10", "successCriteria": "5km", "estimatedTime": 1.5, "priority": 1, "status": "completed",
            "completedAt": "2026-10-05T09:30:00.000Z", "history": [], "deleted": False,
        }, {"id": "id_todo_gone", "planId": None, "title": "지운 할 일", "dueDate": "2026-10-11", "estimatedTime": 1, "deleted": True}],
        "execRecords": [
            {"id": "id_r1", "todoId": "id_todo1", "start": "2026-10-05T08:00", "end": "2026-10-05T09:30", "actualMinutes": 90,
             "blockedReason": "비가 와서 멈춤", "createdAt": "2026-10-05T00:00:00.000Z"},
            {"id": "id_r_orphan", "todoId": "id_todo_gone", "start": "2026-10-05T08:00", "end": "2026-10-05T09:00", "actualMinutes": 60},
        ],
    }

    def setUp(self):
        self.me = User.objects.create_user("t06.owner", password="Test-pw-for-unit-tests-3")
        self.other = User.objects.create_user("t06.other", password="Test-pw-for-unit-tests-4")
        self.client.force_login(self.me)

    def test_imports_into_my_account_only(self):
        r = self.client.post("/api/import/", json.dumps(self.V1), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["plans"], r.json()["todos"]), (1, 1))  # 지운 것은 가져오지 않는다
        data = self.client.get("/api/data/").json()
        self.assertEqual([p["title"] for p in data["plans"]], ["6번 계획"])
        plan = data["plans"][0]
        self.assertEqual(plan["topicTags"], ["운동", "러닝"])
        self.assertEqual(plan["improvementNotes"][0]["text"], "예상 시간 늘리기")
        self.assertEqual(plan["history"][0]["title"], "6번 계획(처음)")     # 6번의 수정 전 계획도 그대로
        todo = data["todos"][0]
        self.assertEqual((todo["title"], todo["status"], todo["planId"]), ("6번 할 일", "completed", plan["id"]))
        self.assertTrue(todo["completedAt"])
        recs = data["execRecords"]
        self.assertEqual(len(recs), 1)                                       # 지운 할 일에 딸린 기록은 건너뜀
        self.assertEqual((recs[0]["actualMinutes"], recs[0]["blockedReason"]), (90, "비가 와서 멈춤"))
        # 다른 계정에는 하나도 보이지 않는다
        self.client.force_login(self.other)
        other = self.client.get("/api/data/").json()
        self.assertEqual((other["plans"], other["todos"], other["execRecords"]), ([], [], []))

    def test_bad_file_is_rejected_without_partial_import(self):
        broken = {"plans": [{"title": "정상", "periodStart": "2026-10-01", "periodEnd": "2026-10-02", "estimatedTime": 1},
                            {"title": "날짜 없음", "estimatedTime": 1}]}
        r = self.client.post("/api/import/", json.dumps(broken), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/api/data/").json()["plans"], [])  # 일부만 들어가지 않는다(전부 취소)
