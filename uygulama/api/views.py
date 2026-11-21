import bcrypt
import uuid
import json
import datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import  Kullanicilar, Menuler, MenuYemekleri, YemekAlerjenleri, BakiyeHareketleri, Degerlendirmeler,Alerjenler
from .serializers import KullaniciSerializer
from django.db import connections, utils
from django.utils import timezone
from django.db.models import Avg

from django_redis import get_redis_connection

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
            # Veritabanından kullanıcıyı çek (db_router otomatik okuma sunucusuna yönlendirir)
            kullanici = Kullanicilar.objects.get(eposta=eposta)
        except Kullanicilar.DoesNotExist:
            return Response({'hata': 'Kullanıcı bulunamadı.'}, status=status.HTTP_404_NOT_FOUND)
            
        # Şifre eşleşiyorsa
        if bcrypt.checkpw(sifre.encode('utf-8'), kullanici.sifre_hash.encode('utf-8')):
            serializer = KullaniciSerializer(kullanici)
            token = str(uuid.uuid4())
            
            # Doğrudan Redis'e ham (raw) bağlantı kuruyoruz
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
        # AŞAMA 4: Kullanıcıya özel alerjen uyarısı için kullanici_id alınır
        kullanici_id = request.query_params.get('kullanici_id') or (request.user.id if request.user and request.user.is_authenticated else None)

        if not all([yemekhane_id, tarih, ogun_id]):
            return Response({'hata': 'yemekhane_id, tarih ve ogun_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. KURAL: Redis Anahtar Formatı
        redis_anahtari = f"menu:{yemekhane_id}:{tarih}:{ogun_id}"
        redis_conn = get_redis_connection("default")

        # Önce Redis'te bu menü var mı diye bakıyoruz
        onbellek_veri = redis_conn.get(redis_anahtari)

        if onbellek_veri:
            # 3. KURAL: İkinci istek Redis'ten geliyor logu
            print(f"LOG: [{redis_anahtari}] verisi REDIS'TEN (Önbellek) getirildi.", flush=True)
            sonuc_dict = json.loads(onbellek_veri)
        else:
            # Redis'te yoksa Veritabanından (Replica) çek ve logla
            print(f"LOG: [{redis_anahtari}] verisi VERITABANINDAN çekildi ve Redis'e yazılacak.", flush=True)

            try:
                menu = Menuler.objects.get(yemekhane_id=yemekhane_id, tarih=tarih, ogun_id=ogun_id)
            except Menuler.DoesNotExist:
                return Response({'hata': 'Bu kriterlere uygun menü bulunamadı.'}, status=status.HTTP_404_NOT_FOUND)

            toplam_kalori = 0
            yemekler_listesi = []
            menu_yemekleri = MenuYemekleri.objects.filter(menu=menu).select_related('yemek__kategori')
            
            for my in menu_yemekleri:
                yemek = my.yemek
                alerjenler = YemekAlerjenleri.objects.filter(yemek=yemek).select_related('alerjen')
                alerjen_isimleri = [a.alerjen.ad for a in alerjenler]
                alerjen_idler = [a.alerjen.id for a in alerjenler]
                toplam_kalori += yemek.kalori 
                
                yemekler_listesi.append({
                    'yemek_ad': yemek.ad,
                    'kategori': yemek.kategori.ad,
                    'kategori_sira': yemek.kategori.sira,
                    'kalori': yemek.kalori,
                    'vejetaryen': bool(yemek.vejetaryen),
                    'alerjenler': alerjen_isimleri,
                    'alerjen_idler': alerjen_idler
                })
            
            yemekler_listesi.sort(key=lambda x: (x['kategori_sira'], x['yemek_ad']))

            sonuc_dict = {
                'menu_id': menu.id,
                'ogun_id': int(menu.ogun_id),
                'ogrenci_fiyati': float(menu.ogrenci_fiyati),
                'personel_fiyati': float(menu.personel_fiyati),
                'toplam_kalori': toplam_kalori,
                'yemekler': yemekler_listesi
            }

            # 2. KURAL: Gün sonuna kadar (gece yarısına kadar) saniye hesabı
            suan = datetime.datetime.now()
            yarin = suan + datetime.timedelta(days=1)
            gece_yarisi = datetime.datetime(yarin.year, yarin.month, yarin.day, 0, 0, 0)
            kalan_saniye = int((gece_yarisi - suan).total_seconds())

            # Veriyi JSON'a çevirip Redis'e gün sonu (TTL) süresiyle yazıyoruz
            redis_conn.set(redis_anahtari, json.dumps(sonuc_dict), ex=kalan_saniye)

        # AŞAMA 4: Kullanıcının seçtiği alerjenleri replikadan çekip yemeklerle eşleştiriyoruz
        kullanici_alerjen_map = {}
        if kullanici_id:
            with connections['replica'].cursor() as cursor:
                cursor.execute("""
                    SELECT a.id, a.ad
                    FROM kullanici_alerjenleri ka
                    JOIN alerjenler a ON a.id = ka.alerjen_id
                    WHERE ka.kullanici_id = %s
                """, [kullanici_id])
                kullanici_alerjen_map = {row[0]: row[1] for row in cursor.fetchall()}

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
            # Yazma işlemi: connections['default'] üzerinden kaynağa gider
            with connections['default'].cursor() as cursor:
                cursor.execute("CALL sp_rezervasyon_yap(%s, %s, %s)", [kullanici_id, menu_id, porsiyon])
                row = cursor.fetchone() # sp'den dönen: rezervasyon_id, ucret, porsiyon, bakiye
                
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
                       v.bos_yer, v.rezervasyon_son, m.ogun_id
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
                'rezervasyon_son': satir[6],
                'ogun_id': satir[7]
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
                SELECT r.id, r.durum, r.ucret, m.tarih, o.ad as ogun, v.rezervasyon_son, r.porsiyon
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
                'rezervasyon_son': satir[5],
                'porsiyon': satir[6]
            })

        return Response(sonuc)
    
