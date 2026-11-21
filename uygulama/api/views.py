import bcrypt
import uuid
import json
import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import utils
from django_redis import get_redis_connection

from .models import Kullanicilar, Menuler
from .serializers import KullaniciSerializer
from . import repositories as repo


class LoginView(APIView):
    # Giriş işlemi kimlik doğrulama gerektirmediği için boş bırakıyoruz
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        eposta = request.data.get('eposta')
        sifre = request.data.get('sifre')

        if not eposta or not sifre:
            return Response({'hata': 'E-posta ve şifre zorunludur.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            kullanici = repo.kullanici_getir_eposta(eposta)
        except Kullanicilar.DoesNotExist:
            return Response({'hata': 'Kullanıcı bulunamadı.'}, status=status.HTTP_404_NOT_FOUND)

        # Şifre eşleşiyorsa Redis'te 30 dakikalık oturum aç
        if bcrypt.checkpw(sifre.encode('utf-8'), kullanici.sifre_hash.encode('utf-8')):
            serializer = KullaniciSerializer(kullanici)
            token = str(uuid.uuid4())

            redis_conn = get_redis_connection("default")
            redis_conn.set(f"oturum:{token}", kullanici.id, ex=1800)

            return Response({
                'mesaj': 'Giriş başarılı',
                'kullanici': serializer.data,
                'rol': kullanici.rol,
                'token': token
            })
        else:
            return Response({'hata': 'Hatalı şifre.'}, status=status.HTTP_401_UNAUTHORIZED)


class GununMenusuView(APIView):
    def get(self, request):
        yemekhane_id = request.query_params.get('yemekhane_id')
        tarih = request.query_params.get('tarih')
        ogun_id = request.query_params.get('ogun_id')
        kullanici_id = request.query_params.get('kullanici_id') or (
            request.user.id if request.user and request.user.is_authenticated else None
        )

        if not all([yemekhane_id, tarih, ogun_id]):
            return Response({'hata': 'yemekhane_id, tarih ve ogun_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. KURAL: Redis Anahtar Formatı
        redis_anahtari = f"menu:{yemekhane_id}:{tarih}:{ogun_id}"
        redis_conn = get_redis_connection("default")
        onbellek_veri = redis_conn.get(redis_anahtari)

        if onbellek_veri:
            print(f"LOG: [{redis_anahtari}] verisi REDIS'TEN (Önbellek) getirildi.", flush=True)
            sonuc_dict = json.loads(onbellek_veri)
        else:
            print(f"LOG: [{redis_anahtari}] verisi VERITABANINDAN çekildi ve Redis'e yazılacak.", flush=True)
            try:
                sonuc_dict = repo.gunun_menusu_getir(yemekhane_id, tarih, ogun_id)
            except Menuler.DoesNotExist:
                return Response({'hata': 'Bu kriterlere uygun menü bulunamadı.'}, status=status.HTTP_404_NOT_FOUND)

            # 2. KURAL: Gün sonuna kadar (gece yarısına kadar) saniye hesabı
            suan = datetime.datetime.now()
            yarin = suan + datetime.timedelta(days=1)
            gece_yarisi = datetime.datetime(yarin.year, yarin.month, yarin.day, 0, 0, 0)
            kalan_saniye = int((gece_yarisi - suan).total_seconds())

            redis_conn.set(redis_anahtari, json.dumps(sonuc_dict), ex=kalan_saniye)

        # AŞAMA 4: Kullanıcının alerjenleriyle eşleşen yemeklere uyarı eklenir
        kullanici_alerjen_map = repo.kullanici_alerjen_haritasi_getir(kullanici_id) if kullanici_id else {}

        for yemek in sonuc_dict.get('yemekler', []):
            yemek_alerjen_idleri = yemek.get('alerjen_idler', [])
            eslesenler = [kullanici_alerjen_map[aid] for aid in yemek_alerjen_idleri if aid in kullanici_alerjen_map]
            yemek['alerjen_uyarisi'] = len(eslesenler) > 0
            yemek['eslesen_alerjenler'] = eslesenler

        return Response(sonuc_dict)


class RezervasyonYapView(APIView):
    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        menu_id = request.data.get('menu_id')
        porsiyon = request.data.get('porsiyon', 'tam')

        if not kullanici_id or not menu_id:
            return Response({'hata': 'kullanici_id ve menu_id gereklidir.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row = repo.sp_rezervasyon_yap_cagir(kullanici_id, menu_id, porsiyon)
            return Response({
                'mesaj': 'Rezervasyon başarılı.',
                'rezervasyon_id': row[0],
                'kesilen_ucret': row[1],
                'porsiyon': row[2],
                'guncel_bakiye': row[3]
            })
        except utils.OperationalError as e:
            hata_kodu = e.args[0]
            hata_mesaji = e.args[1] if len(e.args) > 1 else str(e)
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
            row = repo.sp_rezervasyon_iptal_cagir(kullanici_id, rezervasyon_id)
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
        baslangic = request.query_params.get('baslangic')
        bitis = request.query_params.get('bitis')

        if not all([yemekhane_id, baslangic, bitis]):
            return Response({'hata': 'yemekhane_id, baslangic ve bitis gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(repo.haftalik_menu_getir(yemekhane_id, baslangic, bitis))


class RezervasyonlarimView(APIView):
    def get(self, request):
        kullanici_id = request.query_params.get('kullanici_id')

        if not kullanici_id:
            return Response({'hata': 'kullanici_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(repo.kullanici_rezervasyonlari_getir(kullanici_id))


class BakiyeYukleView(APIView):
    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        tutar = request.data.get('tutar')

        if not kullanici_id or not tutar:
            return Response({'hata': 'kullanici_id ve tutar gereklidir.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            row = repo.sp_bakiye_yukle_cagir(kullanici_id, tutar)
            return Response({
                'mesaj': 'Bakiye başarıyla yüklendi.',
                'hareket_id': row[0],
                'guncel_bakiye': row[1]
            })
        except utils.OperationalError as e:
            hata_kodu = e.args[0]
            if hata_kodu == 1644:
                return Response({'hata': e.args[1]}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'hata': 'Veritabanı hatası oluştu.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BakiyeGecmisiView(APIView):
    def get(self, request):
        kullanici_id = request.query_params.get('kullanici_id')
        if not kullanici_id:
            return Response({'hata': 'kullanici_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(repo.bakiye_gecmisi_getir(kullanici_id))


class DegerlendirmeYapView(APIView):
    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        menu_id = request.data.get('menu_id')
        puan = request.data.get('puan')
        yorum = request.data.get('yorum', '')

        if not all([kullanici_id, menu_id, puan]):
            return Response({'hata': 'Eksik parametre gönderildi.'}, status=status.HTTP_400_BAD_REQUEST)

        if not repo.menu_kullanildi_mi(kullanici_id, menu_id):
            return Response(
                {'hata': 'Sadece kullandığınız (tükettiğiniz) menüleri değerlendirebilirsiniz.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            repo.degerlendirme_olustur(kullanici_id, menu_id, puan, yorum)
            return Response({'mesaj': 'Değerlendirmeniz başarıyla kaydedildi.'})
        except Exception as e:
            return Response({'hata': f'Hata Detayı: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


class YoneticiPaneliView(APIView):
    def get(self, request):
        return Response(repo.yonetici_menu_ozeti_getir())

    def post(self, request):
        yemekhane_id = request.data.get('yemekhane_id')
        tarih = request.data.get('tarih')
        ogun_id = request.data.get('ogun_id')
        ogrenci_fiyati = request.data.get('ogrenci_fiyati')
        personel_fiyati = request.data.get('personel_fiyati')

        if not all([yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati]):
            return Response({'hata': 'Eksik bilgi.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            repo.menu_olustur(yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati)
            return Response({'mesaj': 'Menü başarıyla oluşturuldu.'})
        except Exception as e:
            return Response({'hata': f'Sunucu hatası: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        menu_id = request.data.get('menu_id')
        ogrenci_fiyati = request.data.get('ogrenci_fiyati')
        personel_fiyati = request.data.get('personel_fiyati')

        if not all([menu_id, ogrenci_fiyati, personel_fiyati]):
            return Response({'hata': 'Eksik bilgi.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            menu = repo.menu_guncelle(menu_id, ogrenci_fiyati, personel_fiyati)

            # Menü güncellendiğinde Redis önbelleğini temizle
            redis_anahtari = f"menu:{menu.yemekhane_id}:{menu.tarih}:{menu.ogun_id}"
            redis_conn = get_redis_connection("default")
            redis_conn.delete(redis_anahtari)

            return Response({'mesaj': 'Menü başarıyla güncellendi.'})
        except Menuler.DoesNotExist:
            return Response({'hata': 'Menü bulunamadı.'}, status=status.HTTP_404_NOT_FOUND)


class LogoutView(APIView):
    def post(self, request):
        auth_header = request.headers.get('Authorization')
        if auth_header:
            try:
                token = auth_header.split(' ')[1]
                redis_conn = get_redis_connection("default")
                redis_conn.delete(f"oturum:{token}")
            except IndexError:
                pass

        return Response({'mesaj': 'Başarıyla çıkış yapıldı.'})


class ProfilAlerjenView(APIView):
    def get(self, request):
        kullanici_id = request.query_params.get('kullanici_id')
        if not kullanici_id:
            return Response({'hata': 'kullanici_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'tum_alerjenler': repo.tum_alerjenleri_getir(),
            'secili_alerjenler': repo.kullanici_alerjen_idleri_getir(kullanici_id)
        })

    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        alerjen_idler = request.data.get('alerjen_idler', [])

        if not kullanici_id:
            return Response({'hata': 'kullanici_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            repo.kullanici_alerjenlerini_guncelle(kullanici_id, alerjen_idler)
            return Response({'mesaj': 'Alerjen tercihleriniz güncellendi.'})
        except Exception as e:
            return Response({'hata': f'Güncelleme hatası: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)