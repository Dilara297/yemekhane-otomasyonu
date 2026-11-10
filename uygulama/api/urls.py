from django.urls import path
from .views import LoginView, GununMenusuView, RezervasyonYapView, RezervasyonIptalView, HaftalikMenuView, RezervasyonlarimView

urlpatterns = [
    path('giris/', LoginView.as_view(), name='giris'),
    path('menu/', GununMenusuView.as_view(), name='gunun_menusu'),
    path('menu/haftalik/', HaftalikMenuView.as_view(), name='haftalik_menu'),
    path('rezervasyon/yap/', RezervasyonYapView.as_view(), name='rezervasyon_yap'),
    path('rezervasyon/iptal/', RezervasyonIptalView.as_view(), name='rezervasyon_iptal'),
    path('rezervasyonlarim/', RezervasyonlarimView.as_view(), name='rezervasyonlarim'),
]