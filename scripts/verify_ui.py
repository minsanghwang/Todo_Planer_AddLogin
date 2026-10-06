#!/usr/bin/env python3
"""화면(UI) 시험: 실제 브라우저(Chromium)로 사람이 하는 흐름을 그대로 따라 한다.

임시 DB와 일회용 비밀키로 서버를 띄우고, 가입부터 로그아웃까지 클릭·입력하며
"새로고침해도 남는지", "수정 전 계획이 남는지", "돌아보기 숫자가 맞는지" 등을 확인한다.
스크린샷은 SHOTS 폴더(기본: 임시 폴더)에 저장한다.

사용법:  python3 scripts/verify_ui.py
"""
import http.client
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("VERIFY_UI_PORT", "8766"))
BASE = f"http://127.0.0.1:{PORT}"
WORK = Path(tempfile.mkdtemp(prefix="diary-ui-"))
SHOTS = Path(os.environ.get("SHOTS", WORK / "shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
PW = "Pw-" + secrets.token_urlsafe(12)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (f"  — {detail}" if detail and not ok else ""))
    return ok


def start_server():
    run_key = "ui-" + secrets.token_urlsafe(30)  # 이 실행에서만 존재하는 일회용 값(고정값 아님)
    env = dict(os.environ, DJANGO_DEBUG="1", DJANGO_SECRET_KEY=run_key,
               DATABASE_URL=f"sqlite:///{WORK / 'ui.sqlite3'}")
    subprocess.run([sys.executable, "manage.py", "migrate", "-v", "0"], cwd=ROOT, env=env, check=True)
    proc = subprocess.Popen([sys.executable, "manage.py", "runserver", f"127.0.0.1:{PORT}", "--noreload"],
                            cwd=ROOT, env=env, stdout=open(WORK / "server.log", "w"), stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            http.client.HTTPConnection("127.0.0.1", PORT, timeout=1).request("GET", "/")
            return proc
        except OSError:
            time.sleep(0.3)
    proc.kill()
    raise RuntimeError("서버가 뜨지 않았습니다.")


def tab(page, name):
    page.locator(".tab", has_text=name).click()
    page.wait_for_timeout(250)


def wait_loaded(page):
    page.wait_for_selector(".tabs")


def run(page, ctx):
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))

    # --- 첫 화면 / 로그인 없이 자료 화면
    page.goto(BASE + "/")
    check("첫 화면은 로그인 화면이다", page.locator("input[name=password]").count() == 1 and "로그인" in page.title())
    page.goto(BASE + "/app/")
    check("로그인 없이 /app/ 을 열면 로그인 화면으로 이동한다", "/login/" in page.url and page.locator("input[name=password]").count() == 1)

    # --- 가입
    page.goto(BASE + "/signup/")
    page.fill("#username", "ui.tester")
    page.fill("#password", PW)
    page.fill("#password2", PW)
    page.click("button[type=submit]")
    wait_loaded(page)
    check("가입하면 바로 내 다이어리 화면이 열린다", page.url.endswith("/app/") and "ui.tester" in page.inner_text(".topbar"))

    # --- 계획 두 개
    def add_plan(title, tags, success, est, start="2026-10-01", end="2026-10-31"):
        page.fill("#pf_title", title)
        page.fill("#pf_start", start)
        page.fill("#pf_end", end)
        page.fill("#pf_tags", tags)
        page.fill("#pf_success", success)
        page.fill("#pf_est", est)
        page.click("button:has-text('계획 추가')")
        page.wait_for_selector(f".card h3:has-text('{title}')")

    add_plan("운동 습관 만들기", "운동, 러닝", "주 3회 5km", "12")
    add_plan("책 읽기", "독서", "한 달에 두 권", "20")
    check("계획이 목록에 보인다(기간·태그·성공 기준·예상 시간 포함)",
          "주 3회 5km" in page.inner_text("#tabContent") and "2026-10-01 ~ 2026-10-31" in page.inner_text("#tabContent")
          and page.locator(".tag", has_text="러닝").count() >= 1)

    # --- 우선순위 드래그
    def order():
        return page.locator("#planDragList .drag-item").all_inner_texts()

    before = order()
    page.locator("#planDragList .drag-item").nth(1).drag_to(page.locator("#planDragList .drag-item").nth(0))
    page.wait_for_timeout(700)
    after = order()
    check("우선순위 칸에서 드래그하면 순서가 바뀐다", before != after and "책 읽기" in after[0], f"{before} -> {after}")

    # --- 계획 수정 → 이전 버전 보존
    page.locator(".card:has(h3:has-text('운동 습관 만들기')) button:has-text('수정')").click()
    page.fill("#pf_title", "운동 습관 만들기 (수정)")
    page.fill("#pf_success", "주 4회 5km")
    page.click("button:has-text('수정 저장')")
    page.wait_for_selector("h3:has-text('운동 습관 만들기 (수정)')")
    page.locator(".link-btn", has_text="이전 버전 보기").first.click()
    txt = page.inner_text("#tabContent")
    check("계획을 고쳐도 고치기 전 계획이 남아 있다", "주 3회 5km" in txt and "운동 습관 만들기" in txt)

    # --- 할 일
    tab(page, "할 일")
    page.fill("#tf_title", "아침 러닝 5km")
    page.select_option("#tf_plan", label="운동 습관 만들기 (수정)")
    page.fill("#tf_start", "2026-09-28")
    page.fill("#tf_due", "2026-10-01")  # 서울 오늘(2026-10-06)보다 앞 → 지연
    page.fill("#tf_tags", "러닝")
    page.fill("#tf_success", "5km 30분 안")
    page.fill("#tf_est", "1.5")
    page.click("button:has-text('할 일 추가')")
    page.wait_for_selector("h3:has-text('아침 러닝 5km')")
    page.fill("#tf_title", "독서 30분")
    page.fill("#tf_due", "2026-10-30")
    page.fill("#tf_tags", "독서")
    page.fill("#tf_est", "0.5")
    page.click("button:has-text('할 일 추가')")
    page.wait_for_selector("h3:has-text('독서 30분')")
    check("지난 마감일의 할 일에 '지연' 표시가 붙는다", page.locator(".card:has(h3:has-text('아침 러닝')) .badge.overdue", has_text="지연").count() == 1)

    # --- 검색·필터·정렬
    page.fill("#ff_search", "독서")
    page.wait_for_timeout(300)
    check("검색하면 조건에 맞는 할 일만 보인다", page.locator("h3:has-text('아침 러닝')").count() == 0 and page.locator("h3:has-text('독서 30분')").count() >= 1)
    page.fill("#ff_search", "")
    page.wait_for_timeout(300)
    status_sel = page.locator(".card:has(h3:has-text('필터')) select").nth(0)  # 필터 카드의 첫 선택칸 = 상태
    status_sel.select_option("overdue")
    page.wait_for_timeout(300)
    check("'지연' 필터로 지연된 할 일만 보인다", page.locator("h3:has-text('아침 러닝')").count() >= 1 and page.locator("h3:has-text('독서 30분')").count() == 0)
    status_sel.select_option("all")

    # --- 실행 기록(막힌 이유 포함)
    page.locator(".card:has(h3:has-text('아침 러닝')) .link-btn", has_text="실행 기록 보기").click()
    page.fill("input[id^=ef_s_]", "2026-10-02T06:00")
    page.fill("input[id^=ef_e_]", "2026-10-02T07:30")
    page.fill("input[id^=ef_b_]", "비가 와서 중간에 멈춤")
    page.click("button:has-text('기록 추가')")
    page.wait_for_selector("text=막혔던 이유: 비가 와서 중간에 멈춤")
    check("실행 기록에 시작·끝·실제 시간·막힌 이유가 보인다", "1.50시간" in page.inner_text("#tabContent"))

    # --- 완료 연타 / 되돌리기
    btn = page.locator(".card:has(h3:has-text('아침 러닝')) button:has-text('완료로 변경')")
    btn.dblclick()
    page.wait_for_selector(".card:has(h3:has-text('아침 러닝')) .badge.done")
    check("완료 버튼을 연달아 눌러도 완료는 한 번만 반영된다", page.locator(".card:has(h3:has-text('아침 러닝')) .badge.done").count() == 1)
    check("완료한 일은 '지연'으로 다시 세지 않는다(지연 표시가 사라짐)", page.locator(".card:has(h3:has-text('아침 러닝')) .badge.overdue", has_text="지연").count() == 0)

    # --- 돌아보기
    tab(page, "돌아보기")
    nums = [t.strip() for t in page.locator(".metric .num").all_inner_texts()]
    labels = [t.strip() for t in page.locator(".metric .lab").all_inner_texts()]
    m = dict(zip([l.split(" (")[0] for l in labels], nums))
    page.screenshot(path=str(SHOTS / "review.png"), full_page=True)
    check("돌아보기: 계획 수 2, 완료 1, 지연 0(완료한 일은 지연에서 빠짐), 막힘 1", (m.get("계획 수"), m.get("완료 수"), m.get("지연 수"), m.get("막힘 수")) == ("2", "1", "0", "1"), str(m))
    check("돌아보기: 예상 2.0h, 실제 1.5h, 차이 -0.5h", (m.get("예상 시간"), m.get("실제 시간")) == ("2.0h", "1.5h") and m.get("차이") == "-0.5h", str(m))
    page.locator(".metric", has_text="막힘 수").click()
    check("집계 숫자를 누르면 그 숫자가 나온 할 일로 간다", "아침 러닝 5km" in page.inner_text("#tabContent") and "막힘 (1건)" in page.inner_text("#tabContent"))

    # --- 고칠 점 → 계획으로 넘어감
    page.fill("#rv_note", "예상 시간을 넉넉히 잡기")
    page.select_option("#rv_plan", label="책 읽기")
    page.click("button:has-text('다음 계획에 반영')")
    page.wait_for_selector("text=예상 시간을 넉넉히 잡기")
    check("돌아보기에서 정한 고칠 점이 다음 계획으로 넘어간다", page.locator(".card:has(h3:has-text('책 읽기')) .history-item", has_text="예상 시간을 넉넉히 잡기").count() == 1)

    # --- 5일 기록 탭
    tab(page, "5일 기록")
    page.fill("#ex_q", "아침에 달리면 하루 계획을 더 지킬까?")
    page.fill("#ex_m", "그날 끝낸 할 일 수")
    page.fill("#ex_u", "개")
    page.fill("#ex_r", "아침에 먼저 달린다")
    page.click("button:has-text('고정하기')")
    page.wait_for_selector("text=고정된 질문과 지표")
    page.fill("#dy_v", "3")
    page.click("button:has-text('오늘 기록 저장')")
    page.wait_for_selector("text=1일차")
    page.screenshot(path=str(SHOTS / "five.png"), full_page=True)
    check("5일 기록: 질문·지표·단위가 고정되고 오늘 기록이 1일차로 저장된다", "개" in page.inner_text("#tabContent") and "1일차" in page.inner_text("#tabContent"))
    page.fill("#dy_v", "5")
    page.click("button:has-text('오늘 값 덮어쓰기')")
    page.wait_for_timeout(400)
    check("같은 날 다시 저장하면 새 기록이 아니라 덮어쓴다(1/5일 그대로)", "(1/5일)" in page.inner_text("#tabContent") and "5.00" in page.inner_text("#tabContent"))

    # --- 새로고침 후에도 그대로
    page.reload()
    wait_loaded(page)
    tab(page, "계획")
    t1 = page.inner_text("#tabContent")
    tab(page, "할 일")
    t2 = page.inner_text("#tabContent")
    tab(page, "5일 기록")
    t3 = page.inner_text("#tabContent")
    check("새로고침해도 계획·고칠 점·수정 전 버전이 그대로다", "운동 습관 만들기 (수정)" in t1 and "예상 시간을 넉넉히 잡기" in t1 and "(1건)" in t1)
    check("새로고침해도 할 일·완료 상태·실행 기록 수가 그대로다", "아침 러닝 5km" in t2 and "독서 30분" in t2 and "완료" in t2 and "실행 기록 보기/추가 (1건)" in t2)
    check("새로고침해도 5일 기록(질문·값)이 그대로다", "아침에 달리면 하루 계획을 더 지킬까?" in t3 and "5.00" in t3)
    # 우선순위 순서도 유지
    tab(page, "계획")
    check("새로고침해도 드래그로 바꾼 우선순위 순서가 그대로다", order()[0].find("책 읽기") >= 0)

    # --- 되돌리기
    tab(page, "할 일")
    page.locator(".card:has(h3:has-text('아침 러닝')) button:has-text('진행 중으로 되돌리기')").click()
    page.wait_for_selector(".card:has(h3:has-text('아침 러닝')) button:has-text('완료로 변경')")
    check("완료한 일을 다시 진행 중으로 바꿀 수 있다", True)

    # --- 내보내기
    tab(page, "내 계정")
    page.screenshot(path=str(SHOTS / "account.png"), full_page=True)
    check("계정 삭제 안내가 화면에 적혀 있다", "모두 함께 영구 삭제" in page.inner_text("#tabContent"))
    with page.expect_download() as dl:
        page.click("a:has-text('JSON 파일 내보내기')")
    data = json.loads(Path(dl.value.path()).read_text(encoding="utf-8"))
    check("내 자료 전체가 JSON 파일 하나로 내보내진다", {"plans", "todos", "execRecords", "experiment"} <= set(data)
          and len(data["plans"]) == 2 and len(data["todos"]) == 2 and len(data["execRecords"]) == 1 and len(data["experiment"]["days"]) == 1)

    # --- 로그아웃
    page.click(".topbar button:has-text('로그아웃')")
    page.wait_for_selector("input[name=password]")
    page.goto(BASE + "/app/")
    check("로그아웃한 뒤 /app/ 을 열면 로그인 화면이 나온다", "/login/" in page.url)

    # --- 다시 로그인하면 내 자료가 그대로
    page.fill("#username", "ui.tester")
    page.fill("#password", PW)
    page.click("button[type=submit]")
    wait_loaded(page)
    page.wait_for_selector("h3:has-text('책 읽기')")
    check("다시 로그인하면 내 자료가 그대로 있다", "책 읽기" in page.inner_text("#tabContent"))

    # --- 계정 삭제
    tab(page, "내 계정")
    page.fill("#del_pw", PW)
    page.click("button:has-text('계정과 자료 삭제')")
    page.wait_for_selector("input[name=password]")
    check("계정을 지우면 로그인 화면으로 돌아간다", page.url.rstrip("/") == BASE)
    page.fill("#username", "ui.tester")
    page.fill("#password", PW)
    page.click("button[type=submit]")
    page.wait_for_selector(".error")
    check("지운 계정으로는 더 로그인되지 않는다", "올바르지 않습니다" in page.inner_text(".error"))


