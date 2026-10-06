#!/usr/bin/env python3
"""인증·소유자 확인 검증 스크립트.

임시 DB와 일회용 비밀키로 서버를 직접 띄우고, 진짜 HTTP 요청을 보내 응답을 그대로 기록한다.
기록(docs/evidence.md)에는 쿠키·CSRF 토큰·비밀번호·비밀키 원문을 쓰지 않고 가려서 적는다.

사용법:  python3 scripts/verify_auth.py
"""
import http.client
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("VERIFY_PORT", "8765"))
HOST = "127.0.0.1"

WORK = Path(tempfile.mkdtemp(prefix="diary-verify-"))
DB_PATH = WORK / "verify.sqlite3"
LOG_PATH = WORK / "server.log"
RUN_KEY = "k-" + secrets.token_urlsafe(40)  # 이 실행에서만 존재하는 일회용 값(고정값 아님)
PW_SAME = "Pw-" + secrets.token_urlsafe(14)     # 두 계정이 같이 쓰는 비밀번호 (출력하지 않는다)
PW_OTHER = "Pw-" + secrets.token_urlsafe(14)
PW_NEW = "Pw-" + secrets.token_urlsafe(14)
SECRETS_TO_HIDE = [RUN_KEY, PW_SAME, PW_OTHER, PW_NEW]

OUT = []
CHECKS = []
REQUEST_PATHS = []      # 실제로 보낸 모든 요청 주소
ISSUED_COOKIE_VALUES = set()  # 서버가 발급한 쿠키 값


# ------------------------------------------------------------------ 가리기
def mask(text):
    if text is None:
        return ""
    t = str(text)
    t = re.sub(r"(sessionid|csrftoken)=([A-Za-z0-9]{4})[A-Za-z0-9]+", r"\1=\2…생략", t)
    t = re.sub(r"(X-CSRFToken: )([A-Za-z0-9]{4})[A-Za-z0-9]+", r"\1\2…생략", t)
    t = re.sub(r"(csrfmiddlewaretoken=)[A-Za-z0-9]+", r"\1…생략", t)
    t = re.sub(r'((?:password2?|oldPassword|newPassword)=)[^&\s"]+', r"\1***", t)
    t = re.sub(r'("(?:password|oldPassword|newPassword)": )"[^"]*"', r'\1"***"', t)
    for s in SECRETS_TO_HIDE:
        t = t.replace(s, "***")
    return t


def say(line=""):
    OUT.append(line)


def check(name, passed, detail=""):
    CHECKS.append((name, bool(passed), detail))
    say(f"- {'✅' if passed else '❌'} {name}" + (f" — {detail}" if detail else ""))
    return passed


# ------------------------------------------------------------------ HTTP 클라이언트
class Resp:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        try:
            return json.loads(self.body)
        except ValueError:
            return None


class Client:
    def __init__(self, name):
        self.name = name
        self.cookies = {}

    def clone_session(self, name):
        c = Client(name)
        c.cookies = dict(self.cookies)
        return c

    def request(self, method, path, json_body=None, form=None, headers=None, log=None):
        h = {"Host": f"{HOST}:{PORT}"}
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if method != "GET" and "csrftoken" in self.cookies:
            h["X-CSRFToken"] = self.cookies["csrftoken"]
        body = None
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode()
            h["Content-Type"] = "application/json"
        elif form is not None:
            body = urllib.parse.urlencode(form).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        h.update(headers or {})
        REQUEST_PATHS.append(path)
        conn = http.client.HTTPConnection(HOST, PORT, timeout=20)
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        raw = r.read().decode("utf-8", "replace")
        hdrs = r.getheaders()
        conn.close()
        for k, v in hdrs:
            if k.lower() == "set-cookie":
                first = v.split(";")[0]
                name, _, val = first.partition("=")
                if val == "" or "max-age=0" in v.lower():
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = val
                    if len(val) >= 20:
                        ISSUED_COOKIE_VALUES.add(val)
        resp = Resp(r.status, hdrs, raw)
        if log:
            self.log(method, path, json_body, form, h, resp, log)
        return resp

    def log(self, method, path, json_body, form, sent_headers, resp, label):
        lines = [f"{method} {path}"]
        if "Cookie" in sent_headers:
            lines.append(f"Cookie: {sent_headers['Cookie']}")
        for k in ("X-User-Id", "X-Owner", "X-Account"):
            if k in sent_headers:
                lines.append(f"{k}: {sent_headers[k]}")
        if json_body is not None:
            lines.append("Body: " + json.dumps(json_body, ensure_ascii=False))
        if form is not None:
            lines.append("Body: " + urllib.parse.urlencode(form))
        lines.append(f"→ {resp.status}")
        for k, v in resp.headers:
            if k.lower() in ("location", "set-cookie"):
                lines.append(f"   {k}: {v}")
        snippet = resp.body.strip().replace("\n", " ")
        if resp.headers and any(k.lower() == "content-type" and "json" in v for k, v in resp.headers):
            lines.append(f"   {snippet[:400]}")
        elif snippet:
            lines.append(f"   (HTML {len(resp.body)}자) " + re.sub(r"<[^>]+>", " ", snippet)[:140].strip())
        say(f"**{label}**")
        say("```")
        say(mask("\n".join(lines)))
        say("```")


