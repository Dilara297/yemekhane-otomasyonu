import bcrypt
import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Kullanicilar
from .serializers import KullaniciSerializer

class LoginView(APIView):
    def post(self, request):
        eposta = request.data.get('eposta')
        sifre = request.data.get('sifre')
        
        if not eposta or not sifre:
            return Response({'hata': 'E-posta ve şifre zorunludur.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Veritabanından kullanıcıyı çek (db_router otomatik okuma sunucusuna yönlendirir)
            kullanici = Kullanicilar.objects.get(eposta=eposta)
        except Kullanicilar.DoesNotExist:
            return Response({'hata': 'Kullanıcı bulunamadı.'}, status=status.HTTP_404_NOT_FOUND)
            
        # Şifre eşleşiyorsa (Yemek2026!)
        if bcrypt.checkpw(sifre.encode('utf-8'), kullanici.sifre_hash.encode('utf-8')):
            serializer = KullaniciSerializer(kullanici)
            token = str(uuid.uuid4()) # Aşama 3'te bu token'ı Redis'e yazacağız
            return Response({
                'mesaj': 'Giriş başarılı',
                'kullanici': serializer.data,
                'token': token
            })
        else:
            return Response({'hata': 'Hatalı şifre.'}, status=status.HTTP_401_UNAUTHORIZED)