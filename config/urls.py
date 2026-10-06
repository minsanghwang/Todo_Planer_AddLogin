from django.urls import path

from diary import api, views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("app/", views.app_view, name="app"),

    path("api/me/", api.me_view),
    path("api/data/", api.data_view),
    path("api/export/", api.export_view),
    path("api/import/", api.import_view),
    path("api/account/password/", api.password_view),
    path("api/account/delete/", api.account_delete_view),

    path("api/plans/", api.plan_create),
    path("api/plans/reorder/", api.plan_reorder),
    path("api/plans/<int:pk>/", api.plan_detail),
    path("api/plans/<int:pk>/notes/", api.plan_note),

    path("api/todos/", api.todo_create),
    path("api/todos/reorder/", api.todo_reorder),
    path("api/todos/<int:pk>/", api.todo_detail),
    path("api/todos/<int:pk>/complete/", api.todo_complete),
    path("api/todos/<int:pk>/reopen/", api.todo_reopen),
    path("api/todos/<int:pk>/records/", api.record_create),
    path("api/records/<int:pk>/", api.record_detail),

    path("api/experiment/", api.experiment_view),
    path("api/experiment/fix/", api.experiment_fix),
    path("api/experiment/days/", api.experiment_day),
    path("api/experiment/rule-change/", api.experiment_rule_change),
]
