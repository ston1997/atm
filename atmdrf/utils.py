import requests

from django.http import Http404
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .serializers import *


def get_currency_rate():
    exchange_rate_json = requests.get(
        'https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5'
    ).json()
    usd_buy = exchange_rate_json[0]['buy']
    usd_sale = exchange_rate_json[0]['sale']
    eur_buy = exchange_rate_json[1]['buy']
    eur_sale = exchange_rate_json[1]['sale']
    rates = {
        'usd_buy': usd_buy,
        'usd_sale': usd_sale,
        'eur_buy': eur_buy,
        'eur_sale': eur_sale
    }
    return rates


class TransactionPagination(PageNumberPagination):
    page_size = 10


class ViewSetMixin:
    @staticmethod
    def put_mixin(request, serializer_class, field):
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = Card.objects.get(card_number=serializer.data.get(field))
        if instance.user == request.user:
            result = serializer.update(instance, serializer.validated_data)
            return Response({'result': result})
        raise Http404
