# 플랜두씨 다이어리 2

계획·할 일·실행 기록을 **로그인한 나만** 보는 다이어리. Django 6.1 + PostgreSQL(로컬은 SQLite) + 서버 세션 + PBKDF2.
인증을 어떻게 붙였고 어떻게 확인했는지는 [`docs/submission.md`](docs/submission.md), 실제 요청·응답 기록은 [`docs/evidence.md`](docs/evidence.md).

## 로컬에서 실행

```bash
pip install -r requirements.txt
export DJANGO_DEBUG=1            # 개발 모드 (비밀키는 실행할 때마다 임시로 만들어지며 어디에도 저장되지 않음)
python3 manage.py migrate
python3 manage.py runserver      # http://127.0.0.1:8000/  → 첫 화면이 로그인 화면
```

## 확인하기

```bash
DJANGO_DEBUG=1 python3 manage.py test     # 5일 실험 규칙·6번 JSON 가져오기 테스트 (날짜를 바꿔 가며 5일을 흉내 냄)
python3 scripts/verify_auth.py            # 임시 DB로 서버를 띄워 실제 HTTP 요청으로 인증·소유자 확인 검사 → docs/evidence.md 갱신
python3 scripts/verify_ui.py              # 실제 브라우저(Chromium, playwright 필요)로 가입~삭제까지 클릭하며 화면 시험
```

## 환경변수 (비밀값은 코드·Git에 없고 배포 환경에만 둔다)

| 이름 | 설명 |
|---|---|
| `DJANGO_SECRET_KEY` | 세션 서명 등에 쓰는 비밀키. 배포 환경에서 필수 (없으면 서버가 뜨지 않음) |
| `DATABASE_URL` | PostgreSQL 주소. 없으면 로컬 SQLite |
| `DJANGO_DEBUG` | `1`이면 개발 모드. 배포에서는 설정하지 않음 |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | 쉼표로 구분 (Render에서는 호스트 이름이 자동으로 들어감) |

## 배포 (Render)

1. 이 폴더를 GitHub 공개 저장소로 올린다.
2. Render에서 *New → Blueprint* 로 저장소를 연결하면 `render.yaml` 대로 웹 서비스와 PostgreSQL이 만들어진다.
3. `DJANGO_SECRET_KEY`는 Render가 자동 생성한다(저장소에 올릴 필요 없음).
4. 배포가 끝나면 시크릿 창에서 주소를 열어 로그인 화면이 뜨는지 확인한다.
5. Python 버전 오류가 나면 Render 서비스 환경변수 `PYTHON_VERSION`을 3.12 이상으로 지정한다(Django 6.1 요구).

## 6번(T06) 이력 잇기

T07 소스 이력에 제출했던 T06 commit이 조상으로 들어 있어야 한다. 이 폴더는 새 저장소에서 시작했으므로, T06 저장소의 주소와 commit을 정해 아래처럼 이어 붙인다.

```bash
git remote add t06 <T06 저장소 주소>
git fetch t06
git merge --allow-unrelated-histories <T06 commit>   # 충돌이 나면 이쪽(T07) 파일을 우선해 해결
git merge-base --is-ancestor <T06 commit> HEAD && echo "조상으로 포함됨"
```

## 6번 자료 옮기기

6번 다이어리에서 내보낸 JSON을 로그인 뒤 *내 계정 → 6번 다이어리 자료 가져오기*에서 올리면 내 계정 자료로 들어온다.
