from django.db import models


class Alerjenler(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    ad = models.CharField(unique=True, max_length=40)

    class Meta:
        managed = False
        db_table = 'alerjenler'


class BakiyeHareketleri(models.Model):
    kullanici = models.ForeignKey('Kullanicilar', models.DO_NOTHING)
    tur = models.CharField(max_length=11)
    tutar = models.DecimalField(max_digits=10, decimal_places=2)
    rezervasyon = models.ForeignKey('Rezervasyonlar', models.DO_NOTHING, blank=True, null=True)
    aciklama = models.CharField(max_length=150, blank=True, null=True)
    olusturma = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'bakiye_hareketleri'


class Degerlendirmeler(models.Model):
    kullanici = models.ForeignKey('Kullanicilar', models.DO_NOTHING)
    menu = models.ForeignKey('Menuler', models.DO_NOTHING)
    puan = models.PositiveIntegerField()
    yorum = models.CharField(max_length=500, blank=True, null=True)
    olusturma = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'degerlendirmeler'
        unique_together = (('kullanici', 'menu'),)


class Kullanicilar(models.Model):
    ad = models.CharField(max_length=50)
    soyad = models.CharField(max_length=50)
    eposta = models.CharField(unique=True, max_length=120)
    sifre_hash = models.CharField(max_length=60, db_comment='bcrypt')
    rol = models.CharField(max_length=8)
    ogrenci_no = models.CharField(unique=True, max_length=12, blank=True, null=True)
    bakiye = models.DecimalField(max_digits=10, decimal_places=2)
    aktif = models.IntegerField()
    olusturma = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'kullanicilar'


class MenuYemekleri(models.Model):
    pk = models.CompositePrimaryKey('menu_id', 'yemek_id')
    menu = models.ForeignKey('Menuler', models.DB_CASCADE)
    yemek = models.ForeignKey('Yemekler', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'menu_yemekleri'


class Menuler(models.Model):
    yemekhane = models.ForeignKey('Yemekhaneler', models.DO_NOTHING)
    tarih = models.DateField()
    ogun = models.ForeignKey('Ogunler', models.DO_NOTHING)
    ogrenci_fiyati = models.DecimalField(max_digits=8, decimal_places=2)
    personel_fiyati = models.DecimalField(max_digits=8, decimal_places=2)
    olusturma = models.DateTimeField()
    guncelleme = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'menuler'
        unique_together = (('yemekhane', 'tarih', 'ogun'),)


class Ogunler(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    ad = models.CharField(unique=True, max_length=20)
    sira = models.PositiveIntegerField()
    son_saat = models.TimeField()
    servis_baslangic = models.TimeField()
    servis_bitis = models.TimeField()

    class Meta:
        managed = False
        db_table = 'ogunler'


class Rezervasyonlar(models.Model):
    kullanici = models.ForeignKey(Kullanicilar, models.DO_NOTHING)
    menu = models.ForeignKey(Menuler, models.DO_NOTHING)
    durum = models.CharField(max_length=10)
    porsiyon = models.CharField(max_length=5, default='tam')
    ucret = models.DecimalField(max_digits=8, decimal_places=2)
    olusturma = models.DateTimeField()
    kullanma_zamani = models.DateTimeField(blank=True, null=True)
    iptal_zamani = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'rezervasyonlar'
        unique_together = (('kullanici', 'menu'),)
        
class KullaniciAlerjenleri(models.Model):
    pk = models.CompositePrimaryKey('kullanici_id', 'alerjen_id')
    kullanici = models.ForeignKey(Kullanicilar, models.DB_CASCADE)
    alerjen = models.ForeignKey(Alerjenler, models.DB_CASCADE)

    class Meta:
        managed = False
        db_table = 'kullanici_alerjenleri'


class YemekAlerjenleri(models.Model):
    pk = models.CompositePrimaryKey('yemek_id', 'alerjen_id')
    yemek = models.ForeignKey('Yemekler', models.DB_CASCADE)
    alerjen = models.ForeignKey(Alerjenler, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'yemek_alerjenleri'


class YemekKategorileri(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    ad = models.CharField(unique=True, max_length=40)
    sira = models.PositiveIntegerField()

    class Meta:
        managed = False
        db_table = 'yemek_kategorileri'


class Yemekhaneler(models.Model):
    ad = models.CharField(unique=True, max_length=60)
    konum = models.CharField(max_length=120, blank=True, null=True)
    kapasite = models.PositiveSmallIntegerField()

    class Meta:
        managed = False
        db_table = 'yemekhaneler'


class Yemekler(models.Model):
    id = models.SmallAutoField(primary_key=True)
    kategori = models.ForeignKey(YemekKategorileri, models.DO_NOTHING)
    ad = models.CharField(unique=True, max_length=80)
    kalori = models.PositiveSmallIntegerField(db_comment='porsiyon ba��na kcal')
    vejetaryen = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'yemekler'