def main():
    proc = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1100, "height": 900}, accept_downloads=True, locale="ko-KR", timezone_id="Asia/Seoul")
            page = ctx.new_page()
            errors, bad = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # 'Failed to load resource' 메시지는 아래 bad 목록(주소·상태코드)으로 따로 정확히 검사한다
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
            page.on("response", lambda r: bad.append((r.status, r.request.method, r.url.replace(BASE, ""))) if r.status >= 400 else None)
            try:
                run(page, ctx)
            except Exception as e:  # 시험 도중 막히면 어디서 막혔는지 화면을 남긴다
                page.screenshot(path=str(SHOTS / "failure.png"), full_page=True)
                check("시험이 끝까지 진행된다", False, f"{type(e).__name__}: {str(e)[:300]}")
            check("브라우저 콘솔·페이지에 자바스크립트 오류가 없다", not errors, "; ".join(errors)[:300])
            # 오류 응답은 딱 한 건이어야 한다: 맨 끝에서 '지운 계정으로 로그인'을 일부러 시도한 것(401)
            check("4xx/5xx 응답은 일부러 시도한 '지운 계정 로그인 실패' 한 건뿐이다", bad == [(401, "POST", "/login/")], str(bad))
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n통과 {passed} / {len(RESULTS)}   스크린샷: {SHOTS}")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
