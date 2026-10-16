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
    """계획을 고치기 직전의 모습. 고칠 때마다 한 건씩 쌓이고, 고친 시각과 고친 이유가 함께 남는다."""
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="versions")
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    snapshot = models.JSONField()
    edited_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, default="")  # 고친 이유 (6번에서 가져온 옛 기록은 비어 있음)


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
