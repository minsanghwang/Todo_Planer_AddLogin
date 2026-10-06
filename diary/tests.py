"""5일 실험 규칙 테스트. 하루에 한 건만 만들 수 있어서, '오늘' 날짜를 바꿔 가며 5일을 흉내 낸다."""
import json
from contextlib import contextmanager
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase


@contextmanager
def seoul_today(d):
    with mock.patch("django.utils.timezone.localdate", return_value=d):
        yield


class ExperimentRules(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("exp.user", password="Test-pw-for-unit-tests-1")
        self.client.force_login(self.user)

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def fix(self):
        return self.post("/api/experiment/fix/", {"question": "q", "metricName": "m", "unit": "분", "planRule": "처음 규칙"})

    def day(self, d, value, note=""):
        with seoul_today(d):
            return self.post("/api/experiment/days/", {"value": value, "note": note})

    def test_settings_fixed_only_once(self):
        self.assertEqual(self.fix().status_code, 201)
        self.assertEqual(self.fix().status_code, 400)

    def test_day_needs_fixed_settings_and_value(self):
        self.assertEqual(self.day(date(2026, 10, 6), 10).status_code, 400)  # 설정 전
        self.fix()
        self.assertEqual(self.day(date(2026, 10, 6), "").status_code, 400)  # 값이 빠짐
        self.assertEqual(self.day(date(2026, 10, 6), "abc").status_code, 400)

    def test_same_date_overwrites_instead_of_duplicating(self):
        self.fix()
        self.day(date(2026, 10, 6), 10)
        r = self.day(date(2026, 10, 6), 25)
        days = r.json()["days"]
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0]["value"], "25.00")

    def test_rule_change_only_between_day2_and_day3(self):
        self.fix()
        rc = lambda: self.post("/api/experiment/rule-change/", {"reason": "너무 빡빡해서", "newRule": "새 규칙"})
        self.assertEqual(rc().status_code, 400)            # 0일 기록 → 불가
        self.day(date(2026, 10, 6), 10)
        self.assertEqual(rc().status_code, 400)            # 1일 기록 → 불가
        self.day(date(2026, 10, 7), 20)
        # 규칙을 바꾸기 전에는 3일차 기록이 막힌다
        self.assertEqual(self.day(date(2026, 10, 8), 30).status_code, 400)
        r = rc()
        self.assertEqual(r.status_code, 201)
        change = r.json()["ruleChange"]
        self.assertEqual(change["day1"]["date"], "2026-10-06")  # 1일차 기록을 정확히 가리킴
        self.assertEqual(change["day2"]["date"], "2026-10-07")  # 2일차 기록을 정확히 가리킴
        self.assertEqual(change["beforeRule"], "처음 규칙")
        self.assertTrue(change["changedAt"])
        self.assertEqual(rc().status_code, 400)            # 두 번째 변경 불가
        self.assertEqual(self.day(date(2026, 10, 8), 30).status_code, 201)  # 이제 3일차 가능

    def test_rule_change_requires_reason(self):
        self.fix()
        self.day(date(2026, 10, 6), 1)
        self.day(date(2026, 10, 7), 1)
        r = self.post("/api/experiment/rule-change/", {"reason": "", "newRule": "새 규칙"})
        self.assertEqual(r.status_code, 400)

    def test_exactly_five_days_max_and_comparison(self):
        self.fix()
        self.day(date(2026, 10, 6), "10")
        self.day(date(2026, 10, 7), "20")
        self.post("/api/experiment/rule-change/", {"reason": "r", "newRule": "n"})
        self.day(date(2026, 10, 8), "30")
        self.day(date(2026, 10, 9), "40")
        r = self.day(date(2026, 10, 10), "50")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.day(date(2026, 10, 11), "60").status_code, 400)  # 6일째는 불가
        data = self.client.get("/api/experiment/").json()
        self.assertEqual(len(data["days"]), 5)
        self.assertEqual(data["total"]["sum"], "150.0")      # 10+20+30+40+50
        self.assertEqual(data["total"]["average"], "30.0")
        cmp = data["comparison"]
        self.assertEqual((cmp["before"]["count"], cmp["before"]["sum"], cmp["before"]["average"]), (2, "30.0", "15.0"))
        self.assertEqual((cmp["after"]["count"], cmp["after"]["sum"], cmp["after"]["average"]), (3, "120.0", "40.0"))
        # 전후 비교가 같은 지표·단위·계산 규칙을 쓴다
        self.assertEqual((cmp["metric"], cmp["unit"]), ("m", "분"))

    def test_rounding_is_half_up_to_one_decimal(self):
        self.fix()
        self.day(date(2026, 10, 6), "0.05")   # 0.05 -> 0.1 (ROUND_HALF_UP)
        self.day(date(2026, 10, 7), "0.10")
        d = self.client.get("/api/experiment/").json()["total"]
        self.assertEqual(d["sum"], "0.2")      # 0.15 -> 0.2
        self.assertEqual(d["average"], "0.1")  # 0.075 -> 0.1

    def test_outlier_is_flagged_but_still_counted(self):
        self.fix()
        for i, v in enumerate(["10", "11", "12", "100"]):
            if i == 2:
                self.post("/api/experiment/rule-change/", {"reason": "r", "newRule": "n"})
            self.day(date(2026, 10, 6 + i), v)
        d = self.client.get("/api/experiment/").json()
        flags = [x["outlier"] for x in d["days"]]
        self.assertEqual(flags, [False, False, False, True])
        self.assertEqual(d["total"]["sum"], "133.0")  # 튀는 값도 계산에 그대로 포함

    def test_week_start_is_monday(self):
        self.fix()
        self.day(date(2026, 10, 7), 1)  # 2026-10-07 은 수요일
        d = self.client.get("/api/experiment/").json()["days"][0]
        self.assertEqual(d["weekStart"], "2026-10-05")  # 그 주의 월요일

    def test_experiments_are_private_per_account(self):
        self.fix()
        self.day(date(2026, 10, 6), 77)
        other = User.objects.create_user("exp.other", password="Test-pw-for-unit-tests-2")
        self.client.force_login(other)
        data = self.client.get("/api/experiment/").json()
        self.assertIsNone(data["settings"])
        self.assertEqual(data["days"], [])


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
