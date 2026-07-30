from django.core.management.base import BaseCommand
from django.db import transaction
from main.models import (
    Sale, Adai, BankAccount, Transaction, Expence, 
    PendingSale, MarketingCost, SalesmanSalaryPayment, Customer
)

class Command(BaseCommand):
    help = 'Clear all data from database except Salesman and Product data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete all data',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    'This command will delete ALL data except Salesman and Product records.\n'
                    'To confirm, run: python manage.py clear_data --confirm'
                )
            )
            return

        with transaction.atomic():
            # Count records before deletion
            sale_count = Sale.objects.count()
            adai_count = Adai.objects.count()
            customer_count = Customer.objects.count()
            bank_count = BankAccount.objects.count()
            transaction_count = Transaction.objects.count()
            expense_count = Expence.objects.count()
            pending_sale_count = PendingSale.objects.count()
            marketing_count = MarketingCost.objects.count()
            salary_count = SalesmanSalaryPayment.objects.count()

            # Delete all data except Salesman and Product
            Sale.objects.all().delete()
            Adai.objects.all().delete()
            Customer.objects.all().delete()
            BankAccount.objects.all().delete()
            Transaction.objects.all().delete()
            Expence.objects.all().delete()
            PendingSale.objects.all().delete()
            MarketingCost.objects.all().delete()
            SalesmanSalaryPayment.objects.all().delete()

            # Reset auto-increment counters for models that have them
            from django.db import connection
            with connection.cursor() as cursor:
                # Reset auto-increment for models with primary keys
                cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('main_sale', 'main_adai', 'main_customer', 'main_bankaccount', 'main_transaction', 'main_expence', 'main_pendingsale', 'main_marketingcost', 'main_salesmansalarypayment')")

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully cleared all data:\n'
                    f'- Sales: {sale_count} records deleted\n'
                    f'- Adai: {adai_count} records deleted\n'
                    f'- Customers: {customer_count} records deleted\n'
                    f'- Bank Accounts: {bank_count} records deleted\n'
                    f'- Transactions: {transaction_count} records deleted\n'
                    f'- Expenses: {expense_count} records deleted\n'
                    f'- Pending Sales: {pending_sale_count} records deleted\n'
                    f'- Marketing Costs: {marketing_count} records deleted\n'
                    f'- Salary Payments: {salary_count} records deleted\n\n'
                    f'Salesman and Product data preserved.'
                )
            )
