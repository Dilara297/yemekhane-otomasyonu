from django.db import connections
from django.utils import timezone
from .models import (
    Kullanicilar, Menuler, MenuYemekleri, YemekAlerjenleri,
    BakiyeHareketleri, Degerlendirmeler, Alerjenler
)


# -------------------------------------------------------------------------
# KULLANICI VE ALERJEN İŞLEMLERİ
# -------------------------------------------------------------------------

def kullanici_getir_eposta(eposta):
    """E-posta adresine göre kullanıcıyı getirir (router üzerinden replikadan okur)."""
    return Kullanicilar.objects.get(eposta=eposta)


def kullanici_alerjen_haritasi_getir(kullanici_id):
    """Kullanıcının profilinde seçtiği alerjenleri {id: ad} sözlüğü olarak replikadan okur."""
    with connections['replica'].cursor() as cursor:
        cursor.execute("""
            SELECT a.id, a.ad
            FROM kullanici_alerjenleri ka
            JOIN alerjenler a ON a.id = ka.alerjen_id
            WHERE ka.kullanici_id = %s
        """, [kullanici_id])
        return {row[0]: row[1] for row in cursor.fetchall()}


def tum_alerjenleri_getir():
    """Sistemdeki tüm alerjenleri ID sırasıyla döner."""
    return list(Alerjenler.objects.all().order_by('id').values('id', 'ad'))


def kullanici_alerjen_idleri_getir(kullanici_id):
    """Kullanıcının seçtiği alerjen ID'lerini replikadan liste olarak döner."""
    with connections['replica'].cursor() as cursor:
        cursor.execute(
            "SELECT alerjen_id FROM kullanici_alerjenleri WHERE kullanici_id = %s",
            [kullanici_id]
        )
        return [row[0] for row in cursor.fetchall()]


def kullanici_alerjenlerini_guncelle(kullanici_id, alerjen_idler):
    """Kullanıcının alerjen tercihlerini kaynak (default) veritabanında günceller."""
    with connections['default'].cursor() as cursor:
        cursor.execute(
            "DELETE FROM kullanici_alerjenleri WHERE kullanici_id = %s",
            [kullanici_id]
        )
        for aid in alerjen_idler:
            cursor.execute(
                "INSERT INTO kullanici_alerjenleri (kullanici_id, alerjen_id) VALUES (%s, %s)",
                [kullanici_id, int(aid)]
            )


# -------------------------------------------------------------------------
# MENÜ İŞLEMLERİ
# -------------------------------------------------------------------------

def gunun_menusu_getir(yemekhane_id, tarih, ogun_id):
    """Belirtilen yemekhane, tarih ve öğün için menü ve yemek detaylarını döner."""
    menu = Menuler.objects.get(yemekhane_id=yemekhane_id, tarih=tarih, ogun_id=ogun_id)

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

    return {
        'menu_id': menu.id,
        'ogun_id': int(menu.ogun_id),
        'ogrenci_fiyati': float(menu.ogrenci_fiyati),
        'personel_fiyati': float(menu.personel_fiyati),
        'toplam_kalori': toplam_kalori,
        'yemekler': yemekler_listesi
    }


def haftalik_menu_getir(yemekhane_id, baslangic, bitis):
    """Haftalık menüleri doluluk ve son saat bilgisiyle replikadan okur."""
    with connections['replica'].cursor() as cursor:
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

    return [{
        'menu_id': satir[0],
        'tarih': satir[1],
        'ogun': satir[2],
        'ogrenci_fiyati': satir[3],
        'personel_fiyati': satir[4],
        'bos_yer': satir[5],
        'rezervasyon_son': satir[6],
        'ogun_id': satir[7]
    } for satir in satirlar]


# -------------------------------------------------------------------------
# REZERVASYON VE BAKİYE İŞLEMLERİ (STORED PROCEDURE)
# -------------------------------------------------------------------------

