from django.urls import path
from .views import LoginView, GununMenusuView, LogoutView, ProfilAlerjenView, RezervasyonYapView, RezervasyonIptalView, HaftalikMenuView, RezervasyonlarimView,BakiyeYukleView,BakiyeGecmisiView,DegerlendirmeYapView,YoneticiPaneliView

urlpatterns = [
    path('giris/', LoginView.as_view(), name='giris'),
    path('menu/', GununMenusuView.as_view(), name='gunun_menusu'),
    path('menu/haftalik/', HaftalikMenuView.as_view(), name='haftalik_menu'),
    path('rezervasyon/yap/', RezervasyonYapView.as_view(), name='rezervasyon_yap'),
    path('rezervasyon/iptal/', RezervasyonIptalView.as_view(), name='rezervasyon_iptal'),
    path('rezervasyonlarim/', RezervasyonlarimView.as_view(), name='rezervasyonlarim'),
    path('bakiye/yukle/', BakiyeYukleView.as_view(), name='bakiye_yukle'),
    path('bakiye/gecmis/', BakiyeGecmisiView.as_view(), name='bakiye_gecmis'),
    path('degerlendirme/', DegerlendirmeYapView.as_view(), name='degerlendirme'),
    path('yonetici/menu/', YoneticiPaneliView.as_view(), name='yonetici_menu'),
    path('cikis/', LogoutView.as_view(), name='cikis'),    path('profil/alerjenler/', ProfilAlerjenView.as_view(), name='profil_alerjenler'),
]