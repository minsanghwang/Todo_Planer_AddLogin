# 확인 기록 (자동 생성)

`python3 scripts/verify_auth.py` 가 임시 DB와 일회용 비밀키로 서버를 띄워 실제로 보낸 요청과 받은 응답입니다. 쿠키·CSRF 토큰은 앞 4글자만 남기고 `…생략`으로 가렸고, 비밀번호와 비밀키는 `***`로 가렸습니다. (로컬 개발 서버는 HTTP라서 쿠키의 Secure 표시는 배포 환경에서만 붙습니다.)

## 카드 1 — 가입·로그인·로그아웃
**로그인 없이 첫 화면(/) 열기**
```
GET /
→ 200
   Set-Cookie: csrftoken=qq6V…생략; expires=Tue, 05 Oct 2027 00:34:53 GMT; Max-Age=31449600; Path=/; SameSite=Lax
   (HTML 922자) 로그인 · 플랜두씨 다이어리 2              플랜두씨 다이어리     내 계획과 기록은 로그인한 나만 볼 수 있습니다.                    아이디             비밀번호             로그인
```
- ✅ 첫 화면은 로그인 화면이다(로그인 없이 열림)
**로그인 없이 자료 화면(/app/) 열기**
```
GET /app/
Cookie: csrftoken=qq6V…생략
→ 302
   Location: /login/?next=/app/
```
- ✅ 로그인 없이 /app/ 을 열면 로그인 화면으로 보내진다
**로그인 없이 자료 API 직접 요청**
```
GET /api/data/
Cookie: csrftoken=qq6V…생략
→ 401
   {"detail": "로그인이 필요합니다."}
```
- ✅ 로그인 없이 자료 API를 부르면 401
- ✅ 가입 화면에서 새 계정을 만들 수 있다 (A) — 가입 응답 302

**같은 아이디로 다시 가입**
```
POST /signup/
Cookie: csrftoken=CTU1…생략
Body: username=tester.a&password=***&password2=***
→ 400
   Set-Cookie: csrftoken=CTU1…생략; expires=Tue, 05 Oct 2027 00:34:54 GMT; Max-Age=31449600; Path=/; SameSite=Lax
   (HTML 1117자) 가입 · 플랜두씨 다이어리 2              가입하기     아이디는 영문 소문자·숫자·점·밑줄·하이픈 3~30자, 비밀번호는 8자 이상입니다.      이미 사용 중인 아이디입니다.                  아이디
```
- ✅ 같은 아이디로 두 번 가입되지 않는다
**대소문자만 바꿔 가입**
```
POST /signup/
Cookie: csrftoken=CTU1…생략
Body: username=TESTER.A&password=***&password2=***
→ 400
   Set-Cookie: csrftoken=CTU1…생략; expires=Tue, 05 Oct 2027 00:34:54 GMT; Max-Age=31449600; Path=/; SameSite=Lax
   (HTML 1117자) 가입 · 플랜두씨 다이어리 2              가입하기     아이디는 영문 소문자·숫자·점·밑줄·하이픈 3~30자, 비밀번호는 8자 이상입니다.      이미 사용 중인 아이디입니다.                  아이디
```
- ✅ 대소문자만 다른 아이디로도 이중 가입되지 않는다 — 해당 아이디 행 수 1
**아이디는 맞고 비밀번호가 틀림**
```
POST /login/
Cookie: csrftoken=hmSt…생략
Body: username=tester.a&password=***
→ 401
   Set-Cookie: csrftoken=hmSt…생략; expires=Tue, 05 Oct 2027 00:34:54 GMT; Max-Age=31449600; Path=/; SameSite=Lax
   (HTML 991자) 로그인 · 플랜두씨 다이어리 2              플랜두씨 다이어리     내 계획과 기록은 로그인한 나만 볼 수 있습니다.     아이디 또는 비밀번호가 올바르지 않습니다.                 아이디
```
**없는 아이디**
```
POST /login/
Cookie: csrftoken=25h2…생략
Body: username=nobody.here&password=***
→ 401
   Set-Cookie: csrftoken=25h2…생략; expires=Tue, 05 Oct 2027 00:34:55 GMT; Max-Age=31449600; Path=/; SameSite=Lax
   (HTML 994자) 로그인 · 플랜두씨 다이어리 2              플랜두씨 다이어리     내 계획과 기록은 로그인한 나만 볼 수 있습니다.     아이디 또는 비밀번호가 올바르지 않습니다.                 아이디
```
- ✅ 비밀번호만 틀렸을 때와 아이디가 없을 때 안내 문구·상태코드가 같다 — 둘 다 401: 아이디 또는 비밀번호가 올바르지 않습니다.
**올바른 아이디·비밀번호로 로그인**
```
POST /login/
Cookie: csrftoken=PoBe…생략
Body: username=tester.a&password=***
→ 302
   Location: /app/
   Set-Cookie: csrftoken=y2gh…생략; expires=Tue, 05 Oct 2027 00:34:55 GMT; Max-Age=31449600; Path=/; SameSite=Lax
   Set-Cookie: sessionid=7h8e…생략; expires=Wed, 07 Oct 2026 00:34:55 GMT; HttpOnly; Max-Age=86400; Path=/; SameSite=Lax
```
- ✅ 만든 계정으로 로그인할 수 있다

