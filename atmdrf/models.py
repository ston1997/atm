from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.utils.translation import gettext_lazy as _
from django.db import models

from random import randint


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, **extra_fields):
        """
        Создает и сохраняет пользователя с автоматически сгенерированным
        номером карты и используемым в качестве логина.
        """
        user = self.model(**extra_fields)
        user.create_iban()
        user.create_username()
        try:
            user.atm = ATM.objects.get(pk=1)
        except models.ObjectDoesNotExist:
            ATM.objects.create(balance=10000)
            user.atm = ATM.objects.get(pk=1)
        user.set_password('0000')
        user.save(using=self._db)
        self._create_card(user)
        return user

    def create_user(self, **extra_fields):
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(**extra_fields)

    def create_superuser(self, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self._create_user(**extra_fields)

    @staticmethod
    def _create_card(user):
        card = Card()
        card.card_number = user.username
        card.user = user
        card.save()
        return card.card_number


class CardManager(models.Manager):
    def create(self, kwargs):
        card = self.model(**kwargs)
        card.create_card()
        card.save()
        return card


class ATM(models.Model):
    objects = models.Manager()
    balance = models.PositiveIntegerField(
        default=0,
        verbose_name='Баланс доступної готівки в банкоматі'
    )

    def __str__(self):
        return str(self.balance)

    def get_balance(self):
        return self.balance


class Transaction(models.Model):
    TYPES_TRANSACTIONS = [
        ('Всі транзакціі', 'Всі транзакціі'),
        ('Поповнення', 'Поповнення'),
        ('Зняття готівки', 'Зняття готівки'),
        ('Переказ', 'Переказ'),
        ('Отримання', 'Отримання'),
    ]
    objects = models.Manager()
    date = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата'
    )
    type_transaction = models.CharField(
        max_length=16,
        choices=TYPES_TRANSACTIONS,
        verbose_name='Тип транзакцій'
    )
    sender = models.CharField(
        max_length=16,
        default=None,
        null=True,
        verbose_name='Відправник'
    )
    receiver = models.CharField(
        max_length=16,
        default=None,
        null=True,
        verbose_name='Отримувач'
    )
    value = models.FloatField(
        verbose_name='Сума'
    )
    user = models.ForeignKey(
        'User', on_delete=models.CASCADE,
        related_name='transaction'
    )

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.date} {self.type_transaction} {self.sender} ' \
               f'{self.receiver} {self.value}'