class BakiyeYukleView(APIView):
    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        tutar = request.data.get('tutar')

        if not kullanici_id or not tutar:
            return Response({'hata': 'kullanici_id ve tutar gereklidir.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with connections['default'].cursor() as cursor:
                cursor.execute("CALL sp_bakiye_yukle(%s, %s)", [kullanici_id, tutar])
                row = cursor.fetchone()
                
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

        hareketler = BakiyeHareketleri.objects.filter(kullanici_id=kullanici_id).order_by('-olusturma')
        data = [{
            'tutar': h.tutar,
            'tur': h.tur,
            'aciklama': h.aciklama,
            'tarih': h.olusturma
        } for h in hareketler]
        
        return Response(data)

class DegerlendirmeYapView(APIView):
    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        menu_id = request.data.get('menu_id')
        puan = request.data.get('puan')
        yorum = request.data.get('yorum', '')

        if not all([kullanici_id, menu_id, puan]):
            return Response({'hata': 'Eksik parametre gönderildi.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Kural: Kullanıcı bu menüyü gerçekten tüketmiş mi?
        with connections['replica'].cursor() as cursor:
            cursor.execute("""
                SELECT durum FROM rezervasyonlar 
                WHERE kullanici_id = %s AND menu_id = %s AND durum = 'kullanildi'
            """, [kullanici_id, menu_id])
            kullanildi_mi = cursor.fetchone()

        if not kullanildi_mi:
            return Response({'hata': 'Sadece kullandığınız (tükettiğiniz) menüleri değerlendirebilirsiniz.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            Degerlendirmeler.objects.create(
                kullanici_id=kullanici_id,
                menu_id=menu_id,
                puan=puan,
                yorum=yorum,
                olusturma=timezone.now()
            )
            return Response({'mesaj': 'Değerlendirmeniz başarıyla kaydedildi.'})
        except Exception as e:
            return Response({'hata': f'Hata Detayı: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        
class YoneticiPaneliView(APIView):
    # Menü doluluk ve ortalama puan listeleme
    def get(self, request):
        with connections['replica'].cursor() as cursor:
            # v_menu_doluluk ve degerlendirmeler birleştirilir
            sorgu = """
                SELECT m.id, m.tarih, o.ad as ogun, v.bos_yer, 
                       IFNULL(AVG(d.puan), 0) as ortalama_puan
                FROM menuler m
                JOIN ogunler o ON m.ogun_id = o.id
                LEFT JOIN v_menu_doluluk v ON m.id = v.menu_id
                LEFT JOIN degerlendirmeler d ON m.id = d.menu_id
                GROUP BY m.id, m.tarih, o.ad, v.bos_yer
                ORDER BY m.tarih DESC
            """
            cursor.execute(sorgu)
            satirlar = cursor.fetchall()
            
        data = [{
            'menu_id': s[0], 'tarih': s[1], 'ogun': s[2], 
            'bos_yer': s[3], 'ortalama_puan': float(s[4])
        } for s in satirlar]
        return Response(data)

    # Menü oluşturma 
    def post(self, request):
        yemekhane_id = request.data.get('yemekhane_id')
        tarih = request.data.get('tarih')
        ogun_id = request.data.get('ogun_id')
        ogrenci_fiyati = request.data.get('ogrenci_fiyati')
        personel_fiyati = request.data.get('personel_fiyati')

        if not all([yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati]):
            return Response({'hata': 'Eksik bilgi.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with connections['default'].cursor() as cursor:
                sorgu = """
                    INSERT INTO menuler (yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sorgu, [yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati])
                
            return Response({'mesaj': 'Menü başarıyla oluşturuldu.'})
        except Exception as e:
            return Response({'hata': f'Sunucu hatası: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Menü düzenleme/güncelleme
    def put(self, request):
        menu_id = request.data.get('menu_id')
        ogrenci_fiyati = request.data.get('ogrenci_fiyati')
        personel_fiyati = request.data.get('personel_fiyati')

        if not all([menu_id, ogrenci_fiyati, personel_fiyati]):
            return Response({'hata': 'Eksik bilgi.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            menu = Menuler.objects.get(id=menu_id)
            menu.ogrenci_fiyati = ogrenci_fiyati
            menu.personel_fiyati = personel_fiyati
            menu.guncelleme = timezone.now()
            menu.save()
            
            from django_redis import get_redis_connection
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
    # Tüm alerjenleri ve kullanıcının mevcut seçimlerini replica üzerinden getirir
    def get(self, request):
        kullanici_id = request.query_params.get('kullanici_id')
        if not kullanici_id:
            return Response({'hata': 'kullanici_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        tum_alerjenler = list(Alerjenler.objects.all().order_by('id').values('id', 'ad'))
        
        with connections['replica'].cursor() as cursor:
            cursor.execute("SELECT alerjen_id FROM kullanici_alerjenleri WHERE kullanici_id = %s", [kullanici_id])
            secili_idler = [row[0] for row in cursor.fetchall()]

        return Response({
            'tum_alerjenler': tum_alerjenler,
            'secili_alerjenler': secili_idler
        })

    # Kullanıcının alerjen tercihlerini kaynak (default) veritabanında günceller
    def post(self, request):
        kullanici_id = request.data.get('kullanici_id')
        alerjen_idler = request.data.get('alerjen_idler', [])

        if not kullanici_id:
            return Response({'hata': 'kullanici_id gerekli.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with connections['default'].cursor() as cursor:
                cursor.execute("DELETE FROM kullanici_alerjenleri WHERE kullanici_id = %s", [kullanici_id])
                for aid in alerjen_idler:
                    cursor.execute(
                        "INSERT INTO kullanici_alerjenleri (kullanici_id, alerjen_id) VALUES (%s, %s)",
                        [kullanici_id, int(aid)]
                    )
            return Response({'mesaj': 'Alerjen tercihleriniz güncellendi.'})
        except Exception as e:
            return Response({'hata': f'Güncelleme hatası: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)