## 카드 2 — 비밀번호 보관
DB(`auth_user.password`)에 저장된 값 — 알고리즘$반복횟수$소금값$해시 (소금값·해시는 앞부분만):
```
tester.a: pbkdf2_sha256$1500000$QBmYIN…생략$bncIl2…생략
tester.b: pbkdf2_sha256$1500000$sHXUvQ…생략$4NmR2Y…생략
```
- ✅ 저장된 값이 PBKDF2-SHA256 해시 형식이다 — 반복 1500000회
- ✅ 저장된 값에 입력한 비밀번호 글자가 그대로 들어 있지 않다
- ✅ 같은 비밀번호로 만든 두 계정의 저장값이 서로 다르다(소금값이 다름)

## 카드 3 — 사람 알아보기(서버 세션)
방식: 서버가 세션을 DB에 저장하고, 브라우저에는 무작위 세션 ID 쿠키만 준다(HttpOnly). 만료는 24시간.
**로그인한 상태로 /api/me/ 요청 (성공)**
```
GET /api/me/
Cookie: csrftoken=5EJs…생략; sessionid=kchc…생략
→ 200
   {"username": "tester.a", "today": "2026-10-06"}
```
- ✅ 로그인 상태에서 같은 요청이 성공(200)한다
**로그인한 상태로 자료 화면(/app/) 열기 (성공)**
```
GET /app/
Cookie: csrftoken=5EJs…생략; sessionid=kchc…생략
→ 200
   Set-Cookie: csrftoken=5EJs…생략; expires=Tue, 05 Oct 2027 00:34:55 GMT; Max-Age=31449600; Path=/; SameSite=Lax
   (HTML 754자) 다이어리 · 플랜두씨 다이어리 2                     플랜두씨 다이어리   · tester.a 님의 기록 (나만 볼 수 있음)          로그아웃           불러오는 중...
```
**로그인한 상태로 자료 API(/api/data/) 요청 (성공)**
```
GET /api/data/
Cookie: csrftoken=5EJs…생략; sessionid=kchc…생략
→ 200
   {"plans": [], "todos": [], "execRecords": [], "today": "2026-10-06"}
```
**로그아웃**
```
POST /logout/
Cookie: csrftoken=5EJs…생략; sessionid=kchc…생략
→ 302
   Location: /
   Set-Cookie: sessionid=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=Lax
```
- ✅ 로그아웃하면 서버의 세션 행이 지워진다 — 로그아웃 전 1건 → 후 0건
**로그아웃 전에 복사해 둔 같은 쿠키로, 같은 주소·같은 방식으로 다시 요청 (거절)**
```
GET /api/me/
Cookie: csrftoken=5EJs…생략; sessionid=kchc…생략
→ 401
   Set-Cookie: sessionid=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=Lax
   {"detail": "로그인이 필요합니다."}
```
- ✅ 로그아웃 뒤 같은 값으로 다시 요청하면 거절(401)된다
로그인 응답의 세션 쿠키 설정 줄(값은 가림):
```
sessionid=xrdm…생략; expires=Wed, 07 Oct 2026 00:34:56 GMT; HttpOnly; Max-Age=86400; Path=/; SameSite=Lax
```
- ✅ 세션 쿠키에 만료(Max-Age=86400, 24시간)와 HttpOnly가 붙는다
- ✅ 서버에 저장된 세션에 만료 시각이 있다 — expire_date=2026-10-07 00:34:56.140604
**기기1에서 비밀번호 변경**
```
POST /api/account/password/
Cookie: csrftoken=Ejho…생략; sessionid=066g…생략
Body: {"oldPassword": "***", "newPassword": "***"}
→ 200
   Set-Cookie: sessionid=8z2p…생략; expires=Wed, 07 Oct 2026 00:34:57 GMT; HttpOnly; Max-Age=86400; Path=/; SameSite=Lax
   {"ok": true}
```
**변경한 기기1은 계속 사용 가능**
```
GET /api/me/
Cookie: csrftoken=Ejho…생략; sessionid=8z2p…생략
→ 200
   {"username": "tester.a", "today": "2026-10-06"}
```
**변경 전에 로그인해 둔 기기2의 세션으로 요청 (거절)**
```
GET /api/me/
Cookie: csrftoken=TJrp…생략; sessionid=woi8…생략
→ 401
   Set-Cookie: sessionid=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=Lax
   {"detail": "로그인이 필요합니다."}
```
- ✅ 비밀번호를 바꾸면 이전에 발급한 세션이 더는 통하지 않는다(401)