def signup(c, username, password):
    c.request("GET", "/signup/")
    return c.request("POST", "/signup/", form={"username": username, "password": password, "password2": password})


def login(c, username, password, log=None):
    c.request("GET", "/login/")
    return c.request("POST", "/login/", form={"username": username, "password": password}, log=log)


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def short(s, n=6):
    return s[:n] + "…생략"


# ------------------------------------------------------------------ 서버
def start_server():
    env = dict(os.environ, DJANGO_DEBUG="1", DJANGO_SECRET_KEY=RUN_KEY, DATABASE_URL=f"sqlite:///{DB_PATH}")
    subprocess.run([sys.executable, "manage.py", "migrate", "-v", "0"], cwd=ROOT, env=env, check=True)
    log = open(LOG_PATH, "w")
    proc = subprocess.Popen([sys.executable, "manage.py", "runserver", f"{HOST}:{PORT}", "--noreload"],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            http.client.HTTPConnection(HOST, PORT, timeout=1).request("GET", "/")
            return proc
        except OSError:
            time.sleep(0.3)
    proc.kill()
    raise RuntimeError("서버가 뜨지 않았습니다.")


# ------------------------------------------------------------------ 본 검증
def main():
    proc = start_server()
    try:
        run()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()
    server_log = LOG_PATH.read_text(errors="replace")
    say("\n## 서버 로그·저장소 전체 검사")
    say("```")
    say("서버 로그 마지막 줄들(원문 그대로, 본문·쿠키는 기록되지 않음):")
    say("\n".join(server_log.strip().splitlines()[-8:]))
    say("```")
    for s, label in [(PW_SAME, "비밀번호(공통)"), (PW_OTHER, "비밀번호(다른 계정)"), (PW_NEW, "새 비밀번호")]:
        check(f"서버 로그에 {label} 원문이 없다", s not in server_log)
    check("서버 로그에 비밀키 원문이 없다", RUN_KEY not in server_log)
    check("서버 로그에 세션·CSRF 쿠키 값이 없다", "sessionid=" not in server_log and "csrftoken=" not in server_log)

    # 저장소(작업 폴더·Git 기록)에 비밀키/비밀번호 원문이 있는지
    def tree_has(value):
        for p in ROOT.rglob("*"):
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts and p.stat().st_size < 3_000_000 \
                    and p.suffix not in (".sqlite3",):
                try:
                    if value in p.read_text(errors="ignore"):
                        return True
                except Exception:
                    pass
        return False

    check("작업 폴더 어디에도 이번 비밀키 원문이 없다", not tree_has(RUN_KEY))
    check("작업 폴더 어디에도 테스트 비밀번호 원문이 없다", not any(tree_has(s) for s in (PW_SAME, PW_OTHER, PW_NEW)))
    hard = subprocess.run(["grep", "-rnE", r"SECRET_KEY\s*=\s*['\"][^'\"]+['\"]", "--include=*.py", "--include=*.yaml",
                           "--include=*.yml", "--include=*.env", "--include=*.md", "--exclude=evidence.md", "."], cwd=ROOT, capture_output=True, text=True)
    check("소스에 비밀키를 문자열로 박아 둔 곳이 없다", hard.stdout.strip() == "", hard.stdout.strip()[:200])
    if (ROOT / ".git").exists() and subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True).returncode == 0:
        hist = subprocess.run("git log --all -p", shell=True, cwd=ROOT, capture_output=True, text=True, errors="ignore").stdout
        check("Git 기록 전체에 이번 비밀키·테스트 비밀번호 원문이 없다",
              not any(s in hist for s in SECRETS_TO_HIDE))
        check("Git 기록 전체에 비밀키를 문자열로 박은 줄이 없다",
              re.search(r"SECRET_KEY\s*=\s*['\"][^'\"]+['\"]", hist) is None)
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        check("DB 파일(.sqlite3)과 .env가 Git에 올라가 있지 않다",
              not any(f.endswith(".sqlite3") or f.startswith(".env") for f in tracked))
    else:
        say("- ⚠️ Git 기록 검사는 커밋이 생긴 뒤 다시 실행하면 함께 확인됩니다.")

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    say(f"\n## 요약\n통과 {passed} / {len(CHECKS)}")
    failed = [n for n, ok, _ in CHECKS if not ok]
    if failed:
        say("실패한 항목:")
        for n in failed:
            say(f"- {n}")
    (ROOT / "docs").mkdir(exist_ok=True)
    text = "\n".join(OUT)
    assert not any(s in text for s in SECRETS_TO_HIDE), "기록에 비밀값이 섞였습니다"
    (ROOT / "docs" / "evidence.md").write_text(
        "# 확인 기록 (자동 생성)\n\n"
        "`python3 scripts/verify_auth.py` 가 임시 DB와 일회용 비밀키로 서버를 띄워 실제로 보낸 요청과 받은 응답입니다. "
        "쿠키·CSRF 토큰은 앞 4글자만 남기고 `…생략`으로 가렸고, 비밀번호와 비밀키는 `***`로 가렸습니다. "
        "(로컬 개발 서버는 HTTP라서 쿠키의 Secure 표시는 배포 환경에서만 붙습니다.)\n\n" + text + "\n")
    shutil.rmtree(WORK, ignore_errors=True)
    print("\n".join(f"{'PASS' if ok else 'FAIL'}  {n}" for n, ok, _ in CHECKS))
    print(f"\n통과 {passed} / {len(CHECKS)}  → docs/evidence.md")
    sys.exit(0 if not failed else 1)


