import logging

logger = logging.getLogger("diary.access")


class AccessLogMiddleware:
    """요청 한 줄 기록: 메서드, 경로, 상태코드, 로그인 여부.

    요청 본문(비밀번호가 들어 있음), 쿠키, Authorization 헤더는 읽지도 남기지도 않는다.
    쿼리스트링도 남기지 않는다(주소창에 값이 실려 다니는 일이 없어야 하므로 경로만 기록).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        who = "user" if getattr(request, "user", None) and request.user.is_authenticated else "anon"
        logger.info("%s %s -> %s (%s)", request.method, request.path, response.status_code, who)
        return response
