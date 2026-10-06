"""JSON API. 모든 자료 요청은 여기를 지난다.

주인 확인(남의 자료 차단)의 핵심 위치:
  - require_login ........ 로그인 안 한 요청을 401로 거절
  - owned_or_404 ......... 한 건 조회·수정·삭제에서 owner=request.user 조건으로만 찾고, 없으면 404
  - 목록은 항상 Model.objects.filter(owner=request.user, ...) 로만 만든다 (data_view, export_view)
요청 본문·헤더·주소에 owner, user, user_id 같은 값을 실어 보내도 읽지 않는다(허용 목록 방식).
"""
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from statistics import median
from zoneinfo import ZoneInfo

from django.contrib.auth import update_session_auth_hash, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (
    ExecRecord, Experiment, ExperimentDay, ImprovementNote, Plan, PlanVersion, RuleChange, Todo, TodoVersion,
)

SEOUL = ZoneInfo("Asia/Seoul")


# ------------------------------------------------------------------ 공통 도구
def err(message, status=400):
    return JsonResponse({"detail": message}, status=status, json_dumps_params={"ensure_ascii": False})


def ok(payload=None, status=200):
    return JsonResponse(payload if payload is not None else {"ok": True}, status=status,
                        json_dumps_params={"ensure_ascii": False})