def run():
    A, B = Client("A"), Client("B")
    ua, ub = "tester.a", "tester.b"

    # ============ 카드 1: 가입·로그인·로그아웃, 로그인 없이 자료 화면 ============
    say("## 카드 1 — 가입·로그인·로그아웃")
    anon = Client("anon")
    r = anon.request("GET", "/", log="로그인 없이 첫 화면(/) 열기")
    check("첫 화면은 로그인 화면이다(로그인 없이 열림)", r.status == 200 and "로그인" in r.body and 'name="password"' in r.body)
    r = anon.request("GET", "/app/", log="로그인 없이 자료 화면(/app/) 열기")
    check("로그인 없이 /app/ 을 열면 로그인 화면으로 보내진다", r.status == 302 and "/login/" in dict(r.headers).get("Location", ""))
    r = anon.request("GET", "/api/data/", log="로그인 없이 자료 API 직접 요청")
    check("로그인 없이 자료 API를 부르면 401", r.status == 401 and "계획" not in r.body)

    r = signup(A, ua, PW_SAME)
    check("가입 화면에서 새 계정을 만들 수 있다 (A)", r.status == 302 and "sessionid" in A.cookies, f"가입 응답 {r.status}")
    signup(B, ub, PW_SAME)
    say("")
    d = Client("dup")
    d.request("GET", "/signup/")
    r = d.request("POST", "/signup/", form={"username": ua, "password": PW_OTHER, "password2": PW_OTHER}, log="같은 아이디로 다시 가입")
    check("같은 아이디로 두 번 가입되지 않는다", r.status == 400 and "이미 사용 중" in r.body)
    d.request("GET", "/signup/")
    r = d.request("POST", "/signup/", form={"username": ua.upper(), "password": PW_OTHER, "password2": PW_OTHER}, log="대소문자만 바꿔 가입")
    n = db().execute("select count(*) from auth_user where lower(username)=?", (ua,)).fetchone()[0]
    check("대소문자만 다른 아이디로도 이중 가입되지 않는다", n == 1, f"해당 아이디 행 수 {n}")

    f1, f2 = Client("f1"), Client("f2")
    r1 = login(f1, ua, "x" + PW_OTHER, log="아이디는 맞고 비밀번호가 틀림")
    r2 = login(f2, "nobody.here", PW_OTHER, log="없는 아이디")
    m1 = re.search(r'class="error"[^>]*>(.*?)</div>', r1.body, re.S)
    m2 = re.search(r'class="error"[^>]*>(.*?)</div>', r2.body, re.S)
    check("비밀번호만 틀렸을 때와 아이디가 없을 때 안내 문구·상태코드가 같다",
          m1 and m2 and m1.group(1).strip() == m2.group(1).strip() and r1.status == r2.status == 401,
          f"둘 다 {r1.status}: {m1.group(1).strip() if m1 else None}")

    A2 = Client("A-login")
    r = login(A2, ua, PW_SAME, log="올바른 아이디·비밀번호로 로그인")
    check("만든 계정으로 로그인할 수 있다", r.status == 302 and "sessionid" in A2.cookies)

    # ============ 카드 2: 비밀번호 보관 ============
    say("\n## 카드 2 — 비밀번호 보관")
    con = db()
    rows = {r["username"]: r["password"] for r in con.execute("select username, password from auth_user")}
    pa, pb = rows[ua], rows[ub]
    alg_a, it_a, salt_a, h_a = pa.split("$")
    alg_b, it_b, salt_b, h_b = pb.split("$")
    say("DB(`auth_user.password`)에 저장된 값 — 알고리즘$반복횟수$소금값$해시 (소금값·해시는 앞부분만):")
    say("```")
    say(f"{ua}: {alg_a}${it_a}${short(salt_a)}${short(h_a)}")
    say(f"{ub}: {alg_b}${it_b}${short(salt_b)}${short(h_b)}")
    say("```")
    check("저장된 값이 PBKDF2-SHA256 해시 형식이다", alg_a == "pbkdf2_sha256" and int(it_a) >= 600000, f"반복 {it_a}회")
    check("저장된 값에 입력한 비밀번호 글자가 그대로 들어 있지 않다", PW_SAME not in pa and PW_SAME not in pb)
    check("같은 비밀번호로 만든 두 계정의 저장값이 서로 다르다(소금값이 다름)", pa != pb and salt_a != salt_b and h_a != h_b)

    # ============ 카드 3: 세션 ============
    say("\n## 카드 3 — 사람 알아보기(서버 세션)")
    say("방식: 서버가 세션을 DB에 저장하고, 브라우저에는 무작위 세션 ID 쿠키만 준다(HttpOnly). 만료는 24시간.")
    r = A.request("GET", "/api/me/", log="로그인한 상태로 /api/me/ 요청 (성공)")
    check("로그인 상태에서 같은 요청이 성공(200)한다", r.status == 200 and r.json().get("username") == ua)
    A.request("GET", "/app/", log="로그인한 상태로 자료 화면(/app/) 열기 (성공)")
    A.request("GET", "/api/data/", log="로그인한 상태로 자료 API(/api/data/) 요청 (성공)")
    sess_cookie = A.cookies["sessionid"]
    before = db().execute("select count(*) from django_session where session_key=?", (sess_cookie,)).fetchone()[0]
    stale = A.clone_session("A-stale")  # 로그아웃 '직전'의 쿠키를 그대로 복사해 둔다
    A.request("GET", "/app/")
    r = A.request("POST", "/logout/", log="로그아웃")
    after = db().execute("select count(*) from django_session where session_key=?", (sess_cookie,)).fetchone()[0]
    check("로그아웃하면 서버의 세션 행이 지워진다", before == 1 and after == 0, f"로그아웃 전 {before}건 → 후 {after}건")
    r = stale.request("GET", "/api/me/", log="로그아웃 전에 복사해 둔 같은 쿠키로, 같은 주소·같은 방식으로 다시 요청 (거절)")
    check("로그아웃 뒤 같은 값으로 다시 요청하면 거절(401)된다", r.status == 401)

    exp = db().execute("select expire_date from django_session limit 1").fetchone()
    set_cookie = [v for k, v in A2.request("GET", "/login/").headers if k.lower() == "set-cookie"]
    r = Client("x"); lg = Client("lg")
    lg.request("GET", "/login/")
    resp = lg.request("POST", "/login/", form={"username": ua, "password": PW_SAME})
    sc = [v for k, v in resp.headers if k.lower() == "set-cookie" and v.startswith("sessionid")]
    say("로그인 응답의 세션 쿠키 설정 줄(값은 가림):")
    say("```")
    say(mask(sc[0]) if sc else "(없음)")
    say("```")
    check("세션 쿠키에 만료(Max-Age=86400, 24시간)와 HttpOnly가 붙는다", bool(sc) and "Max-Age=86400" in sc[0] and "HttpOnly" in sc[0])
    ex = db().execute("select expire_date from django_session where session_key=?", (lg.cookies["sessionid"],)).fetchone()
    check("서버에 저장된 세션에 만료 시각이 있다", ex is not None and ex[0] is not None, f"expire_date={ex[0] if ex else None}")

    # 비밀번호 바꾸면 이전 세션 무효
    c1 = Client("c1"); login(c1, ua, PW_SAME)
    c2 = Client("c2"); login(c2, ua, PW_SAME)
    r = c1.request("POST", "/api/account/password/", json_body={"oldPassword": PW_SAME, "newPassword": PW_NEW}, log="기기1에서 비밀번호 변경")
    r_new = c1.request("GET", "/api/me/", log="변경한 기기1은 계속 사용 가능")
    r_old = c2.request("GET", "/api/me/", log="변경 전에 로그인해 둔 기기2의 세션으로 요청 (거절)")
    check("비밀번호를 바꾸면 이전에 발급한 세션이 더는 통하지 않는다(401)", r.status == 200 and r_old.status == 401 and r_new.status == 200)
    # 바꾼 비밀번호로 이후 테스트 진행
    PW_A_NOW = PW_NEW
    A = Client("A"); login(A, ua, PW_A_NOW)
    B = Client("B"); login(B, ub, PW_SAME)

    # ============ 카드 4: 남의 자료 ============
    say("\n## 카드 4 — 남의 자료 읽기·수정·삭제")

    def seed(c, tag):
        ids = {}
        r = c.request("POST", "/api/plans/", json_body={"title": f"{tag} 계획", "periodStart": "2026-10-01", "periodEnd": "2026-10-31",
                                                        "topicTags": ["운동"], "successCriteria": "주 3회", "estimatedTime": 10})
        ids["plan"] = int(r.json()["id"])
        r = c.request("POST", "/api/plans/", json_body={"title": f"{tag} 계획2", "periodStart": "2026-10-01", "periodEnd": "2026-10-31", "estimatedTime": 2})
        ids["plan2"] = int(r.json()["id"])
        r = c.request("POST", "/api/todos/", json_body={"title": f"{tag} 할 일", "planId": ids["plan"], "dueDate": "2026-10-20",
                                                        "tags": ["러닝"], "successCriteria": "5km", "estimatedTime": 1.5})
        ids["todo"] = int(r.json()["id"])
        r = c.request("POST", "/api/todos/", json_body={"title": f"{tag} 할 일2", "dueDate": "2026-10-22", "estimatedTime": 1})
        ids["todo2"] = int(r.json()["id"])
        r = c.request("POST", f"/api/todos/{ids['todo']}/records/", json_body={"start": "2026-10-06T09:00", "end": "2026-10-06T10:00",
                                                                          "blockedReason": f"{tag}만 아는 사정", "requestId": f"seed-{tag}"})
        ids["rec"] = int(r.json()["id"])
        return ids

    ida, idb = seed(A, "A계정"), seed(B, "B계정")
    say(f"계정 두 개(`{ua}`, `{ub}`)를 만들고 각각 계획 2건·할 일 2건·실행 기록 1건을 넣었습니다. 비밀번호는 적지 않습니다.")
    say(f"- A의 번호: 계획 {ida['plan']}, {ida['plan2']} / 할 일 {ida['todo']}, {ida['todo2']} / 기록 {ida['rec']}")
    say(f"- B의 번호: 계획 {idb['plan']}, {idb['plan2']} / 할 일 {idb['todo']}, {idb['todo2']} / 기록 {idb['rec']}")
    check("계정 두 개를 만들어 각각에 자료를 넣었다", True)

    def counts(c):
        d = c.request("GET", "/api/data/").json()
        return {"plans": len(d["plans"]), "todos": len(d["todos"]), "records": len(d["execRecords"])}

    def snapshot_titles(c):
        d = c.request("GET", "/api/data/").json()
        return [p["title"] for p in d["plans"]] + [t["title"] for t in d["todos"]]

    cnt_b_before, cnt_a_before = counts(B), counts(A)
    titles_b_before, titles_a_before = snapshot_titles(B), snapshot_titles(A)

    five = {}

    def attack(who, ids_mine, ids_theirs, label_who, label_whom):
        res = {}
        # 성공(내 자료)과 거절(남의 자료)을 나란히
        res["read_ok"] = who.request("GET", f"/api/todos/{ids_mine['todo']}/", log=f"[{label_who}] 내 할 일 읽기 (성공)")
        res["read_no"] = who.request("GET", f"/api/todos/{ids_theirs['todo']}/", log=f"[{label_who}] {label_whom}의 할 일 읽기 (거절)")
        res["read_plan_no"] = who.request("GET", f"/api/plans/{ids_theirs['plan']}/", log=f"[{label_who}] {label_whom}의 계획 읽기 (거절)")
        res["read_rec_no"] = who.request("GET", f"/api/records/{ids_theirs['rec']}/", log=f"[{label_who}] {label_whom}의 실행 기록 읽기 (거절)")
        res["edit_ok"] = who.request("PUT", f"/api/todos/{ids_mine['todo2']}/", json_body={"title": "내가 고친 제목", "dueDate": "2026-10-23", "estimatedTime": 1},
                                     log=f"[{label_who}] 내 할 일 수정 (성공)")
        tmp = who.request("POST", "/api/todos/", json_body={"title": "곧 지울 내 할 일", "dueDate": "2026-10-27", "estimatedTime": 1}).json()["id"]
        res["del_ok"] = who.request("DELETE", f"/api/todos/{tmp}/", log=f"[{label_who}] 내 할 일 삭제 (성공)")
        res["edit_no"] = who.request("PUT", f"/api/todos/{ids_theirs['todo']}/", json_body={"title": "남이 고친 제목", "dueDate": "2026-10-23", "estimatedTime": 9},
                                     log=f"[{label_who}] {label_whom}의 할 일 수정 (거절)")
        res["edit_plan_no"] = who.request("PUT", f"/api/plans/{ids_theirs['plan']}/", json_body={"title": "남이 고친 계획", "periodStart": "2026-10-01", "periodEnd": "2026-10-02", "estimatedTime": 9},
                                          log=f"[{label_who}] {label_whom}의 계획 수정 (거절)")
        res["del_no"] = who.request("DELETE", f"/api/todos/{ids_theirs['todo']}/", log=f"[{label_who}] {label_whom}의 할 일 삭제 (거절)")
        res["del_plan_no"] = who.request("DELETE", f"/api/plans/{ids_theirs['plan']}/", log=f"[{label_who}] {label_whom}의 계획 삭제 (거절)")
        res["del_rec_no"] = who.request("DELETE", f"/api/records/{ids_theirs['rec']}/", log=f"[{label_who}] {label_whom}의 실행 기록 삭제 (거절)")
        res["add_rec_no"] = who.request("POST", f"/api/todos/{ids_theirs['todo']}/records/", json_body={"start": "2026-10-06T09:00", "end": "2026-10-06T09:30", "requestId": "x1"},
                                        log=f"[{label_who}] {label_whom}의 할 일에 실행 기록 끼워 넣기 (거절)")
        res["complete_no"] = who.request("POST", f"/api/todos/{ids_theirs['todo']}/complete/", log=f"[{label_who}] {label_whom}의 할 일을 완료로 바꾸기 (거절)")
        res["link_plan_no"] = who.request("POST", "/api/todos/", json_body={"title": "남의 계획에 붙이기", "planId": ids_theirs["plan"], "dueDate": "2026-10-30", "estimatedTime": 1},
                                          log=f"[{label_who}] 내 할 일을 {label_whom}의 계획에 붙이기 (거절)")
        res["reorder_no"] = who.request("POST", "/api/todos/reorder/", json_body={"ids": [ids_theirs["todo"], ids_theirs["todo2"]]},
                                        log=f"[{label_who}] {label_whom}의 할 일 순서 바꾸기 (거절)")
        return res

    say("\n### A → B 방향 (A로 로그인해 B의 자료를 건드림)")
    ab = attack(A, ida, idb, "A", "B")
    mid_b = (counts(B), snapshot_titles(B))   # A의 공격 직후의 B (B는 아직 아무것도 안 고침)
    mid_a = (counts(A), snapshot_titles(A))   # B가 공격하기 직전의 A (A는 자기 할 일 제목만 고쳤음)
    say("\n### B → A 방향 (B로 로그인해 A의 자료를 건드림)")
    ba = attack(B, idb, ida, "B", "A")

    def rejected(r):
        return r.status in (403, 404)

    for tag, res in (("A→B", ab), ("B→A", ba)):
        check(f"[{tag}] 남의 자료 읽기(할 일·계획·실행 기록)가 모두 거절된다", all(rejected(res[k]) for k in ("read_no", "read_plan_no", "read_rec_no")),
              "상태코드 " + "/".join(str(res[k].status) for k in ("read_no", "read_plan_no", "read_rec_no")))
        check(f"[{tag}] 남의 자료 수정(할 일·계획)이 거절된다", rejected(res["edit_no"]) and rejected(res["edit_plan_no"]))
        check(f"[{tag}] 남의 자료 삭제(할 일·계획·실행 기록)가 거절된다", all(rejected(res[k]) for k in ("del_no", "del_plan_no", "del_rec_no")))
        check(f"[{tag}] 남의 자료에 끼워 넣기·완료·순서 바꾸기·계획 붙이기도 거절된다",
              all(rejected(res[k]) for k in ("add_rec_no", "complete_no", "link_plan_no", "reorder_no")))
        check(f"[{tag}] 내 자료의 읽기·수정·삭제는 성공(200)한다", res["read_ok"].status == 200 and res["edit_ok"].status == 200 and res["del_ok"].status == 200)
        check(f"[{tag}] 거절 응답이 존재 자체를 숨기는 404 이다(없는 번호의 응답과 같다)",
              res["read_no"].status == 404 and res["read_no"].body == A.request("GET", "/api/todos/99999999/").body)

    # 거절 전후 건수
    end_a = (counts(A), snapshot_titles(A))
    say("\n### 거절 앞뒤 자료 건수")
    say("```")
    say(f"B 계정 (A가 건드리기 전 → 후): {cnt_b_before} → {mid_b[0]}")
    say(f"A 계정 (B가 건드리기 전 → 후): {mid_a[0]} → {end_a[0]}")
    say("```")
    check("A의 공격 앞뒤로 B의 자료 건수가 같다(새로 생긴 자료도 없다)", cnt_b_before == mid_b[0])
    check("A의 공격 앞뒤로 B의 자료 내용(제목)도 그대로다", titles_b_before == mid_b[1])
    check("B의 공격 앞뒤로 A의 자료 건수가 같다(새로 생긴 자료도 없다)", mid_a[0] == end_a[0])
    check("B의 공격 앞뒤로 A의 자료 내용(제목)도 그대로다", mid_a[1] == end_a[1])

    # 주소·헤더·본문에 다른 계정을 적어 보내기
    say("\n### 주소·헤더·본문에 다른 계정을 적어 보내기")
    spoof = A.request("POST", "/api/todos/", json_body={"title": "A가 B 이름으로 만들기", "dueDate": "2026-10-25", "estimatedTime": 1,
                                                    "owner": int(idb["todo"]), "owner_id": 999, "user": ub, "username": ub, "user_id": 2},
                      headers={"X-User-Id": "2", "X-Owner": ub, "X-Account": ub},
                      log="본문(owner·user·username·user_id)과 헤더(X-User-Id·X-Owner·X-Account)에 B를 적어 할 일 만들기")
    spoof_id = int(spoof.json()["id"])
    la = A.request("GET", f"/api/data/?owner={idb['todo']}&user={ub}&username={ub}&user_id=2", headers={"X-User-Id": "2", "X-Owner": ub},
                   log="주소(?owner&user&username&user_id)와 헤더에 B를 적어 목록 요청")
    la_json = la.json()
    lb = B.request("GET", "/api/data/")
    owner_row = db().execute("select u.username from diary_todo t join auth_user u on u.id=t.owner_id where t.id=?", (spoof_id,)).fetchone()
    check("본문·헤더에 B를 적어 보내도 만들어진 할 일의 주인은 A(로그인한 사람)이다", owner_row and owner_row[0] == ua, f"DB상 주인 {owner_row[0] if owner_row else None}")
    check("그 할 일이 B의 목록에 나타나지 않는다", str(spoof_id) not in [t["id"] for t in lb.json()["todos"]])
    check("주소·헤더에 B를 적어 보내도 목록에는 A의 자료만 돌아온다",
          all("B계정" not in t["title"] for t in la_json["todos"]) and all("B계정" not in p["title"] for p in la_json["plans"]))
    body_all = la.body
    b_ids = [str(idb[k]) for k in ("todo", "todo2")]
    check("A의 목록 응답 전체에 B의 자료 제목·사정이 하나도 없다", "B계정" not in body_all and "B계정만 아는 사정" not in body_all)
    check("B의 목록 응답 전체에 A의 자료가 하나도 없다", "A계정" not in lb.body)

    # 로그인하지 않은 직접 요청
    say("\n### 로그인하지 않고 직접 요청")
    r_list = anon.request("GET", "/api/data/", log="로그인 없이 목록 요청 (거절)")
    r_one = anon.request("GET", f"/api/todos/{idb['todo']}/", log="로그인 없이 B의 할 일 한 건 요청 (거절)")
    r_put = anon.request("DELETE", f"/api/todos/{idb['todo']}/", log="로그인 없이 B의 할 일 삭제 요청 (거절)")
    check("로그인 없는 직접 요청(목록·읽기·삭제)이 모두 401로 거절된다", r_list.status == r_one.status == r_put.status == 401)
    check("그 거절 응답에 자료가 들어 있지 않다", "B계정" not in r_list.body + r_one.body)

    # ============ 연타·중복 ============
    say("\n## 보조 확인 — 완료 연타·중복 기록")
    t = A.request("POST", "/api/todos/", json_body={"title": "연타 시험", "dueDate": "2026-10-26", "estimatedTime": 1}).json()["id"]

    def click(_):
        return A.request("POST", f"/api/todos/{t}/complete/").json()["completedAt"]

    with ThreadPoolExecutor(8) as ex:
        stamps = list(ex.map(click, range(8)))
    row = db().execute("select status, completed_at from diary_todo where id=?", (t,)).fetchone()
    say(f"완료 버튼 요청 8번을 동시에 보낸 결과: 서버가 돌려준 완료 시각 {len(set(stamps))}종류, DB 상태 `{row[0]}`")
    check("완료 요청을 연달아 8번 보내도 완료 시각은 한 번만 정해진다", len(set(stamps)) == 1 and row[0] == "completed")
    rid = "dedupe-" + secrets.token_hex(4)
    body = {"start": "2026-10-06T09:00", "end": "2026-10-06T09:40", "blockedReason": "연타 시험", "requestId": rid}

    def rec(_):
        return A.request("POST", f"/api/todos/{t}/records/", json_body=body).status

    with ThreadPoolExecutor(6) as ex:
        sts = list(ex.map(rec, range(6)))
    n = db().execute("select count(*) from diary_execrecord where todo_id=?", (t,)).fetchone()[0]
    say(f"같은 실행 기록 요청(같은 requestId) 6번을 동시에 보낸 결과: 상태코드 {sorted(sts)}, DB 기록 {n}건")
    check("같은 요청이 여러 번 와도 실행 기록은 한 건만 남는다", n == 1)

    # ============ 내보내기·계정 삭제 ============
    say("\n## 보조 확인 — 내보내기·계정 삭제")
    exp = A.request("GET", "/api/export/")
    ej = exp.json()
    say(f"내보내기 응답: {exp.status}, Content-Disposition `{dict((k.lower(), v) for k, v in exp.headers).get('content-disposition')}`, "
        f"키 {sorted(ej.keys())}")
    check("내 자료 전체가 파일 하나(JSON)로 내보내진다", exp.status == 200 and {"plans", "todos", "execRecords", "experiment"} <= set(ej))
    check("내보내기에 B의 자료·비밀번호 정보가 없다", "B계정" not in exp.body and "pbkdf2" not in exp.body and "password" not in exp.body.lower())

    Dc = Client("D")
    signup(Dc, "tester.d", PW_OTHER)
    Dc.request("POST", "/api/plans/", json_body={"title": "지울 계획", "periodStart": "2026-10-01", "periodEnd": "2026-10-02", "estimatedTime": 1})
    Dc.request("POST", "/api/todos/", json_body={"title": "지울 할 일", "dueDate": "2026-10-02", "estimatedTime": 1})
    did = db().execute("select id from auth_user where username='tester.d'").fetchone()[0]
    before = {tb: db().execute(f"select count(*) from {tb} where owner_id=?", (did,)).fetchone()[0] for tb in ("diary_plan", "diary_todo")}
    bad = Dc.request("POST", "/api/account/delete/", json_body={"password": "wrong-password"}, log="틀린 비밀번호로 계정 삭제 시도 (거절)")
    r = Dc.request("POST", "/api/account/delete/", json_body={"password": PW_OTHER}, log="올바른 비밀번호로 계정 삭제")
    left = {tb: db().execute(f"select count(*) from {tb} where owner_id=?", (did,)).fetchone()[0] for tb in ("diary_plan", "diary_todo")}
    u_left = db().execute("select count(*) from auth_user where id=?", (did,)).fetchone()[0]
    say(f"삭제 전 자료 {before} → 삭제 후 {left}, 계정 행 {u_left}건")
    check("계정을 지우면 내 자료도 함께 지워진다", bad.status == 400 and r.status == 200 and u_left == 0 and not any(left.values()) and any(before.values()))
    check("남은 다른 계정(A, B)의 자료는 그대로다", counts(B)["todos"] >= 2 and counts(A)["todos"] >= 2)

    # 주소(URL)에 세션·토큰이 실려 다니지 않는지: 실제로 보낸 모든 요청 주소를 서버가 발급한 쿠키 값과 직접 비교
    leaked = [p for p in REQUEST_PATHS if "sessionid" in p or "csrftoken" in p or any(val in p for val in ISSUED_COOKIE_VALUES)]
    check("세션·토큰 값이 주소(URL)에 실려 다니지 않는다", not leaked,
          f"요청 주소 {len(REQUEST_PATHS)}개, 서버가 발급한 쿠키 값 {len(ISSUED_COOKIE_VALUES)}개와 대조")

    # 응답·화면에 비밀번호 원문이 없는지
    say("\n## 응답·화면에 비밀번호 원문이 없는지")
    pages = [anon.request("GET", "/").body, anon.request("GET", "/signup/").body, A.request("GET", "/app/").body,
             A.request("GET", "/static/diary/app.js").body, A.request("GET", "/api/data/").body, A.request("GET", "/api/me/").body, exp.body]
    allbody = "\n".join(pages)
    check("화면·정적 파일·API 응답 어디에도 비밀번호 원문이 없다", not any(s in allbody for s in (PW_SAME, PW_OTHER, PW_NEW)))
    check("화면·API 응답 어디에도 비밀키 원문이 없다", RUN_KEY not in allbody)
    check("브라우저 코드(app.js)에 세션·토큰을 저장하는 코드가 없다(localStorage/sessionStorage 미사용)",
          "localStorage" not in pages[3] and "sessionStorage" not in pages[3])
    err_page = anon.request("GET", "/nope-" + secrets.token_hex(3))
    check("오류 화면에도 비밀키·설정값이 노출되지 않는다", RUN_KEY not in err_page.body)


if __name__ == "__main__":
    main()
