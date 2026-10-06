"""
플랜두씨 다이어리 2 설정.

비밀값은 코드에 두지 않고 환경변수로만 받는다.
  DJANGO_SECRET_KEY   세션 서명 등에 쓰는 비밀키 (배포 환경에서만 등록)
  DATABASE_URL        PostgreSQL 주소 (없으면 로컬 SQLite)
  DJANGO_DEBUG        "1"이면 개발 모드
  DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS  쉼표로 구분
Vercel에서는 VERCEL_URL 등 시스템 환경변수에서 허용 호스트와 CSRF 출처를 자동으로 가져온다.
"""
import os
import secrets
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG") == "1"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        # 개발 중에만: 실행할 때마다 새로 만드는 임시 키. 파일에도 Git에도 남지 않는다.
        SECRET_KEY = secrets.token_urlsafe(50)
    else:
        raise RuntimeError("DJANGO_SECRET_KEY 환경변수가 없습니다. 배포 환경에 등록하세요.")

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

# 배포 환경이 알려 주는 우리 서비스의 정확한 호스트만 추가한다.
# (*.vercel.app 같은 와일드카드는 쓰지 않는다: 남의 vercel.app 사이트가 우리 로그인 요청을 보낼 수 있게 되므로)
_platform_hosts = [
    os.environ.get("RENDER_EXTERNAL_HOSTNAME"),          # Render
    os.environ.get("VERCEL_URL"),                         # Vercel: 이번 배포의 고유 주소
    os.environ.get("VERCEL_BRANCH_URL"),                  # Vercel: 브랜치 주소
    os.environ.get("VERCEL_PROJECT_PRODUCTION_URL"),      # Vercel: 프로덕션 주소
]
for _h in _platform_hosts:
    if _h and _h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_h)
        CSRF_TRUSTED_ORIGINS.append(f"https://{_h}")

IS_VERCEL = bool(os.environ.get("VERCEL"))

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "diary",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "diary.middleware.AccessLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        # 서버리스(Vercel)는 요청마다 새 실행 환경이 생길 수 있어 연결을 붙들어 두지 않는다.
        conn_max_age=0 if IS_VERCEL else 600,
    )
}
if IS_VERCEL and DATABASES["default"]["ENGINE"].endswith("postgresql"):
    # 연결 풀러(트랜잭션 모드)를 거쳐도 동작하도록
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# ---- 비밀번호: 되돌릴 수 없게 보관 (PBKDF2-SHA256 + 계정마다 다른 소금값) ----
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---- 세션: 서버(DB)에 저장하는 세션. 로그아웃하면 서버에서 지운다. ----
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 24  # 24시간 뒤 만료
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 3600

LOGIN_URL = "/login/"

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- 로그: 요청 본문(비밀번호)·쿠키·헤더는 절대 남기지 않는다 (diary/middleware.py 참고) ----
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "diary.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
