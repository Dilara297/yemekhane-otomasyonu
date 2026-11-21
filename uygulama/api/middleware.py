from django_redis import get_redis_connection

class RedisOturumYenileMiddleware:
    """Her istekte Authorization: Bearer <token> varsa Redis oturum süresini 30 dk (1800 sn) yeniler."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1].strip()
            if token:
                redis_conn = get_redis_connection("default")
                anahtar = f"oturum:{token}"
                if redis_conn.exists(anahtar):
                    redis_conn.expire(anahtar, 1800)

        return self.get_response(request)