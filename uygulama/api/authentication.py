from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django_redis import get_redis_connection
from .models import Kullanicilar

class RedisTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None
        
        try:
            token = auth_header.split(' ')[1]
        except IndexError:
            raise AuthenticationFailed('Geçersiz token formatı.')

        redis_anahtari = f"oturum:{token}"
        redis_conn = get_redis_connection("default")
        
        # Redis'ten ham veriyi çekiyoruz (Byte olarak gelir)
        kullanici_id_bytes = redis_conn.get(redis_anahtari)

        if not kullanici_id_bytes:
            raise AuthenticationFailed('Oturum süresi dolmuş veya geçersiz token.')

        # Byte formatını integer'a çeviriyoruz
        kullanici_id = int(kullanici_id_bytes.decode('utf-8'))

        # KURAL: API'ye gelen her istekte süre 30 dakika yenilenir (expire)
        redis_conn.expire(redis_anahtari, 1800)

        try:
            kullanici = Kullanicilar.objects.get(id=kullanici_id)
        except Kullanicilar.DoesNotExist:
            raise AuthenticationFailed('Kullanıcı bulunamadı.')

        return (kullanici, token)
    
    def authenticate_header(self, request):
        return 'Bearer'