def require_login(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return err("로그인이 필요합니다.", 401)
        return view(request, *args, **kwargs)
    return wrapper


def body(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise BadRequest("JSON 형식이 올바르지 않습니다.")
    if not isinstance(data, dict):
        raise BadRequest("JSON 객체가 필요합니다.")
    return data


class BadRequest(Exception):
    pass


class NotFound(Exception):
    pass


def api(view):
    """BadRequest / NotFound를 JSON 응답으로 바꾼다."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except BadRequest as e:
            return err(str(e), 400)
        except NotFound:
            return err("찾을 수 없습니다.", 404)
    return wrapper


def owned_or_404(model, user, pk, **extra):
    """주인 확인의 한가운데. 남의 자료는 '없는 자료'와 똑같이 404로 답한다."""
    try:
        pk = int(pk)
    except (TypeError, ValueError):
        raise NotFound()
    obj = model.objects.filter(owner=user, pk=pk, **extra).first()
    if obj is None:
        raise NotFound()
    return obj


def parse_date(value, field, required=True):
    if value in (None, ""):
        if required:
            raise BadRequest(f"{field}을(를) 입력해 주세요.")
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise BadRequest(f"{field} 형식이 올바르지 않습니다.")


def parse_dt(value, field):
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        raise BadRequest(f"{field} 형식이 올바르지 않습니다.")
    if timezone.is_naive(dt):
        dt = dt.replace(tzinfo=SEOUL)
    return dt


def parse_hours(value):
    try:
        h = float(value)
    except (TypeError, ValueError):
        raise BadRequest("예상 시간은 숫자여야 합니다.")
    if h < 0 or h > 10000:
        raise BadRequest("예상 시간 범위가 올바르지 않습니다.")
    return h


def clean_tags(value):
    if not isinstance(value, list):
        return []
    out = []
    for t in value:
        t = str(t).strip()[:50]
        if t and t not in out:
            out.append(t)
    return out


def iso(dt):
    return dt.astimezone(SEOUL).isoformat() if dt else None


# ------------------------------------------------------------------ 직렬화 (화면이 쓰는 모양)
def plan_snapshot(p):
    return {
        "title": p.title, "topicTags": p.topic_tags, "periodStart": p.period_start.isoformat(),
        "periodEnd": p.period_end.isoformat(), "priority": p.priority,
        "successCriteria": p.success_criteria, "estimatedTime": p.estimated_hours,
    }


def todo_snapshot(t):
    return {
        "planId": str(t.plan_id) if t.plan_id else None, "title": t.title, "tags": t.tags,
        "periodStart": t.period_start.isoformat() if t.period_start else None,
        "dueDate": t.due_date.isoformat(), "successCriteria": t.success_criteria,
        "estimatedTime": t.estimated_hours, "priority": t.priority,
    }


def ser_plan(p):
    d = plan_snapshot(p)
    d["id"] = str(p.id)
    d["history"] = [dict(v.snapshot, editedAt=iso(v.edited_at)) for v in p.versions.all()]
    d["improvementNotes"] = [
        {"id": str(n.id), "text": n.text, "addedAt": iso(n.created_at)} for n in p.notes.all()
    ]
    return d


def ser_todo(t):
    d = todo_snapshot(t)
    d.update(id=str(t.id), status=t.status, completedAt=iso(t.completed_at),
             history=[dict(v.snapshot, editedAt=iso(v.edited_at)) for v in t.versions.all()])
    return d


def ser_record(r):
    return {"id": str(r.id), "todoId": str(r.todo_id), "start": iso(r.started_at), "end": iso(r.ended_at),
            "actualMinutes": r.actual_minutes, "blockedReason": r.blocked_reason}


def next_priority(qs):
    top = qs.order_by("-priority").values_list("priority", flat=True).first()
    return (top or 0) + 1


# ------------------------------------------------------------------ 계정
@require_login
def me_view(request):
    return ok({"username": request.user.get_username(), "today": timezone.localdate().isoformat()})


@require_login
@require_http_methods(["POST"])
@api
def password_view(request):
    data = body(request)
    old, new = data.get("oldPassword", ""), data.get("newPassword", "")
    if not request.user.check_password(old):
        raise BadRequest("현재 비밀번호가 올바르지 않습니다.")
    try:
        validate_password(new, request.user)
    except ValidationError as e:
        raise BadRequest(" ".join(e.messages))
    request.user.set_password(new)
    request.user.save()
    # 비밀번호가 바뀌면 이 계정의 다른 세션은 모두 무효가 된다. 지금 쓰는 세션만 새 해시로 갱신.
    update_session_auth_hash(request, request.user)
    return ok()


@require_login
@require_http_methods(["POST"])
@api
def account_delete_view(request):
    data = body(request)
    if not request.user.check_password(data.get("password", "")):
        raise BadRequest("비밀번호가 올바르지 않습니다.")
    user = request.user
    logout(request)
    user.delete()  # on_delete=CASCADE 로 이 계정의 계획·할 일·기록·실험이 모두 함께 지워진다
    return ok()


# ------------------------------------------------------------------ 전체 조회·내보내기·가져오기
def collect(user):
    plans = Plan.objects.filter(owner=user, deleted=False).order_by("priority", "id").prefetch_related("versions", "notes")
    todos = Todo.objects.filter(owner=user, deleted=False).order_by("priority", "id").prefetch_related("versions")
    records = ExecRecord.objects.filter(owner=user, todo__deleted=False).order_by("started_at")
    return {
        "plans": [ser_plan(p) for p in plans],
        "todos": [ser_todo(t) for t in todos],
        "execRecords": [ser_record(r) for r in records],
    }


@require_login
def data_view(request):
    out = collect(request.user)
    out["today"] = timezone.localdate().isoformat()
    return ok(out)


@require_login
def export_view(request):
    out = collect(request.user)
    out["experiment"] = experiment_payload(request.user)
    out["exportedAt"] = iso(timezone.now())
    out["username"] = request.user.get_username()
    resp = HttpResponse(json.dumps(out, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="diary-export-{timezone.localdate().isoformat()}.json"'
    return resp


@require_login
@require_http_methods(["POST"])
@api
@transaction.atomic
def import_view(request):
    """6번 다이어리에서 내보낸 JSON을 '내 계정'으로 옮긴다."""
    data = body(request)
    plan_map, todo_map = {}, {}
    for p in data.get("plans", []) or []:
        if p.get("deleted"):
            continue
        obj = Plan.objects.create(
            owner=request.user, title=str(p.get("title", ""))[:200] or "(제목 없음)",
            topic_tags=clean_tags(p.get("topicTags")), period_start=parse_date(p.get("periodStart"), "계획 시작일"),
            period_end=parse_date(p.get("periodEnd"), "계획 종료일"),
            priority=int(p.get("priority") or next_priority(Plan.objects.filter(owner=request.user))),
            success_criteria=str(p.get("successCriteria", "")), estimated_hours=parse_hours(p.get("estimatedTime") or 0),
        )
        plan_map[p.get("id")] = obj
        for h in p.get("history", []) or []:
            PlanVersion.objects.create(plan=obj, owner=request.user, snapshot={
                k: h.get(k) for k in ("title", "topicTags", "periodStart", "periodEnd", "priority", "successCriteria", "estimatedTime")
            } | {"importedEditedAt": h.get("editedAt")})
        for n in p.get("improvementNotes", []) or []:
            ImprovementNote.objects.create(plan=obj, owner=request.user, text=str(n.get("text", "")))
    for t in data.get("todos", []) or []:
        if t.get("deleted"):
            continue
        obj = Todo.objects.create(
            owner=request.user, plan=plan_map.get(t.get("planId")), title=str(t.get("title", ""))[:200] or "(제목 없음)",
            tags=clean_tags(t.get("tags")), period_start=parse_date(t.get("periodStart"), "시작일", required=False),
            due_date=parse_date(t.get("dueDate"), "마감일"), success_criteria=str(t.get("successCriteria", "")),
            estimated_hours=parse_hours(t.get("estimatedTime") or 0),
            priority=int(t.get("priority") or next_priority(Todo.objects.filter(owner=request.user))),
            status="completed" if t.get("status") == "completed" else "in_progress",
            completed_at=parse_dt(t["completedAt"], "완료 시각") if t.get("completedAt") else None,
        )
        todo_map[t.get("id")] = obj
    for r in data.get("execRecords", []) or []:
        todo = todo_map.get(r.get("todoId"))
        if not todo:
            continue
        start, end = parse_dt(r.get("start"), "시작 시각"), parse_dt(r.get("end"), "끝난 시각")
        ExecRecord.objects.create(
            owner=request.user, todo=todo, started_at=start, ended_at=end,
            actual_minutes=int(r.get("actualMinutes") or round((end - start).total_seconds() / 60)),
            blocked_reason=str(r.get("blockedReason", "")),
        )
    return ok({"plans": len(plan_map), "todos": len(todo_map)})


# ------------------------------------------------------------------ 계획
def plan_fields(data):
    title = str(data.get("title", "")).strip()
    if not title:
        raise BadRequest("제목을 입력해 주세요.")
    start, end = parse_date(data.get("periodStart"), "시작일"), parse_date(data.get("periodEnd"), "종료일")
    if end < start:
        raise BadRequest("종료일이 시작일보다 빠를 수 없습니다.")
    return dict(
        title=title[:200], topic_tags=clean_tags(data.get("topicTags")), period_start=start, period_end=end,
        success_criteria=str(data.get("successCriteria", "")).strip(),
        estimated_hours=parse_hours(data.get("estimatedTime")),
    )


@require_login
@require_http_methods(["POST"])
@api
def plan_create(request):
    f = plan_fields(body(request))
    p = Plan.objects.create(owner=request.user, priority=next_priority(Plan.objects.filter(owner=request.user, deleted=False)), **f)
    return ok(ser_plan(p), 201)


@require_login
@require_http_methods(["GET", "PUT", "DELETE"])
@api
@transaction.atomic
def plan_detail(request, pk):
    p = owned_or_404(Plan, request.user, pk, deleted=False)   # <- 주인 확인
    if request.method == "GET":
        return ok(ser_plan(p))
    if request.method == "DELETE":
        p.deleted = True
        p.save()
        return ok()
    f = plan_fields(body(request))
    PlanVersion.objects.create(plan=p, owner=request.user, snapshot=plan_snapshot(p))  # 고치기 전 모습 보존
    for k, v in f.items():
        setattr(p, k, v)
    p.save()
    return ok(ser_plan(p))


@require_login
@require_http_methods(["POST"])
@api
@transaction.atomic
def plan_note(request, pk):
    p = owned_or_404(Plan, request.user, pk, deleted=False)
    text = str(body(request).get("text", "")).strip()
    if not text:
        raise BadRequest("내용을 입력해 주세요.")
    PlanVersion.objects.create(plan=p, owner=request.user, snapshot=plan_snapshot(p))
    ImprovementNote.objects.create(plan=p, owner=request.user, text=text)
    return ok(ser_plan(p), 201)


def reorder(model, request):
    ids = body(request).get("ids")
    if not isinstance(ids, list) or not ids:
        raise BadRequest("정렬할 항목이 없습니다.")
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        raise NotFound()
    items = {o.pk: o for o in model.objects.filter(owner=request.user, pk__in=ids, deleted=False)}
    if len(items) != len(set(ids)):
        raise NotFound()  # 내 것이 아닌 번호가 하나라도 섞여 있으면 통째로 거절 (아무것도 바꾸지 않음)
    slots = sorted(o.priority for o in items.values())  # 화면에 보인 항목들이 가진 순번 칸을 새 순서로 다시 나눠 준다
    with transaction.atomic():
        for slot, pk in zip(slots, ids):
            items[pk].priority = slot
            items[pk].save(update_fields=["priority"])
    return ok()


@require_login
@require_http_methods(["POST"])
@api
def plan_reorder(request):
    return reorder(Plan, request)


# ------------------------------------------------------------------ 할 일
def todo_fields(request, data):
    title = str(data.get("title", "")).strip()
    if not title:
        raise BadRequest("제목을 입력해 주세요.")
    due = parse_date(data.get("dueDate"), "마감일")
    start = parse_date(data.get("periodStart"), "시작일", required=False)
    if start and due < start:
        raise BadRequest("마감일이 시작일보다 빠를 수 없습니다.")
    plan = None
    if data.get("planId"):
        plan = owned_or_404(Plan, request.user, data["planId"], deleted=False)  # 남의 계획에 붙일 수 없다
    return dict(
        title=title[:200], tags=clean_tags(data.get("tags")), period_start=start, due_date=due,
        success_criteria=str(data.get("successCriteria", "")).strip(),
        estimated_hours=parse_hours(data.get("estimatedTime")), plan=plan,
    )


@require_login
@require_http_methods(["POST"])
@api
def todo_create(request):
    f = todo_fields(request, body(request))
    t = Todo.objects.create(owner=request.user, priority=next_priority(Todo.objects.filter(owner=request.user, deleted=False)), **f)
    return ok(ser_todo(t), 201)


@require_login
@require_http_methods(["GET", "PUT", "DELETE"])
@api
@transaction.atomic
def todo_detail(request, pk):
    t = owned_or_404(Todo, request.user, pk, deleted=False)   # <- 주인 확인
    if request.method == "GET":
        return ok(ser_todo(t))
    if request.method == "DELETE":
        t.deleted = True
        t.save()
        return ok()
    f = todo_fields(request, body(request))
    TodoVersion.objects.create(todo=t, owner=request.user, snapshot=todo_snapshot(t))
    for k, v in f.items():
        setattr(t, k, v)
    t.save()
    return ok(ser_todo(t))


@require_login
@require_http_methods(["POST"])
@api
def todo_complete(request, pk):
    # 같은 요청이 몇 번, 동시에 와도 결과는 '완료 상태 한 건'.
    # "아직 진행 중인 것만 완료로 바꾼다"를 UPDATE 한 문장으로 처리하므로 두 번째 요청부터는 아무것도 바꾸지 않는다.
    t = owned_or_404(Todo, request.user, pk, deleted=False)   # <- 주인 확인
    now = timezone.now()
    Todo.objects.filter(pk=t.pk, owner=request.user, status="in_progress").update(
        status="completed", completed_at=now, updated_at=now)
    t.refresh_from_db()
    return ok(ser_todo(t))


@require_login
@require_http_methods(["POST"])
@api
def todo_reopen(request, pk):
    t = owned_or_404(Todo, request.user, pk, deleted=False)
    Todo.objects.filter(pk=t.pk, owner=request.user, status="completed").update(
        status="in_progress", completed_at=None, updated_at=timezone.now())
    t.refresh_from_db()
    return ok(ser_todo(t))


@require_login
@require_http_methods(["POST"])
@api
def todo_reorder(request):
    return reorder(Todo, request)


@require_login
@require_http_methods(["POST"])
@api
def record_create(request, pk):
    todo = owned_or_404(Todo, request.user, pk, deleted=False)
    data = body(request)
    start, end = parse_dt(data.get("start"), "시작 시각"), parse_dt(data.get("end"), "끝난 시각")
    if end < start:
        raise BadRequest("끝난 시각이 시작 시각보다 빠를 수 없습니다.")
    request_id = str(data.get("requestId") or uuid.uuid4())[:64]
    try:
        with transaction.atomic():
            rec = ExecRecord.objects.create(
                owner=request.user, todo=todo, started_at=start, ended_at=end,
                actual_minutes=round((end - start).total_seconds() / 60),
                blocked_reason=str(data.get("blockedReason", "")).strip(), request_id=request_id,
            )
        return ok(ser_record(rec), 201)
    except IntegrityError:
        # 같은 requestId 로 다시 온 요청: 새로 만들지 않고 처음 만든 한 건을 돌려준다
        rec = ExecRecord.objects.get(owner=request.user, request_id=request_id)
        return ok(ser_record(rec), 200)


@require_login
@require_http_methods(["GET", "DELETE"])
@api
def record_detail(request, pk):
    r = owned_or_404(ExecRecord, request.user, pk)   # <- 주인 확인
    if request.method == "GET":
        return ok(ser_record(r))
    r.delete()
    return ok()


# ------------------------------------------------------------------ 5일 실험
RULES = {
    "calc": "일별 값을 그대로 더해 합계를 내고, 합계를 기록된 일수로 나눠 평균을 낸다. 반올림은 마지막에 한 번만 한다.",
    "missing": "값이 비어 있으면 저장하지 않는다(0으로 채우지 않음). 기록하지 않은 날짜는 '일차'로 세지 않으므로 평균의 분모에도 들어가지 않는다.",
    "duplicate": "같은 날짜(서울 시간 기준)에는 한 건만 둔다. 같은 날 다시 저장하면 새 기록이 생기지 않고 그날 기록의 값이 덮어써진다.",
    "outlier": "전체 값의 중앙값보다 3배 넘게 크거나 1/3보다 작은 값은 '튀는 값'으로 표시만 한다. 계산에서 빼지 않고 그대로 포함한다.",
    "rounding": "합계·평균은 소수 둘째 자리에서 반올림해 소수 첫째 자리까지 보여 준다(0.05는 올림, ROUND_HALF_UP).",
    "week_start": "주의 시작 요일은 월요일이다.",
}
MAX_DAYS = 5


def r1(x):
    return Decimal(x).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def week_start(d):
    return d - timedelta(days=d.weekday())


def stats(days):
    vals = [d.value for d in days]
    if not vals:
        return {"count": 0, "sum": None, "average": None, "values": []}
    total = sum(vals, Decimal("0"))
    return {"count": len(vals), "sum": str(r1(total)), "average": str(r1(total / len(vals))),
            "values": [str(v) for v in vals]}


def experiment_payload(user):
    exp = Experiment.objects.filter(owner=user).first()
    days = list(ExperimentDay.objects.filter(owner=user).order_by("date"))
    change = RuleChange.objects.filter(owner=user).select_related("day1", "day2").first()
    med = median([d.value for d in days]) if days else None
    out_days = []
    for i, d in enumerate(days, 1):
        flag = bool(med and med > 0 and (d.value > med * 3 or d.value < med / 3))
        out_days.append({"id": str(d.id), "dayNo": i, "date": d.date.isoformat(), "value": str(d.value),
                         "note": d.note, "weekStart": week_start(d.date).isoformat(), "outlier": flag,
                         "recordedAt": iso(d.created_at)})
    payload = {
        "rules": RULES, "maxDays": MAX_DAYS, "today": timezone.localdate().isoformat(),
        "settings": None, "days": out_days, "ruleChange": None, "comparison": None,
        "total": stats(days),
    }
    if exp:
        payload["settings"] = {"question": exp.question, "metricName": exp.metric_name, "unit": exp.unit,
                               "planRule": exp.plan_rule, "fixedAt": iso(exp.fixed_at)}
    if change:
        payload["ruleChange"] = {
            "changedAt": iso(change.changed_at), "reason": change.reason, "beforeRule": change.before_rule,
            "afterRule": change.after_rule, "day1": {"id": str(change.day1_id), "date": change.day1.date.isoformat()},
            "day2": {"id": str(change.day2_id), "date": change.day2.date.isoformat()},
        }
        payload["comparison"] = {
            "metric": exp.metric_name, "unit": exp.unit, "calc": RULES["calc"],
            "before": stats([d for d in days if d.date <= change.day2.date]),
            "after": stats([d for d in days if d.date > change.day2.date]),
        }
    return payload


@require_login
def experiment_view(request):
    return ok(experiment_payload(request.user))


@require_login
@require_http_methods(["POST"])
@api
@transaction.atomic
def experiment_fix(request):
    if Experiment.objects.filter(owner=request.user).exists():
        raise BadRequest("이미 고정되었습니다. 1일차에 한 번만 정할 수 있습니다.")
    if ExperimentDay.objects.filter(owner=request.user).exists():
        raise BadRequest("기록이 시작된 뒤에는 정할 수 없습니다.")
    d = body(request)
    vals = {k: str(d.get(k, "")).strip() for k in ("question", "metricName", "unit", "planRule")}
    if not all(vals.values()):
        raise BadRequest("질문·지표·단위·계획 규칙을 모두 적어 주세요.")
    Experiment.objects.create(owner=request.user, question=vals["question"][:300], metric_name=vals["metricName"][:100],
                              unit=vals["unit"][:30], plan_rule=vals["planRule"])
    return ok(experiment_payload(request.user), 201)


@require_login
@require_http_methods(["POST"])
@api
@transaction.atomic
def experiment_day(request):
    if not Experiment.objects.filter(owner=request.user).exists():
        raise BadRequest("먼저 질문·지표·단위·계획 규칙을 고정해 주세요.")
    d = body(request)
    raw = d.get("value")
    if raw in (None, ""):
        raise BadRequest("값이 비어 있습니다. 값 없이는 저장하지 않습니다.")
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or abs(value) > Decimal("9999999999"):
            raise ValueError
    except Exception:
        raise BadRequest("값은 숫자여야 합니다.")
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    today = timezone.localdate()  # 서울 기준 오늘. 날짜는 사용자가 정하지 못한다.
    existing = ExperimentDay.objects.filter(owner=request.user, date=today).first()
    n = ExperimentDay.objects.filter(owner=request.user).count()
    if existing:
        existing.value, existing.note = value, str(d.get("note", ""))[:300]
        existing.save()
        return ok(experiment_payload(request.user))
    if n >= MAX_DAYS:
        raise BadRequest("5일 기록이 모두 채워졌습니다. 더 만들 수 없습니다.")
    if n == 2 and not RuleChange.objects.filter(owner=request.user).exists():
        raise BadRequest("3일차 기록 전에 계획 규칙 변경을 먼저 기록해 주세요.")
    ExperimentDay.objects.create(owner=request.user, date=today, value=value, note=str(d.get("note", ""))[:300])
    return ok(experiment_payload(request.user), 201)


@require_login
@require_http_methods(["POST"])
@api
@transaction.atomic
def experiment_rule_change(request):
    exp = Experiment.objects.filter(owner=request.user).first()
    if not exp:
        raise BadRequest("먼저 실험 설정을 고정해 주세요.")
    if RuleChange.objects.filter(owner=request.user).exists():
        raise BadRequest("계획 규칙은 한 번만 바꿀 수 있습니다.")
    days = list(ExperimentDay.objects.filter(owner=request.user).order_by("date"))
    if len(days) != 2:
        raise BadRequest("계획 규칙 변경은 2일차 기록 뒤, 3일차 기록 앞에서만 할 수 있습니다. "
                         f"지금 기록된 날은 {len(days)}일입니다.")
    d = body(request)
    reason, new_rule = str(d.get("reason", "")).strip(), str(d.get("newRule", "")).strip()
    if not reason or not new_rule:
        raise BadRequest("바꾼 이유와 새 계획 규칙을 모두 적어 주세요.")
    RuleChange.objects.create(owner=request.user, reason=reason, before_rule=exp.plan_rule, after_rule=new_rule,
                              day1=days[0], day2=days[1])
    return ok(experiment_payload(request.user), 201)
