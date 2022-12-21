from django.urls import path, include
from rest_framework import routers

from .views import *

router = routers.SimpleRouter()
router.register(r'user', UserViewSet)
router.register(r'wallet', UserWalletViewSet, basename='wallet')

urlpatterns = [
    path('', include(router.urls)),
    path('', UserIsOwnerViewSet.as_view()),
    path('log/', TransactionListAPIView.as_view()),
    path('register/', UserRegisterAPIView.as_view()),
    path('currency-rate/', CurrencyRate.as_view()),
]
