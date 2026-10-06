from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Plan(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="plans")
    title = models.CharField(max_length=200)
    topic_tags = models.JSONField(default=list)
    period_start = models.DateField()
    period_end = models.DateField()
    priority = models.IntegerField(default=1)
    success_criteria = models.TextField(blank=True, default="")
    estimated_hours = models.FloatField(default=0)
    deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PlanVersion(models.Model):
    """계획을 고치기 직전의 모습. 고칠 때마다 한 건씩 쌓인다."""
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="versions")
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    snapshot = models.JSONField()
    edited_at = models.DateTimeField(auto_now_add=True)


class ImprovementNote(models.Model):
    """돌아보기에서 정한 고칠 점. 지정한 계획으로 넘어간다."""
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="notes")
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Todo(models.Model):
    STATUS = [("in_progress", "진행 중"), ("completed", "완료")]
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="todos")
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL, related_name="todos")
    title = models.CharField(max_length=200)
    tags = models.JSONField(default=list)
    period_start = models.DateField(null=True, blank=True)
    due_date = models.DateField()  # 마감일 = 기간의 끝
    success_criteria = models.TextField(blank=True, default="")
    estimated_hours = models.FloatField(default=0)
    priority = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS, default="in_progress")
    completed_at = models.DateTimeField(null=True, blank=True)
    deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TodoVersion(models.Model):
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="versions")
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    snapshot = models.JSONField()
    edited_at = models.DateTimeField(auto_now_add=True)


class ExecRecord(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exec_records")
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="records")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    actual_minutes = models.IntegerField()
    blocked_reason = models.TextField(blank=True, default="")
    # 같은 요청이 두 번 도착해도 한 건만 남기려는 열쇠 (더블클릭·재전송 방어)
    request_id = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "request_id"],
                condition=models.Q(request_id__isnull=False),
                name="uniq_exec_request_per_owner",
            )
        ]


class Experiment(models.Model):
    """1일차에 한 번 고정하는 5일 실험 설정. 한 계정에 한 건."""
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="experiment")
    question = models.CharField(max_length=300)
    metric_name = models.CharField(max_length=100)
    unit = models.CharField(max_length=30)
    plan_rule = models.TextField()
    fixed_at = models.DateTimeField(auto_now_add=True)


class ExperimentDay(models.Model):
    """하루 한 건. 날짜는 서버가 서울 시간 기준 '오늘'로 정한다(과거 날짜로 채울 수 없음)."""
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="experiment_days")
    date = models.DateField()
    value = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "date"], name="uniq_experiment_day_per_owner")]
        ordering = ["date"]


class RuleChange(models.Model):
    """계획 규칙 변경 기록. 2일차 기록 뒤, 3일차 기록 앞에서만 만들 수 있다."""
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="rule_change")
    changed_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    before_rule = models.TextField()
    after_rule = models.TextField()
    day1 = models.ForeignKey(ExperimentDay, on_delete=models.PROTECT, related_name="+")
    day2 = models.ForeignKey(ExperimentDay, on_delete=models.PROTECT, related_name="+")