## 카드 4 — 남의 자료 읽기·수정·삭제
계정 두 개(`tester.a`, `tester.b`)를 만들고 각각 계획 2건·할 일 2건·실행 기록 1건을 넣었습니다. 비밀번호는 적지 않습니다.
- A의 번호: 계획 1, 2 / 할 일 1, 2 / 기록 1
- B의 번호: 계획 3, 4 / 할 일 3, 4 / 기록 2
- ✅ 계정 두 개를 만들어 각각에 자료를 넣었다

### A → B 방향 (A로 로그인해 B의 자료를 건드림)
**[A] 내 할 일 읽기 (성공)**
```
GET /api/todos/1/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 200
   {"planId": "1", "title": "A계정 할 일", "tags": ["러닝"], "periodStart": null, "dueDate": "2026-10-20", "successCriteria": "5km", "estimatedTime": 1.5, "priority": 1, "id": "1", "status": "in_progress", "completedAt": null, "history": []}
```
**[A] B의 할 일 읽기 (거절)**
```
GET /api/todos/3/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 계획 읽기 (거절)**
```
GET /api/plans/3/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 실행 기록 읽기 (거절)**
```
GET /api/records/2/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] 내 할 일 수정 (성공)**
```
PUT /api/todos/2/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
Body: {"title": "내가 고친 제목", "dueDate": "2026-10-23", "estimatedTime": 1}
→ 200
   {"planId": null, "title": "내가 고친 제목", "tags": [], "periodStart": null, "dueDate": "2026-10-23", "successCriteria": "", "estimatedTime": 1.0, "priority": 2, "id": "2", "status": "in_progress", "completedAt": null, "history": [{"planId": null, "title": "A계정 할 일2", "tags": [], "periodStart": null, "dueDate": "2026-10-22", "successCriteria": "", "estimatedTime": 1.0, "priority": 2, "editedAt": "2026-1
```
**[A] 내 할 일 삭제 (성공)**
```
DELETE /api/todos/5/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 200
   {"ok": true}
```
**[A] B의 할 일 수정 (거절)**
```
PUT /api/todos/3/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
Body: {"title": "남이 고친 제목", "dueDate": "2026-10-23", "estimatedTime": 9}
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 계획 수정 (거절)**
```
PUT /api/plans/3/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
Body: {"title": "남이 고친 계획", "periodStart": "2026-10-01", "periodEnd": "2026-10-02", "estimatedTime": 9}
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 할 일 삭제 (거절)**
```
DELETE /api/todos/3/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 계획 삭제 (거절)**
```
DELETE /api/plans/3/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 실행 기록 삭제 (거절)**
```
DELETE /api/records/2/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 할 일에 실행 기록 끼워 넣기 (거절)**
```
POST /api/todos/3/records/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
Body: {"start": "2026-10-06T09:00", "end": "2026-10-06T09:30", "requestId": "x1"}
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 할 일을 완료로 바꾸기 (거절)**
```
POST /api/todos/3/complete/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] 내 할 일을 B의 계획에 붙이기 (거절)**
```
POST /api/todos/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
Body: {"title": "남의 계획에 붙이기", "planId": 3, "dueDate": "2026-10-30", "estimatedTime": 1}
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[A] B의 할 일 순서 바꾸기 (거절)**
```
POST /api/todos/reorder/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
Body: {"ids": [3, 4]}
→ 404
   {"detail": "찾을 수 없습니다."}
```

### B → A 방향 (B로 로그인해 A의 자료를 건드림)
**[B] 내 할 일 읽기 (성공)**
```
GET /api/todos/3/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 200
   {"planId": "3", "title": "B계정 할 일", "tags": ["러닝"], "periodStart": null, "dueDate": "2026-10-20", "successCriteria": "5km", "estimatedTime": 1.5, "priority": 1, "id": "3", "status": "in_progress", "completedAt": null, "history": []}
```
**[B] A의 할 일 읽기 (거절)**
```
GET /api/todos/1/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 계획 읽기 (거절)**
```
GET /api/plans/1/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 실행 기록 읽기 (거절)**
```
GET /api/records/1/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] 내 할 일 수정 (성공)**
```
PUT /api/todos/4/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
Body: {"title": "내가 고친 제목", "dueDate": "2026-10-23", "estimatedTime": 1}
→ 200
   {"planId": null, "title": "내가 고친 제목", "tags": [], "periodStart": null, "dueDate": "2026-10-23", "successCriteria": "", "estimatedTime": 1.0, "priority": 2, "id": "4", "status": "in_progress", "completedAt": null, "history": [{"planId": null, "title": "B계정 할 일2", "tags": [], "periodStart": null, "dueDate": "2026-10-22", "successCriteria": "", "estimatedTime": 1.0, "priority": 2, "editedAt": "2026-1
```
**[B] 내 할 일 삭제 (성공)**
```
DELETE /api/todos/6/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 200
   {"ok": true}
```
**[B] A의 할 일 수정 (거절)**
```
PUT /api/todos/1/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
Body: {"title": "남이 고친 제목", "dueDate": "2026-10-23", "estimatedTime": 9}
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 계획 수정 (거절)**
```
PUT /api/plans/1/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
Body: {"title": "남이 고친 계획", "periodStart": "2026-10-01", "periodEnd": "2026-10-02", "estimatedTime": 9}
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 할 일 삭제 (거절)**
```
DELETE /api/todos/1/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 계획 삭제 (거절)**
```
DELETE /api/plans/1/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 실행 기록 삭제 (거절)**
```
DELETE /api/records/1/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 할 일에 실행 기록 끼워 넣기 (거절)**
```
POST /api/todos/1/records/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
Body: {"start": "2026-10-06T09:00", "end": "2026-10-06T09:30", "requestId": "x1"}
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 할 일을 완료로 바꾸기 (거절)**
```
POST /api/todos/1/complete/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] 내 할 일을 A의 계획에 붙이기 (거절)**
```
POST /api/todos/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
Body: {"title": "남의 계획에 붙이기", "planId": 1, "dueDate": "2026-10-30", "estimatedTime": 1}
→ 404
   {"detail": "찾을 수 없습니다."}
```
**[B] A의 할 일 순서 바꾸기 (거절)**
```
POST /api/todos/reorder/
Cookie: csrftoken=YlrC…생략; sessionid=154r…생략
Body: {"ids": [1, 2]}
→ 404
   {"detail": "찾을 수 없습니다."}
```
- ✅ [A→B] 남의 자료 읽기(할 일·계획·실행 기록)가 모두 거절된다 — 상태코드 404/404/404
- ✅ [A→B] 남의 자료 수정(할 일·계획)이 거절된다
- ✅ [A→B] 남의 자료 삭제(할 일·계획·실행 기록)가 거절된다
- ✅ [A→B] 남의 자료에 끼워 넣기·완료·순서 바꾸기·계획 붙이기도 거절된다
- ✅ [A→B] 내 자료의 읽기·수정·삭제는 성공(200)한다
- ✅ [A→B] 거절 응답이 존재 자체를 숨기는 404 이다(없는 번호의 응답과 같다)
- ✅ [B→A] 남의 자료 읽기(할 일·계획·실행 기록)가 모두 거절된다 — 상태코드 404/404/404
- ✅ [B→A] 남의 자료 수정(할 일·계획)이 거절된다
- ✅ [B→A] 남의 자료 삭제(할 일·계획·실행 기록)가 거절된다
- ✅ [B→A] 남의 자료에 끼워 넣기·완료·순서 바꾸기·계획 붙이기도 거절된다
- ✅ [B→A] 내 자료의 읽기·수정·삭제는 성공(200)한다
- ✅ [B→A] 거절 응답이 존재 자체를 숨기는 404 이다(없는 번호의 응답과 같다)

### 거절 앞뒤 자료 건수
```
B 계정 (A가 건드리기 전 → 후): {'plans': 2, 'todos': 2, 'records': 1} → {'plans': 2, 'todos': 2, 'records': 1}
A 계정 (B가 건드리기 전 → 후): {'plans': 2, 'todos': 2, 'records': 1} → {'plans': 2, 'todos': 2, 'records': 1}
```
- ✅ A의 공격 앞뒤로 B의 자료 건수가 같다(새로 생긴 자료도 없다)
- ✅ A의 공격 앞뒤로 B의 자료 내용(제목)도 그대로다
- ✅ B의 공격 앞뒤로 A의 자료 건수가 같다(새로 생긴 자료도 없다)
- ✅ B의 공격 앞뒤로 A의 자료 내용(제목)도 그대로다

### 주소·헤더·본문에 다른 계정을 적어 보내기
**본문(owner·user·username·user_id)과 헤더(X-User-Id·X-Owner·X-Account)에 B를 적어 할 일 만들기**
```
POST /api/todos/
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
X-User-Id: 2
X-Owner: tester.b
X-Account: tester.b
Body: {"title": "A가 B 이름으로 만들기", "dueDate": "2026-10-25", "estimatedTime": 1, "owner": 3, "owner_id": 999, "user": "tester.b", "username": "tester.b", "user_id": 2}
→ 201
   {"planId": null, "title": "A가 B 이름으로 만들기", "tags": [], "periodStart": null, "dueDate": "2026-10-25", "successCriteria": "", "estimatedTime": 1.0, "priority": 3, "id": "7", "status": "in_progress", "completedAt": null, "history": []}
```
**주소(?owner&user&username&user_id)와 헤더에 B를 적어 목록 요청**
```
GET /api/data/?owner=3&user=tester.b&username=tester.b&user_id=2
Cookie: csrftoken=AdVf…생략; sessionid=rjzd…생략
X-User-Id: 2
X-Owner: tester.b
→ 200
   {"plans": [{"title": "A계정 계획", "topicTags": ["운동"], "periodStart": "2026-10-01", "periodEnd": "2026-10-31", "priority": 1, "successCriteria": "주 3회", "estimatedTime": 10.0, "id": "1", "history": [], "improvementNotes": []}, {"title": "A계정 계획2", "topicTags": [], "periodStart": "2026-10-01", "periodEnd": "2026-10-31", "priority": 2, "successCriteria": "", "estimatedTime": 2.0, "id": "2", "history": 
```
- ✅ 본문·헤더에 B를 적어 보내도 만들어진 할 일의 주인은 A(로그인한 사람)이다 — DB상 주인 tester.a
- ✅ 그 할 일이 B의 목록에 나타나지 않는다
- ✅ 주소·헤더에 B를 적어 보내도 목록에는 A의 자료만 돌아온다
- ✅ A의 목록 응답 전체에 B의 자료 제목·사정이 하나도 없다
- ✅ B의 목록 응답 전체에 A의 자료가 하나도 없다

### 로그인하지 않고 직접 요청
**로그인 없이 목록 요청 (거절)**
```
GET /api/data/
Cookie: csrftoken=qq6V…생략
→ 401
   {"detail": "로그인이 필요합니다."}
```
**로그인 없이 B의 할 일 한 건 요청 (거절)**
```
GET /api/todos/3/
Cookie: csrftoken=qq6V…생략
→ 401
   {"detail": "로그인이 필요합니다."}
```
**로그인 없이 B의 할 일 삭제 요청 (거절)**
```
DELETE /api/todos/3/
Cookie: csrftoken=qq6V…생략
→ 401
   {"detail": "로그인이 필요합니다."}
```
- ✅ 로그인 없는 직접 요청(목록·읽기·삭제)이 모두 401로 거절된다
- ✅ 그 거절 응답에 자료가 들어 있지 않다

## 보조 확인 — 완료 연타·중복 기록
완료 버튼 요청 8번을 동시에 보낸 결과: 서버가 돌려준 완료 시각 1종류, DB 상태 `completed`
- ✅ 완료 요청을 연달아 8번 보내도 완료 시각은 한 번만 정해진다
같은 실행 기록 요청(같은 requestId) 6번을 동시에 보낸 결과: 상태코드 [200, 200, 200, 200, 200, 201], DB 기록 1건
- ✅ 같은 요청이 여러 번 와도 실행 기록은 한 건만 남는다

## 보조 확인 — 내보내기·계정 삭제
내보내기 응답: 200, Content-Disposition `attachment; filename="diary-export-2026-10-06.json"`, 키 ['execRecords', 'experiment', 'exportedAt', 'plans', 'todos', 'username']
- ✅ 내 자료 전체가 파일 하나(JSON)로 내보내진다
- ✅ 내보내기에 B의 자료·비밀번호 정보가 없다
**틀린 비밀번호로 계정 삭제 시도 (거절)**
```
POST /api/account/delete/
Cookie: csrftoken=3DbM…생략; sessionid=4ygc…생략
Body: {"password": "***"}
→ 400
   {"detail": "비밀번호가 올바르지 않습니다."}
```
**올바른 비밀번호로 계정 삭제**
```
POST /api/account/delete/
Cookie: csrftoken=3DbM…생략; sessionid=4ygc…생략
Body: {"password": "***"}
→ 200
   Set-Cookie: sessionid=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=Lax
   {"ok": true}
```
삭제 전 자료 {'diary_plan': 1, 'diary_todo': 1} → 삭제 후 {'diary_plan': 0, 'diary_todo': 0}, 계정 행 0건
- ✅ 계정을 지우면 내 자료도 함께 지워진다
- ✅ 남은 다른 계정(A, B)의 자료는 그대로다
- ✅ 세션·토큰 값이 주소(URL)에 실려 다니지 않는다 — 요청 주소 121개, 서버가 발급한 쿠키 값 32개와 대조

## 응답·화면에 비밀번호 원문이 없는지
- ✅ 화면·정적 파일·API 응답 어디에도 비밀번호 원문이 없다
- ✅ 화면·API 응답 어디에도 비밀키 원문이 없다
- ✅ 브라우저 코드(app.js)에 세션·토큰을 저장하는 코드가 없다(localStorage/sessionStorage 미사용)
- ✅ 오류 화면에도 비밀키·설정값이 노출되지 않는다

## 서버 로그·저장소 전체 검사
```
서버 로그 마지막 줄들(원문 그대로, 본문·쿠키는 기록되지 않음):
[06/Oct/2026 09:35:00] "GET /static/diary/app.js HTTP/1.1" 200 33763
2026-10-06 09:35:00,456 GET /api/data/ -> 200 (user)
[06/Oct/2026 09:35:00] "GET /api/data/ HTTP/1.1" 200 2039
2026-10-06 09:35:00,459 GET /api/me/ -> 200 (user)
[06/Oct/2026 09:35:00] "GET /api/me/ HTTP/1.1" 200 47
2026-10-06 09:35:00,464 GET /nope-637fe0 -> 404 (anon)
2026-10-06 09:35:00,464 Not Found: /nope-637fe0
[06/Oct/2026 09:35:00] "GET /nope-637fe0 HTTP/1.1" 404 6345
```
- ✅ 서버 로그에 비밀번호(공통) 원문이 없다
- ✅ 서버 로그에 비밀번호(다른 계정) 원문이 없다
- ✅ 서버 로그에 새 비밀번호 원문이 없다
- ✅ 서버 로그에 비밀키 원문이 없다
- ✅ 서버 로그에 세션·CSRF 쿠키 값이 없다
- ✅ 작업 폴더 어디에도 이번 비밀키 원문이 없다
- ✅ 작업 폴더 어디에도 테스트 비밀번호 원문이 없다
- ✅ 소스에 비밀키를 문자열로 박아 둔 곳이 없다
- ✅ Git 기록 전체에 이번 비밀키·테스트 비밀번호 원문이 없다
- ✅ Git 기록 전체에 비밀키를 문자열로 박은 줄이 없다
- ✅ DB 파일(.sqlite3)과 .env가 Git에 올라가 있지 않다

## 요약
통과 63 / 63