def sp_rezervasyon_yap_cagir(kullanici_id, menu_id, porsiyon):
    """Kaynak sunucuda sp_rezervasyon_yap prosedürünü çağırır."""
    with connections['default'].cursor() as cursor:
        cursor.execute("CALL sp_rezervasyon_yap(%s, %s, %s)", [kullanici_id, menu_id, porsiyon])
        return cursor.fetchone()  # rezervasyon_id, ucret, porsiyon, bakiye


def sp_rezervasyon_iptal_cagir(kullanici_id, rezervasyon_id):
    """Kaynak sunucuda sp_rezervasyon_iptal prosedürünü çağırır."""
    with connections['default'].cursor() as cursor:
        cursor.execute("CALL sp_rezervasyon_iptal(%s, %s)", [kullanici_id, rezervasyon_id])
        return cursor.fetchone()  # rezervasyon_id, iade, bakiye


def kullanici_rezervasyonlari_getir(kullanici_id):
    """Kullanıcının geçmiş ve aktif rezervasyonlarını replikadan okur."""
    with connections['replica'].cursor() as cursor:
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

    return [{
        'rezervasyon_id': satir[0],
        'durum': satir[1],
        'ucret': satir[2],
        'tarih': satir[3],
        'ogun': satir[4],
        'rezervasyon_son': satir[5],
        'porsiyon': satir[6]
    } for satir in satirlar]


def sp_bakiye_yukle_cagir(kullanici_id, tutar):
    """Kaynak sunucuda sp_bakiye_yukle prosedürünü çağırır."""
    with connections['default'].cursor() as cursor:
        cursor.execute("CALL sp_bakiye_yukle(%s, %s)", [kullanici_id, tutar])
        return cursor.fetchone()  # hareket_id, bakiye


def bakiye_gecmisi_getir(kullanici_id):
    """Kullanıcının bakiye hareketlerini tarihe göre azalan sırada döner."""
    hareketler = BakiyeHareketleri.objects.filter(kullanici_id=kullanici_id).order_by('-olusturma')
    return [{
        'tutar': h.tutar,
        'tur': h.tur,
        'aciklama': h.aciklama,
        'tarih': h.olusturma
    } for h in hareketler]


# -------------------------------------------------------------------------
# DEĞERLENDİRME VE YÖNETİCİ PANELİ İŞLEMLERİ
# -------------------------------------------------------------------------

def menu_kullanildi_mi(kullanici_id, menu_id):
    """Kullanıcının ilgili menüyü gerçekten tüketip tüketmediğini replikadan kontrol eder."""
    with connections['replica'].cursor() as cursor:
        cursor.execute("""
            SELECT durum FROM rezervasyonlar
            WHERE kullanici_id = %s AND menu_id = %s AND durum = 'kullanildi'
        """, [kullanici_id, menu_id])
        return cursor.fetchone() is not None


def degerlendirme_olustur(kullanici_id, menu_id, puan, yorum):
    """Yeni menü değerlendirmesini kaydeder."""
    Degerlendirmeler.objects.create(
        kullanici_id=kullanici_id,
        menu_id=menu_id,
        puan=puan,
        yorum=yorum,
        olusturma=timezone.now()
    )


def yonetici_menu_ozeti_getir():
    """Tüm menülerin doluluk ve ortalama puan özetini replikadan okur."""
    with connections['replica'].cursor() as cursor:
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

    return [{
        'menu_id': s[0],
        'tarih': s[1],
        'ogun': s[2],
        'bos_yer': s[3],
        'ortalama_puan': float(s[4])
    } for s in satirlar]


def menu_olustur(yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati):
    """Kaynak sunucuda yeni bir menü kaydı oluşturur."""
    with connections['default'].cursor() as cursor:
        sorgu = """
            INSERT INTO menuler (yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(sorgu, [yemekhane_id, tarih, ogun_id, ogrenci_fiyati, personel_fiyati])


def menu_guncelle(menu_id, ogrenci_fiyati, personel_fiyati):
    """Mevcut menünün fiyatlarını günceller ve güncellenen menü nesnesini döner."""
    menu = Menuler.objects.get(id=menu_id)
    menu.ogrenci_fiyati = ogrenci_fiyati
    menu.personel_fiyati = personel_fiyati
    menu.guncelleme = timezone.now()
    menu.save()
    return menu