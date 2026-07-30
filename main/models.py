from django.db import models

class Salesman(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    area = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    nid = models.CharField(max_length=50)
    comission = models.FloatField(default=0)
    basic_salary = models.FloatField(default=0)
    Due = models.FloatField(default=0)
    salescomission = models.FloatField(default=0)
    Paid = models.FloatField(default=0)

    def __str__(self):
        return self.name

class Customer(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    area = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    nid = models.CharField(max_length=50)
    due = models.FloatField(default=0)
    Advance = models.FloatField(default=0)
    Paid = models.FloatField(default=0)

    def __str__(self):
        return self.name

class Product(models.Model):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    size = models.CharField(max_length=50)
    rate = models.FloatField(default=0)
    add_stock = models.FloatField(default=0)
    production_cost = models.FloatField(default=0)
    total_sales = models.FloatField(default=0)
    total_stock = models.FloatField(default=0)
    image = models.URLField(max_length=500, blank=True, null=True)

    def __str__(self):
        return self.name

class Sale(models.Model):
    salesman = models.ForeignKey(Salesman, on_delete=models.SET_NULL, null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    products = models.JSONField(default=list)  # Store product info as JSON
    total_price = models.FloatField(default=0)
    discount = models.FloatField(default=0)
    less = models.FloatField(default=0)  # final_less (unchangable)
    total_less_products = models.FloatField(default=0)
    less_input = models.FloatField(default=0)
    payment_received = models.FloatField(default=0)
    advance_used = models.FloatField(default=0)
    payment_incash=models.FloatField(default=0)
    due = models.FloatField(default=0)
    date = models.DateField()
    time = models.TimeField()
    comission = models.FloatField(default=0)
    invoice_number = models.CharField(max_length=100, unique=True, blank=True, null=True)

class Adai(models.Model):
    salesman = models.ForeignKey(Salesman, on_delete=models.SET_NULL, null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    due = models.FloatField(default=0)
    advance = models.FloatField(default=0)
    date = models.DateField()
    sales_comission = models.FloatField(default=0)
    invoice_number = models.CharField(max_length=50, blank=True, null=True)

class BankAccount(models.Model):
    bank_name = models.CharField(max_length=100)
    branch_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50, unique=True)
    opening_balance = models.FloatField(default=0)
    current_balance = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bank_name} - {self.branch_name} ({self.account_number})"

class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('debit', 'Debit'),
        ('credit', 'Credit'),
    )
    
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    narration = models.CharField(max_length=200)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES, default='credit')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        if self.bank_account:
            if self.transaction_type == 'debit':
                self.bank_account.current_balance -= self.amount
            else:  # credit
                self.bank_account.current_balance += self.amount
            self.bank_account.save()
            self.balance = self.bank_account.current_balance
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.narration} ({self.amount})"

class Expence(models.Model):
    date = models.DateField()
    narration = models.CharField(max_length=255)
    suplier = models.CharField(max_length=100)
    due = models.FloatField(default=0)
    advance = models.FloatField(default=0)
    total_pay = models.FloatField(default=0)

class PendingSale(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ]
    
    salesman = models.ForeignKey(Salesman, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    products = models.JSONField(default=list)
    total_price = models.FloatField(default=0)
    discount = models.FloatField(default=0)
    less = models.FloatField(default=0)  # final_less (unchangable)
    total_less_products = models.FloatField(default=0)
    less_input = models.FloatField(default=0)
    payment_received = models.FloatField(default=0)
    due = models.FloatField(default=0)
    date = models.DateField(auto_now_add=True)
    time = models.TimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    invoice_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    comission = models.FloatField(default=0)

    def __str__(self):
        return f"Pending Sale - {self.invoice_number or 'No Invoice'} - {self.salesman.name}"

class MarketingCost(models.Model):
    date = models.DateField()
    salesman = models.ForeignKey(Salesman, on_delete=models.CASCADE)
    customer_name = models.CharField(max_length=100)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    expense_type = models.CharField(max_length=50, choices=[
        ('Transportation', 'Transportation'),
        ('Hotel', 'Hotel'),
        ('Food', 'Food'),
        ('Mobile', 'Mobile'),
    ])
    amount = models.FloatField(default=0)

    def __str__(self):
        return f"{self.date} - {self.salesman.name} - {self.expense_type} - {self.amount}"

class SalesmanSalaryPayment(models.Model):
    salesman = models.ForeignKey(Salesman, on_delete=models.CASCADE)
    amount = models.FloatField(default=0)
    date = models.DateField()
    def __str__(self):
        return f"{self.salesman.name} - {self.amount} on {self.date}"

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    order_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    customer_name = models.CharField(max_length=100)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)
    shipping_address = models.TextField()
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    products = models.JSONField(default=list)
    total_price = models.FloatField(default=0)
    discount = models.FloatField(default=0)
    shipping_cost = models.FloatField(default=0)
    payment_method = models.CharField(max_length=50, default='cash_on_delivery')
    payment_received = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Order {self.order_number} - {self.customer_name}"