class Card(models.Model):
    TYPES_CURRENCY = [
        ('UAH', 'Гривня'),
        ('USD', 'Долар США'),
        ('EUR', 'Євро'),
    ]
    objects = CardManager()
    card_number = models.CharField(
        max_length=16,
        unique=True, primary_key=True,
        verbose_name='Номер карти'
    )
    currency = models.CharField(
        max_length=3,
        choices=TYPES_CURRENCY,
        default='UAH',
        verbose_name='Валюта карти'
    )
    balance = models.FloatField(
        default=0,
        verbose_name='Баланс карти'
    )
    user = models.ForeignKey('User', on_delete=models.CASCADE,
                             related_name='wallet')

    def __str__(self):
        return f'{self.currency} {self.card_number}'

    def create_card(self):
        random_card = [str(randint(0, 9)) for _ in range(12)]
        new_card = '4149' + ''.join(random_card)
        self.card_number = new_card
        return self.card_number

    def get_balance(self):
        return f'Баланс карти: {self.balance} {self.currency}'

    def deposit(self, value):
        atm = ATM.objects.get(pk=1)
        atm.balance += value
        self.balance += value
        self.log_recording('Поповнення', None, self.card_number, value,
                           self.user)
        atm.save(), self.save()
        return f'Баланс рахунку {self} поповнено на {value} {self.currency}'

    def withdraw(self, value):
        atm = ATM.objects.get(pk=1)
        if value <= atm.get_balance() and value <= self.balance:
            self.balance -= value
            atm.balance -= value
            self.log_recording('Зняття готівки', None, self.card_number, value,
                               self.user)
            atm.save(), self.save()
            return f'Знято {value} {self.currency}'
        return f'На вашому рахунку недостатньо коштів для зняття {value} ' \
               f'{self.currency}' if value > self.balance else \
            'В банкоматі недостатньо готівки'

    def send_money(self, value, receiver_card):
        if value <= self.balance:
            self.balance -= value
            if self.currency != receiver_card.currency:
                value = self.exchange(value, self, receiver_card)
            receiver_card.balance += value
            self.log_recording(
                'Переказ', self.card_number, receiver_card.card_number,
                value, self.user)
            self.log_recording(
                'Отримання', self.card_number, receiver_card.card_number, value,
                receiver_card.user)
            self.save(), receiver_card.save()
            return f'Успішний переказ на {receiver_card} {value} ' \
                   f'{receiver_card.currency}'
        return f'На вашому рахунку недостатньо коштів для переказу {value}' \
               f'{self.currency}'

    @staticmethod
    def log_recording(type_transaction, sender, receiver, value, user):
        transaction = Transaction.objects.create(
            type_transaction=type_transaction,
            sender=sender,
            receiver=receiver,
            value=value,
            user=user
        )
        return transaction

    @staticmethod
    def exchange(value, sender_card, receiver_card):
        from atm.utils import get_currency_rate
        currency_rate = get_currency_rate()
        exchanger = {
            'UAH': {
                'USD': lambda: value / float(currency_rate['usd_sale']),
                'EUR': lambda: value / float(currency_rate['eur_sale'])
            },
            'USD': {
                'EUR': lambda: ((currency_rate['usd_sale'] * value) /
                                currency_rate['eur_buy']),
                'UAH': lambda: value * float(currency_rate['usd_buy'])
            },
            'EUR': {
                'USD': lambda: ((currency_rate['eur_buy'] * value) /
                                currency_rate['usd_sale']),
                'UAH': lambda: value * float(currency_rate['eur_buy'])
            }
        }
        result = exchanger[sender_card.currency][receiver_card.currency]()
        return round(result, 2)


class User(AbstractBaseUser, PermissionsMixin):
    username_validator = UnicodeUsernameValidator()
    objects = UserManager()
    username = models.CharField(
        _("Номер карти"),
        max_length=16,
        unique=True,
        validators=[username_validator]
    )
    iban = models.CharField(
        max_length=30, unique=True,
        verbose_name='Номер рахунку IBAN',
        primary_key=True
    )
    password = models.CharField(
        _("PIN-код"),
        max_length=4, default='0000'
    )
    last_name = models.CharField(
        max_length=30,
        verbose_name='Прізвище'
    )
    first_name = models.CharField(
        max_length=30,
        verbose_name='Ім\'я'
    )
    phone_number = models.CharField(
        max_length=13,
        verbose_name='Фінансовий номер телефону'
    )
    time_create = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата відкриття рахунку'
    )
    time_update = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата оновлення даних'
    )
    is_active = models.BooleanField(
        _('is_active'),
        default=True
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_(
            "Designates whether the user can log into this admin site."),
    )
    atm = models.ForeignKey(
        ATM,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )

    USERNAME_FIELD = 'username'

    REQUIRED_FIELDS = ['first_name', 'last_name', 'phone_number']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def __str__(self):
        return self.iban

    def create_username(self):
        random_card = [str(randint(0, 9)) for _ in range(12)]
        new_card = '4149' + ''.join(random_card)
        self.username = new_card
        return self.username

    def create_iban(self):
        country = 'UA'
        code = '0000'
        random_iban = [str(randint(0, 9)) for _ in range(12)]
        new_iban = country + code + ''.join(random_iban)
        return self.set_iban(new_iban)

    def set_iban(self, iban):
        self.iban = iban
        return self.iban

    def change_pin(self, current_pin, pin1, pin2):
        if not self.check_password(current_pin):
            return f'Поточний PIN-код неправильний'
        if pin1 == pin2:
            self.set_password(pin2)
            self.save()
            return f'Новий PIN-код {pin2} установлено'
        return f'PIN-код не співпадає'
