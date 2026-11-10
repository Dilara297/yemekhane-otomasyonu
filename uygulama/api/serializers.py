from rest_framework import serializers
from .models import Kullanicilar, Menuler, Yemekler, BakiyeHareketleri, Rezervasyonlar, Yemekhaneler, Ogunler

class KullaniciSerializer(serializers.ModelSerializer):
    class Meta:
        model = Kullanicilar
        fields = ['id', 'ad', 'soyad', 'eposta', 'rol', 'bakiye']

class YemekhaneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Yemekhaneler
        fields = '__all__'

class OgunSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ogunler
        fields = '__all__'

class YemekSerializer(serializers.ModelSerializer):
    class Meta:
        model = Yemekler
        fields = '__all__'

class BakiyeHareketSerializer(serializers.ModelSerializer):
    class Meta:
        model = BakiyeHareketleri
        fields = '__all__'

class RezervasyonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rezervasyonlar
        fields = '__all__'