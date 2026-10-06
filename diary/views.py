"""화면(HTML) 쪽 뷰: 로그인·가입·로그아웃과 앱 화면.

가입 흐름   signup_view  -> User.objects.create_user (비밀번호는 PBKDF2로 해시되어 저장)
로그인 흐름 login_view   -> authenticate -> login (세션 키 새로 발급, 서버 DB에 세션 저장)
로그아웃    logout_view  -> logout (서버의 세션 행 삭제)
자료 조회   app_view(화면) + api.py(JSON). 둘 다 로그인 안 했으면 거절.
"""
import re

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

# 아이디가 없을 때와 비밀번호가 틀렸을 때 똑같은 문구를 쓴다.
LOGIN_FAIL = "아이디 또는 비밀번호가 올바르지 않습니다."
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,30}$")


@never_cache
def home_view(request):
    """첫 화면 = 로그인 화면. 이미 로그인한 사람은 앱으로 보낸다."""
    if request.user.is_authenticated:
        return redirect("app")
    return render(request, "diary/login.html")


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("app")
    if request.method == "POST":
        username = request.POST.get("username", "").strip().lower()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("app")
        return render(request, "diary/login.html", {"error": LOGIN_FAIL, "username": username}, status=401)
    return render(request, "diary/login.html")


@never_cache
@require_http_methods(["GET", "POST"])
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("app")
    if request.method == "GET":
        return render(request, "diary/signup.html")
    username = request.POST.get("username", "").strip().lower()  # 대소문자만 다른 아이디로 이중 가입 방지
    pw1, pw2 = request.POST.get("password", ""), request.POST.get("password2", "")
    errors = []
    if not USERNAME_RE.match(username):
        errors.append("아이디는 영문 소문자·숫자·점·밑줄·하이픈 3~30자로 입력해 주세요.")
    if pw1 != pw2:
        errors.append("비밀번호 확인이 일치하지 않습니다.")
    if not errors:
        try:
            validate_password(pw1, User(username=username))
        except ValidationError as e:
            errors.extend(e.messages)
    if not errors and User.objects.filter(username=username).exists():
        errors.append("이미 사용 중인 아이디입니다.")
    if not errors:
        try:
            user = User.objects.create_user(username=username, password=pw1)
        except IntegrityError:  # 동시에 같은 아이디로 가입한 경우도 DB 유니크 제약이 막는다
            errors.append("이미 사용 중인 아이디입니다.")
        else:
            login(request, user)
            return redirect("app")
    return render(request, "diary/signup.html", {"errors": errors, "username": username}, status=400)


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


@never_cache
def app_view(request):
    if not request.user.is_authenticated:
        return redirect(f"/login/?next=/app/")
    return render(request, "diary/app.html", {"username": request.user.get_username()})
