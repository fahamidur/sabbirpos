from django.core.management.base import BaseCommand
from django.db import transaction
from main.models import (
    Transaction,
    BankAccount,
    Sale,
    Adai,
    PendingSale,
    SalesmanSalaryPayment,
    Expence,
    Order,
    Customer,
    Salesman,
    Product,
)


class Command(BaseCommand):
    help = (
        'Delete all transactional data; keep Customer, Salesman, Product, and MarketingCost. '
        'Optionally reset balance/counter fields on kept models.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete all transactional data.',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Also reset Customer (due/Advance/Paid), Salesman (Due/Paid/salescomission), and Product (total_sales) to 0.',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    'This command will DELETE all transactional data and keep only:\n'
                    '  Customer, Salesman, Product, MarketingCost\n'
                    'Deleted: Transaction, BankAccount, Sale, Adai, PendingSale, '
                    'SalesmanSalaryPayment, Expence, Order\n\n'
                    'To confirm, run: python manage.py reset_transactional_data --confirm\n\n'
                    'To also reset balance/counter fields on kept models, add: --reset'
                )
            )
            return

        with transaction.atomic():
            # Delete in order (children before parents / no FKs to kept models)
            counts = {}

            counts['Transaction'] = Transaction.objects.count()
            Transaction.objects.all().delete()

            counts['BankAccount'] = BankAccount.objects.count()
            BankAccount.objects.all().delete()

            counts['Sale'] = Sale.objects.count()
            Sale.objects.all().delete()

            counts['Adai'] = Adai.objects.count()
            Adai.objects.all().delete()

            counts['PendingSale'] = PendingSale.objects.count()
            PendingSale.objects.all().delete()

            counts['SalesmanSalaryPayment'] = SalesmanSalaryPayment.objects.count()
            SalesmanSalaryPayment.objects.all().delete()

            counts['Expence'] = Expence.objects.count()
            Expence.objects.all().delete()

            counts['Order'] = Order.objects.count()
            Order.objects.all().delete()

            # Optional: reset balance/counter fields on kept models
            if options['reset']:
                Customer.objects.all().update(due=0, Advance=0, Paid=0)
                Salesman.objects.all().update(Due=0, Paid=0, salescomission=0)
                Product.objects.all().update(total_sales=0)
                self.stdout.write(
                    self.style.SUCCESS('Reset Customer (due/Advance/Paid), Salesman (Due/Paid/salescomission), Product (total_sales) to 0.')
                )

            # Report
            self.stdout.write(self.style.SUCCESS('Successfully cleared transactional data:'))
            for name, n in counts.items():
                self.stdout.write(f'  - {name}: {n} record(s) deleted')
            self.stdout.write(
                self.style.SUCCESS(
                    '\nKept: Customer, Salesman, Product, MarketingCost.'
                )
            )
