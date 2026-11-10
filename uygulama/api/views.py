import bcrypt
import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Kullanicilar
from .serializers import KullaniciSerializer
from django.db import connections, utils

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
        
from .models import Menuler, MenuYemekleri, YemekAlerjenleri

class GununMenusuView(APIView):
    def get(self, request):
        yemekhane_id = request.query_params.get('yemekhane_id')
        tarih = request.query_params.get('tarih')
        ogun_id = request.query_params.get('ogun_id')

        if not all([yemekhane_id, tarih, ogun_id]):
            return Response({'hata': 'yemekhane_id, tarih ve ogun_id parametreleri gerekli.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Okuma işlemi: replika veritabanından çekilir (db_router sayesinde otomatik)
            menu = Menuler.objects.get(
                yemekhane_id=yemekhane_id, tarih=tarih, ogun_id=ogun_id
            )
        except Menuler.DoesNotExist:
            return Response({'hata': 'Bu kriterlere uygun menü bulunamadı.'}, status=status.HTTP_404_NOT_FOUND)

        toplam_kalori = 0
        yemekler_listesi = []

        # Menüye ait yemekleri ve kategorilerini al
        menu_yemekleri = MenuYemekleri.objects.filter(menu=menu).select_related('yemek__kategori')
        
        for my in menu_yemekleri:
            yemek = my.yemek
            
            # Yemeğin alerjenlerini al
            alerjenler = YemekAlerjenleri.objects.filter(yemek=yemek).select_related('alerjen')
            alerjen_isimleri = [a.alerjen.ad for a in alerjenler]

            # Toplam kaloriyi uygulamada topla kuralı
            toplam_kalori += yemek.kalori 
            
            yemekler_listesi.append({
                'yemek_ad': yemek.ad,
                'kategori': yemek.kategori.ad,
                'kategori_sira': yemek.kategori.sira,
                'kalori': yemek.kalori,
                'vejetaryen': bool(yemek.vejetaryen),
                'alerjenler': alerjen_isimleri
            })
        
        # Yemekleri PDF'teki gibi kategori_sira ve isme göre sırala
        yemekler_listesi.sort(key=lambda x: (x['kategori_sira'], x['yemek_ad']))

        return Response({
            'menu_id': menu.id,
            'ogrenci_fiyati': menu.ogrenci_fiyati,
            'personel_fiyati': menu.personel_fiyati,
            'toplam_kalori': toplam_kalori,
            'yemekler': yemekler_listesi
        })
        
class RezervasyonYapView(APIView):
    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        menu_id = request.data.get('menu_id')
        
        if not kullanici_id or not menu_id:
            return Response({'hata': 'kullanici_id ve menu_id gereklidir.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Yazma işlemi: connections['default'] üzerinden kaynağa gider
            with connections['default'].cursor() as cursor:
                cursor.execute("CALL sp_rezervasyon_yap(%s, %s)", [kullanici_id, menu_id])
                row = cursor.fetchone() # sp'den dönen: rezervasyon_id, ucret, bakiye
                
            return Response({
                'mesaj': 'Rezervasyon başarılı.',
                'rezervasyon_id': row[0],
                'kesilen_ucret': row[1],
                'guncel_bakiye': row[2]
            })
        except utils.OperationalError as e:
            hata_kodu = e.args[0]
            hata_mesaji = e.args[1] if len(e.args) > 1 else str(e)
            
            # 1644: SQLSTATE 45000 için MySQL hata kodu
            if hata_kodu == 1644:
                return Response({'hata': hata_mesaji}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'hata': 'Veritabanı hatası oluştu.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RezervasyonIptalView(APIView):
    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        rezervasyon_id = request.data.get('rezervasyon_id')
        
        if not kullanici_id or not rezervasyon_id:
            return Response({'hata': 'kullanici_id ve rezervasyon_id gereklidir.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            with connections['default'].cursor() as cursor:
                cursor.execute("CALL sp_rezervasyon_iptal(%s, %s)", [kullanici_id, rezervasyon_id])
                row = cursor.fetchone() # sp'den dönen: rezervasyon_id, iade, bakiye
                
            return Response({
                'mesaj': 'İptal başarılı.',
                'rezervasyon_id': row[0],
                'iade_edilen': row[1],
                'guncel_bakiye': row[2]
            })
        except utils.OperationalError as e:
            hata_kodu = e.args[0]
            if hata_kodu == 1644:
                return Response({'hata': e.args[1]}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'hata': 'Veritabanı hatası oluştu.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
class HaftalikMenuView(APIView):
    def get(self, request):
        yemekhane_id = request.query_params.get('yemekhane_id')
        baslangic = request.query_params.get('baslangic') # YYYY-MM-DD
        bitis = request.query_params.get('bitis')

        if not all([yemekhane_id, baslangic, bitis]):
            return Response({'hata': 'yemekhane_id, baslangic ve bitis gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        # Okuma işlemi (replica üzerinden)
        with connections['replica'].cursor() as cursor:
            # v_menu_doluluk view'ını kullanarak boş yer ve son saati alıyoruz
            sorgu = """
                SELECT m.id, m.tarih, o.ad as ogun, m.ogrenci_fiyati, m.personel_fiyati,
                       v.bos_yer, v.rezervasyon_son
                FROM menuler m
                JOIN ogunler o ON m.ogun_id = o.id
                JOIN v_menu_doluluk v ON m.id = v.menu_id
                WHERE m.yemekhane_id = %s AND m.tarih BETWEEN %s AND %s
                ORDER BY m.tarih, o.sira
            """
            cursor.execute(sorgu, [yemekhane_id, baslangic, bitis])
            satirlar = cursor.fetchall()

        sonuc = []
        for satir in satirlar:
            sonuc.append({
                'menu_id': satir[0],
                'tarih': satir[1],
                'ogun': satir[2],
                'ogrenci_fiyati': satir[3],
                'personel_fiyati': satir[4],
                'bos_yer': satir[5],
                'rezervasyon_son': satir[6]
            })

        return Response(sonuc)

class RezervasyonlarimView(APIView):
    def get(self, request):
        kullanici_id = request.query_params.get('kullanici_id')
        
        if not kullanici_id:
            return Response({'hata': 'kullanici_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        with connections['replica'].cursor() as cursor:
            # Aktif, kullanıldı, iptal durumları ve iptal süresi (rezervasyon_son) bilgisi
            sorgu = """
                SELECT r.id, r.durum, r.ucret, m.tarih, o.ad as ogun, v.rezervasyon_son
                FROM rezervasyonlar r
                JOIN menuler m ON r.menu_id = m.id
                JOIN ogunler o ON m.ogun_id = o.id
                JOIN v_menu_doluluk v ON m.id = v.menu_id
                WHERE r.kullanici_id = %s
                ORDER BY m.tarih DESC, o.sira DESC
            """
            cursor.execute(sorgu, [kullanici_id])
            satirlar = cursor.fetchall()

        sonuc = []
        for satir in satirlar:
            sonuc.append({
                'rezervasyon_id': satir[0],
                'durum': satir[1],
                'ucret': satir[2],
                'tarih': satir[3],
                'ogun': satir[4],
                'rezervasyon_son': satir[5]
            })

        return Response(sonuc)