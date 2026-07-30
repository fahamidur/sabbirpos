# views.py
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction  # Add this import at the top
from django.db import models

from django.http import HttpResponse
from django.template.loader import render_to_string
from playwright.async_api import async_playwright
import asyncio
from .models import Salesman  # Make sure this import is at the top
from .models import Product
from .models import Customer, Sale,Adai
from .models import Transaction
from .models import Expence,PendingSale
from .models import BankAccount
from .models import MarketingCost
from .models import SalesmanSalaryPayment
from .models import Order

from django.http import JsonResponse, HttpResponse
import json
import os
import hmac
import random
from pathlib import Path
from datetime import timedelta
from datetime import datetime
from django.contrib import messages
import calendar
import pandas as pd
from django.urls import reverse
from django.db.models import Sum
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.conf import settings
from io import BytesIO


def get_customer_calculated_due_advance(customer):
    """
    Calculate current due and advance from Sales + Adai. Customer.due and Customer.Advance
    are treated as initial (opening) values, set only on create/edit.
    Total advance used (Sale.advance_used) is also considered in the calculation.
    Returns (current_due, current_advance).
    """
    initial_due = float(customer.due or 0)
    initial_advance = float(customer.Advance or 0)
    total_sale_due = Sale.objects.filter(customer=customer).aggregate(t=Sum('due'))['t'] or 0
    total_advance_used = Sale.objects.filter(customer=customer).aggregate(t=Sum('advance_used'))['t'] or 0
    due_collected = Adai.objects.filter(customer=customer).aggregate(t=Sum('due'))['t'] or 0
    advance_collected = Adai.objects.filter(customer=customer).aggregate(t=Sum('advance'))['t'] or 0
    total_obligation = initial_due + total_sale_due - initial_advance
    total_collected = due_collected + advance_collected
    net = total_collected - total_obligation-total_advance_used
    if net < 0:
        return (-net, 0)
    if net > 0:
        return (0, net)
    return (0, 0)


def get_sale_net_amount(sale):
    """
    Net bill for a sale using only saved fields (same as sale_due at save_sale time).
    save_sale stores: total_price = gross (total_price+final_less-less_input), discount, less=final_less.
    Net = total_price - discount - less.
    """
    total_price = float(sale.total_price or 0)
    discount = float(sale.discount or 0)
    less = float(sale.less or 0)
    return total_price - discount - less


def get_balance_after_each_sale(customer):
    """
    For each sale of this customer, compute (due, advance) balance after that sale.
    Events are processed in chronological order (sales by date+time, then adais by date).
    Returns dict: sale.id -> {'due': x, 'advance': y}.
    """
    from datetime import time as dt_time
    initial_due = float(customer.due or 0)
    initial_advance = float(customer.Advance or 0)
    obligation = initial_due - initial_advance  # net opening obligation
    paid = 0.0
    result = {}  # sale_id -> {'due': _, 'advance': _}

    # Build list of events: (date, time_sort_key, 'sale'|'adai', obj)
    events = []
    for s in Sale.objects.filter(customer=customer).order_by('date', 'time'):
        t = s.time if s.time else dt_time(0, 0, 0)
        events.append((s.date, (t.hour, t.minute, t.second), 'sale', s))
    for a in Adai.objects.filter(customer=customer).order_by('date'):
        events.append((a.date, (23, 59, 59), 'adai', a))  # adai after sales on same day
    events.sort(key=lambda e: (e[0], e[1]))

    for _date, _time, etype, obj in events:
        if etype == 'sale':
            obligation += float(obj.due or 0)
            paid += float(obj.payment_received or 0) + float(obj.advance_used or 0)
            balance = obligation - paid
            if balance >= 0:
                result[obj.id] = {'due': round(balance, 2), 'advance': 0}
            else:
                result[obj.id] = {'due': 0, 'advance': round(-balance, 2)}
        else:
            paid += float(obj.due or 0) + float(obj.advance or 0)

    return result


def get_customer_ledger_events(customer):
    """
    Build a single list of ledger events from Sales and Adai only, in chronological order.
    Each event: {'date': date, 'time_sort': (h,m,s), 'debit': x, 'credit': y, 'particulars': str, 'invoice_number': str}.
    Debit = increases what customer owes (sale net). Credit = decreases (payment, adai).
    NOTE: Do not add Sale.advance_used as a separate credit event here; sale net debit already
    applies against any existing advance through the running balance.
    """
    from datetime import time as dt_time
    events = []
    for s in Sale.objects.filter(customer=customer).order_by('date', 'time'):
        t = s.time if s.time else dt_time(0, 0, 0)
        net = get_sale_net_amount(s)
        inv = s.invoice_number or 'N/A'
        events.append({
            'date': s.date,
            'time_sort': (t.hour, t.minute, t.second),
            'debit': net,
            'credit': 0,
            'particulars': 'Sale',
            'invoice_number': inv,
            'desc': ', '.join([str(p.get('name') or p.get('product') or '') for p in (s.products or [])])[:80],
        })
        if (s.payment_received or 0) > 0:
            events.append({
                'date': s.date,
                'time_sort': (t.hour, t.minute, t.second),
                'debit': 0,
                'credit': float(s.payment_received or 0),
                'particulars': 'Payment at sale',
                'invoice_number': inv,
                'desc': '',
            })
    for a in Adai.objects.filter(customer=customer).order_by('date'):
        if (a.due or 0) > 0:
            events.append({
                'date': a.date,
                'time_sort': (23, 59, 59),
                'debit': 0,
                'credit': float(a.due or 0),
                'particulars': 'Due payment',
                'invoice_number': 'Adai',
                'desc': '',
            })
        if (a.advance or 0) > 0:
            events.append({
                'date': a.date,
                'time_sort': (23, 59, 59),
                'debit': 0,
                'credit': float(a.advance or 0),
                'particulars': 'Advance',
                'invoice_number': 'Adai',
                'desc': '',
            })
    events.sort(key=lambda e: (e['date'], e['time_sort']))
    return events


def index(request):
    """
    View to render the company website homepage (index.html)
    This is a public-facing page that doesn't require authentication
    """
    return render(request, 'index.html')

def homepage(request):
    """
    View to render the ecommerce homepage (homepage.html)
    This is a public-facing page that displays products
    """
    products = Product.objects.all().order_by('id')  # Get all products
    return render(request, 'homepage.html', {'products': products})

def product_detail(request, product_id):
    """
    View to render the product detail page
    """
    try:
        product = Product.objects.get(id=product_id)
        # Get related products (other products in the same category or similar)
        related_products = Product.objects.exclude(id=product_id).order_by('?')[:4]
        return render(request, 'product_detail.html', {
            'product': product,
            'related_products': related_products
        })
    except Product.DoesNotExist:
        return redirect('homepage')

def dashboard(request):
    # Default to the current date if no filter is applied
    selected_date = datetime.now()
    selected_month = selected_date.month
    selected_year = selected_date.year

    if request.method == "POST":
        # Get the selected month and year from the form
        selected_month = int(request.POST.get("month", selected_month))
        selected_year = int(request.POST.get("year", selected_year))

    # Calculate the previous month and year
    if selected_month == 1:
        previous_month = 12
        previous_year = selected_year - 1
    else:
        previous_month = selected_month - 1
        previous_year = selected_year

    # Initialize aggregates for sales
    total_sale_all = 0
    total_commission_all = 0
    total_discount_all = 0
    total_sales_due = 0
    total_payment_received = 0
    total_advance_used = 0

    current_month_sale = 0
    current_month_commission = 0
    current_month_discount = 0
    current_month_sales_due = 0
    current_month_payment_received = 0
    current_month_advance_used = 0

    previous_month_sale = 0
    previous_month_commission = 0
    previous_month_discount = 0
    previous_month_sales_due = 0
    previous_month_payment_received = 0
    previous_month_advance_used = 0

    # Initialize aggregates for adai
    total_due_adai = 0
    total_advance_adai = 0

    current_month_due_adai = 0
    current_month_advance_adai = 0

    previous_month_due_adai = 0
    previous_month_advance_adai = 0

    # Track customers per period (from sales + adai) for due formula
    all_customer_ids = set()
    current_month_customer_ids = set()
    previous_month_customer_ids = set()

    # Process sales data from Sale model
    sales_data = Sale.objects.all()
    for sale in sales_data:
        sale_total = float(sale.total_price or 0)
        sale_commission = float(sale.discount or 0)
        sale_discount = float(sale.less or 0)
        sale_due = float(sale.due or 0)
        sale_payment_received = float(sale.payment_received or 0)
        sale_advance_used = float(sale.advance_used or 0)
        sale_date = sale.date

        total_sale_all += sale_total
        total_commission_all += sale_commission
        total_discount_all += sale_discount
        total_sales_due += sale_due
        total_payment_received += sale_payment_received
        total_advance_used += sale_advance_used
        if sale.customer_id:
            all_customer_ids.add(sale.customer_id)
        if sale_date:
            # Current month data
            if sale_date.year == selected_year and sale_date.month == selected_month:
                current_month_sale += sale_total
                current_month_commission += sale_commission
                current_month_discount += sale_discount
                current_month_sales_due += sale_due
                current_month_payment_received += sale_payment_received
                current_month_advance_used += sale_advance_used
                if sale.customer_id:
                    current_month_customer_ids.add(sale.customer_id)

            # Previous month data
            if sale_date.year == previous_year and sale_date.month == previous_month:
                previous_month_sale += sale_total
                previous_month_commission += sale_commission
                previous_month_discount += sale_discount
                previous_month_sales_due += sale_due
                previous_month_payment_received += sale_payment_received
                previous_month_advance_used += sale_advance_used
                if sale.customer_id:
                    previous_month_customer_ids.add(sale.customer_id)

    # Process adai data from Adai model
    adai_data = Adai.objects.all()
    for adai in adai_data:
        adai_due = float(adai.due or 0)
        adai_advance = float(adai.advance or 0)
        adai_date = adai.date

        total_due_adai += adai_due
        total_advance_adai += adai_advance
        if adai.customer_id:
            all_customer_ids.add(adai.customer_id)

        if adai_date:
            # Current month data
            if adai_date.year == selected_year and adai_date.month == selected_month:
                current_month_due_adai += adai_due
                current_month_advance_adai += adai_advance
                if adai.customer_id:
                    current_month_customer_ids.add(adai.customer_id)

            # Previous month data
            if adai_date.year == previous_year and adai_date.month == previous_month:
                previous_month_due_adai += adai_due
                previous_month_advance_adai += adai_advance
                if adai.customer_id:
                    previous_month_customer_ids.add(adai.customer_id)

    # Customer initial due/advance sums for each period's involved customers
    all_customers = Customer.objects.filter(id__in=all_customer_ids) if all_customer_ids else Customer.objects.none()
    current_month_customers = Customer.objects.filter(id__in=current_month_customer_ids) if current_month_customer_ids else Customer.objects.none()
    previous_month_customers = Customer.objects.filter(id__in=previous_month_customer_ids) if previous_month_customer_ids else Customer.objects.none()

    total_customer_initial_due = sum(float(c.due or 0) for c in all_customers)
    total_customer_advance = sum(float(c.Advance or 0) for c in all_customers)
    current_month_customer_initial_due = sum(float(c.due or 0) for c in current_month_customers)
    current_month_customer_advance = sum(float(c.Advance or 0) for c in current_month_customers)
    previous_month_customer_initial_due = sum(float(c.due or 0) for c in previous_month_customers)
    previous_month_customer_advance = sum(float(c.Advance or 0) for c in previous_month_customers)

    # Due formula for all-time/current/previous:
    # (sales_due + customer_initial_due) - (customer_advance + adai_due + adai_advance - advance_used)
    total_due = (total_sales_due + total_customer_initial_due) - (
        total_customer_advance + total_due_adai + total_advance_adai - total_advance_used
    )
    current_month_due = (current_month_sales_due + current_month_customer_initial_due) - (
        current_month_customer_advance + current_month_due_adai + current_month_advance_adai - current_month_advance_used
    )
    previous_month_due = (previous_month_sales_due + previous_month_customer_initial_due) - (
        previous_month_customer_advance + previous_month_due_adai + previous_month_advance_adai - previous_month_advance_used
    )

    # If negative, show 0
    total_due = max(0.0, float(total_due or 0))
    current_month_due = max(0.0, float(current_month_due or 0))
    previous_month_due = max(0.0, float(previous_month_due or 0))

    # Calculate total opening advance (for advance section cards)
    from django.db.models import Sum
    total_opening_advance = Customer.objects.aggregate(t=Sum('Advance'))['t'] or 0
    # অগ্রিম জমা মোট: গ্রাহকের ইনিশিয়াল অগ্রিম + সব Adai.advance (Adjust Sales)
    advance_adai_all_time = float(total_opening_advance or 0) + float(total_advance_adai or 0)
    # অগ্রিম ব্যবহৃত হলে (Sale.advance_used) অগ্রিম জমা থেকে কাটতে হবে
    advance_adai_all_time_after_used = max(0.0, float(advance_adai_all_time or 0) - float(total_advance_used or 0))
    # current_month_due can be negative (no max constraint)
    # Remove previous_month_due from context if present

    # Prepare context for the template
    context = {
        "selected_month": selected_month,
        "selected_year": selected_year,
        "months": [{"number": i, "name": calendar.month_name[i]} for i in range(1, 13)],
        "years": range(2020, 2031),
        "total_sales": {
            "previous_month": previous_month_sale,
            "current_month": current_month_sale,
            "all_time": total_sale_all,
        },
        "total_commission": {
            "previous_month": previous_month_commission,
            "current_month": current_month_commission,
            "all_time": total_commission_all,
        },
        "after_discount": {
            "previous_month": previous_month_sale - previous_month_commission-previous_month_discount,
            "current_month": current_month_sale - current_month_commission-current_month_discount,
            "all_time": total_sale_all - total_commission_all-total_discount_all,
        },
        "less": {
            "previous_month": previous_month_discount,
            "current_month": current_month_discount,
            "all_time": total_discount_all,
        },
        "due": {
            "previous_month": previous_month_due,
            "current_month": current_month_due,
            "all_time": total_due,
        },
        "payment_received": {
            "previous_month": previous_month_payment_received,
            "current_month": current_month_payment_received,
            "all_time": total_payment_received,
        },
        "due_adai": {
            "previous_month": previous_month_due_adai,
            "current_month": current_month_due_adai,
            "all_time": total_due_adai,
        },
        "advance_adai": {
            "previous_month": max(0.0, float(previous_month_advance_adai or 0) - float(previous_month_advance_used or 0)),
            "current_month": max(0.0, float(current_month_advance_adai or 0) - float(current_month_advance_used or 0)),
            "all_time": advance_adai_all_time_after_used,
        },
        "mot_adai": {
            "previous_month": previous_month_advance_adai+previous_month_due_adai+previous_month_payment_received,
            "current_month": current_month_advance_adai+current_month_due_adai+current_month_payment_received,
            # চলতি মাসের মতো: আদায়ে অগ্রিম+বাকি আদায় + বিক্রিতে পেমেন্ট (Customer.Advance বাদ)
            "all_time": float(total_advance_adai or 0) + float(total_due_adai or 0) + float(total_payment_received or 0),
        },
    }

    return render(request, "Report.html", context)

@csrf_exempt
def salesman_list(request):
    if request.method == 'POST':
        # Adding a new salesmanm
        name = request.POST.get('name')
        code = request.POST.get('code')
        area = request.POST.get('area')
        phone = request.POST.get('phone')
        nid = request.POST.get('nid')
        comission = float(request.POST.get('comission', 0) or 0)
        basic_salary = float(request.POST.get('basic_salary', 0) or 0)
        if name and code and area and phone and nid:
            Salesman.objects.create(
                name=name,
                code=code,
                area=area,
                phone=phone,
                nid=nid,
                comission=comission,
                basic_salary=basic_salary
            )
            return redirect('salesman_list')

    # Period filter: all_time (default), last_month, custom (month + year)
    today = datetime.now().date()
    period = (request.GET.get('period') or 'all_time').strip().lower()
    filter_year = None
    filter_month = None
    if period == 'last_month':
        if today.month == 1:
            filter_year = today.year - 1
            filter_month = 12
        else:
            filter_year = today.year
            filter_month = today.month - 1
    elif period == 'custom':
        try:
            filter_year = int(request.GET.get('year') or 0)
            filter_month = int(request.GET.get('month') or 0)
            if not (1 <= filter_month <= 12 and filter_year >= 2000):
                period = 'all_time'
                filter_year = filter_month = None
        except (ValueError, TypeError):
            period = 'all_time'
            filter_year = filter_month = None

    # Base querysets for Sale and Adai (optionally filtered by date)
    sale_qs = Sale.objects.all()
    adai_qs = Adai.objects.all()
    if filter_year and filter_month:
        sale_qs = sale_qs.filter(date__year=filter_year, date__month=filter_month)
        adai_qs = adai_qs.filter(date__year=filter_year, date__month=filter_month)

    # Fetching all salesmen
    salesmen_list = Salesman.objects.all()
    # Commission from all sales (filtered by period)
    commission_from_sales = dict(
        sale_qs.values('salesman').annotate(total=Sum('comission')).values_list('salesman', 'total')
    )
    # Commission from Adai (filtered by period)
    commission_from_adai = dict(
        adai_qs.filter(salesman__isnull=False).values('salesman').annotate(total=Sum('sales_comission')).values_list('salesman', 'total')
    )
    # Total paid sales per salesman (filtered by period)
    paid_sales_by_salesman = dict(
        sale_qs.values('salesman').annotate(total=Sum('payment_received')).values_list('salesman', 'total')
    )
    # Total collection (due + advance) per salesman from Adai (filtered by period)
    salesmen_with_adai = []
    for salesman in salesmen_list:
        adai_records = adai_qs.filter(salesman=salesman)
        total_due = sum(a.due or 0 for a in adai_records)
        total_advance = sum(a.advance or 0 for a in adai_records)
        total_collection = total_due + total_advance
        total_paid_sales = paid_sales_by_salesman.get(salesman.id, 0) or 0
        total_sales = total_collection + total_paid_sales
        total_commission = (commission_from_sales.get(salesman.id, 0) or 0) + (commission_from_adai.get(salesman.id, 0) or 0)
        s = {
            'id': salesman.id,
            'name': salesman.name,
            'code': salesman.code,
            'area': salesman.area,
            'phone': salesman.phone,
            'comission': salesman.comission,
            'basic_salary': getattr(salesman, 'basic_salary', 0),
            'salescomission': total_commission,
            'adai': total_collection,
            'total_collection': total_collection,
            'total_paid_sales': total_paid_sales,
            'total_sales': total_sales,
        }
        s['json'] = json.dumps(s)
        salesmen_with_adai.append(s)

    # Build list of months for custom dropdown (1-12)
    months = [{'value': i, 'label': calendar.month_name[i]} for i in range(1, 13)]
    current_year = today.year
    years = list(range(current_year, current_year - 11, -1))  # current year and 10 past years
    context = {
        'salesmen': salesmen_with_adai,
        'period': period,
        'filter_month': filter_month or today.month,
        'filter_year': filter_year or current_year,
        'months': months,
        'years': years,
    }
    return render(request, 'Salesman.html', context)

@csrf_exempt
def delete_salesman(request, salesman_id):
    if request.method == 'POST':
        try:
            salesman = Salesman.objects.get(id=salesman_id)
            salesman.delete()
        except Salesman.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('salesman_list')




@csrf_exempt
def customer_list(request):
    if request.method == 'POST':
        # Adding a new customer (initial due/advance from form only)
        name = request.POST.get('name')
        code = request.POST.get('code')
        area = request.POST.get('area')
        phone = request.POST.get('phone')
        nid = request.POST.get('nid')
        initial_due = float(request.POST.get('due', 0) or 0)
        initial_advance = float(request.POST.get('Advance', 0) or 0)
        if name and code and area and phone and nid:
            Customer.objects.create(
                name=name,
                code=code,
                area=area,
                phone=phone,
                nid=nid,
                due=initial_due,
                Advance=initial_advance,
                Paid=0
            )
            return redirect('customer_list')

    # Fetching all customers
    customers = Customer.objects.all()
    sales_data = Sale.objects.all()
    current_month = datetime.now().month
    current_year = datetime.now().year

    # Total buy = sum of net sale per sale (same as download_cash_memo net_bill)
    customer_totals = {}
    for sale in sales_data:
        customer_obj = sale.customer
        sale_date = sale.date
        net_sale = get_sale_net_amount(sale)  # total - discount - effective_less (matches memo)
        if customer_obj:
            customer_name = customer_obj.name
            if customer_name not in customer_totals:
                customer_totals[customer_name] = {'total_buy': 0, 'current_month_buy': 0}
            customer_totals[customer_name]['total_buy'] += net_sale
            if sale_date and sale_date.year == current_year and sale_date.month == current_month:
                customer_totals[customer_name]['current_month_buy'] += net_sale

    customer_list_data = []
    for customer in customers:
        current_due, current_advance = get_customer_calculated_due_advance(customer)
        customer_name = customer.name
        customer_dict = {
            'id': customer.id,
            'name': customer.name,
            'code': customer.code,
            'area': customer.area,
            'phone': customer.phone,
            'nid': customer.nid,
            'due': current_due,
            'Advance': current_advance,
            'initial_due': customer.due,
            'initial_advance': customer.Advance,
            'Paid': customer.Paid,
            'total_buy': customer_totals.get(customer_name, {}).get('total_buy', 0),
            'current_month_buy': customer_totals.get(customer_name, {}).get('current_month_buy', 0),
        }
        customer_dict['json'] = json.dumps(customer_dict)
        customer_list_data.append(customer_dict)

    return render(request, 'Customer.html', {'customer': customer_list_data})

@csrf_exempt
def upload_customers(request):
    """Upload customers from Excel file"""
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            excel_file = request.FILES['excel_file']
            
            # Read Excel file
            df = pd.read_excel(excel_file)
            
            # List of exact column names from the Excel file
            excel_column_names = ['Name', 'Code', 'Area', 'Phone', 'NID', 'Due', 'Advance', 'Paid']
            
            # Check for missing columns in the DataFrame
            missing_excel_columns = [col for col in excel_column_names if col not in df.columns]
            if missing_excel_columns:
                messages.error(request, f'Missing required columns in Excel file: {", ".join(missing_excel_columns)}. Please ensure your Excel has these exact column headers.')
                return redirect('customer_list')
            
            success_count = 0
            error_count = 0
            error_details = []
            
            for index, row in df.iterrows():
                try:
                    # Convert values to appropriate types and handle NaN using Excel column names
                    name = str(row['Name']) if pd.notna(row['Name']) else ''
                    code = str(row['Code']) if pd.notna(row['Code']) else ''
                    area = str(row['Area']) if pd.notna(row['Area']) else ''
                    phone = str(row['Phone']) if pd.notna(row['Phone']) else ''
                    nid = str(row['NID']) if pd.notna(row['NID']) else ''
                    due = float(row['Due']) if pd.notna(row['Due']) else 0.0
                    advance = float(row['Advance']) if pd.notna(row['Advance']) else 0.0
                    paid = float(row['Paid']) if pd.notna(row['Paid']) else 0.0
                    
                    # Validate required fields
                    if not name or not code or not area or not phone or not nid:
                        raise ValueError("Name, Code, Area, Phone, and NID are required fields for each customer.")
                    
                    customer, created = Customer.objects.update_or_create(
                        code=code,
                        defaults={
                            'name': name,
                            'area': area,
                            'phone': phone,
                            'nid': nid,
                            'due': due,
                            'Advance': advance,
                            'Paid': paid
                        }
                    )
                    
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    error_msg = f"Row {index + 2}: {str(e)}"
                    error_details.append(error_msg)
                    print(f"Error processing row {index + 2}: {str(e)}")
            
            if success_count > 0:
                messages.success(request, f'Successfully uploaded {success_count} customers')
            if error_count > 0:
                messages.warning(request, f'Failed to upload {error_count} customers')
                for error in error_details[:5]:  # Show first 5 errors
                    messages.error(request, error)
                if len(error_details) > 5:
                    messages.error(request, f"... and {len(error_details) - 5} more errors")
            
            return redirect('customer_list')
            
        except Exception as e:
            error_msg = f'Error processing file: {str(e)}'
            print(error_msg)  # Print to console for debugging
            messages.error(request, error_msg)
            return redirect('customer_list')
    
    # If GET request, redirect to customer list (upload will be done via modal)
    return redirect('customer_list')

@csrf_exempt
def export_customers_excel(request):
    """Export all customer data to Excel file"""
    try:
        # Fetch all customers
        customers = Customer.objects.all()
        
        # Fetch all sales for calculating totals
        sales_data = Sale.objects.all()
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        # Calculate total and current month purchases for each customer
        customer_totals = {}
        for sale in sales_data:
            customer_obj = sale.customer
            sale_date = sale.date
            total_price = float(sale.total_price or 0)
            
            if customer_obj:
                customer_name = customer_obj.name
                if customer_name not in customer_totals:
                    customer_totals[customer_name] = {'total_buy': 0, 'current_month_buy': 0}
                
                customer_totals[customer_name]['total_buy'] += total_price
                
                if sale_date.year == current_year and sale_date.month == current_month:
                    customer_totals[customer_name]['current_month_buy'] += total_price
        
        # Prepare data for Excel (use calculated due/advance)
        excel_data = []
        for customer in customers:
            customer_name = customer.name
            calc_due, calc_adv = get_customer_calculated_due_advance(customer)
            excel_data.append({
                'Name': customer.name,
                'Code': customer.code,
                'Area': customer.area,
                'Phone': customer.phone,
                'NID': customer.nid,
                'Due': float(calc_due),
                'Advance': float(calc_adv),
                'Paid': float(customer.Paid or 0),
                'Total Buy': customer_totals.get(customer_name, {}).get('total_buy', 0),
                'Current Month Buy': customer_totals.get(customer_name, {}).get('current_month_buy', 0),
            })
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Customers')
        
        # Prepare response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="customers_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        
        return response
    except Exception as e:
        messages.error(request, f'Error exporting customers: {str(e)}')
        return redirect('customer_list')

@csrf_exempt
def delete_customer(request, customer_id):
    if request.method == 'POST':
        try:
            customer = Customer.objects.get(id=customer_id)
            customer.delete()
        except Customer.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('customer_list')



@csrf_exempt
def product_list(request):
    if request.method == 'POST':
        # Retrieve form data
        code = request.POST.get('code')
        name = request.POST.get('name')
        size = request.POST.get('size')
        rate = float(request.POST.get('rate', 0) or 0)
        production_cost = float(request.POST.get('production_cost', 0) or 0)
        image_url = request.POST.get('image', '').strip()

        # Ensure all required fields are provided
        if code and name and size and rate is not None and production_cost is not None:
            product = Product.objects.create(
                code=code,
                name=name,
                size=size,
                rate=rate,
                add_stock=0,
                production_cost=production_cost,
                total_sales=0,
                total_stock=0,
                image=image_url if image_url else None
            )
            return redirect('product_list')
    
    # Fetch all products from the database
    products = Product.objects.all()
    return render(request, 'Product.html', {'products': products})

@csrf_exempt
def delete_product(request, product_id):
    if request.method == 'POST':
        try:
            product = Product.objects.get(id=product_id)
            product.delete()
        except Product.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('product_list')


# def pos_dashboard(request):
#     # Retrieve products from the Product model
#     products = Product.objects.all()
#     products_data = [
#         {
#             'id': product.id,
#             'name': product.name,
#             'rate': product.rate,
#             'size': product.size,
#             'total_stock': product.total_stock,
#             # Add other fields as needed
#         }
#         for product in products
#     ]

#     # Retrieve salesmen from the Salesman model
#     salesmen = Salesman.objects.all()
#     salesman_data = [
#         {
#             'id': salesman.id,
#             'name': salesman.name,
#             'code': salesman.code,
#             'area': salesman.area,
#             # Add other fields as needed
#         }
#         for salesman in salesmen
#     ]

#     # Retrieve customers from the Customer model
#     customers = Customer.objects.all()
#     customers_data = [
#         {
#             'id': customer.id,
#             'name': customer.name,
#             'code': customer.code,
#             'area': customer.area,
#             'due': customer.due,           # <-- Add this line
#             'Advance': customer.Advance,   # <-- And this line
#             # Add other fields as needed
#         }
#         for customer in customers
#     ]

#     context = {
#         'products': products_data,    # Each product should include a 'name' and 'rate' field
#         'salesman': salesman_data,    # Each salesman should include a 'name' field
#         'customers': customers_data,  # Each customer should include a 'name' field
#     }
    
#     return render(request, 'Sales.html', context)
def pos_dashboard(request):
    # Retrieve products from the Product model
    products = Product.objects.all()
    products_data = [
        {
            'id': product.id,
            'name': f"{product.name} - {product.size}",
            'rate': product.rate,
            'size': product.size,
            'total_stock': product.total_stock,
            # Add other fields as needed
        }
        for product in products
    ]

    # Retrieve salesmen from the Salesman model
    salesmen = Salesman.objects.all()
    salesman_data = [
        {
            'id': salesman.id,
            'name': salesman.name,
            'code': salesman.code,
            'area': salesman.area,
            # Add other fields as needed
        }
        for salesman in salesmen
    ]

    # Check if a salesman is selected (GET or POST)
    selected_salesman_id = request.GET.get('salesman') or request.POST.get('salesman')
    filtered_customers = None
    if selected_salesman_id:
        try:
            selected_salesman = Salesman.objects.get(id=selected_salesman_id)
            # Expecting code in format '001-100'
            code_range = selected_salesman.code
            if '-' in code_range:
                start_code, end_code = code_range.split('-')
                try:
                    start_code = int(start_code)
                    end_code = int(end_code)
                    # Only include customers whose code is numeric and in the range
                    filtered_customers = [
                        c for c in Customer.objects.all()
                        if c.code.isdigit() and start_code <= int(c.code) <= end_code
                    ]
                except ValueError:
                    filtered_customers = Customer.objects.none()
            else:
                filtered_customers = Customer.objects.none()
        except Salesman.DoesNotExist:
            filtered_customers = Customer.objects.none()
    else:
        filtered_customers = Customer.objects.all()

    customers_data = []
    for customer in filtered_customers:
        calc_due, calc_adv = get_customer_calculated_due_advance(customer)
        customers_data.append({
            'id': customer.id,
            'name': customer.name,
            'code': customer.code,
            'area': customer.area,
            'due': calc_due,
            'Advance': calc_adv,
        })

    context = {
        'products': products_data,    # Each product should include a 'name' and 'rate' field
        'salesman': salesman_data,    # Each salesman should include a 'name' field
        'customers': customers_data,  # Each customer should include a 'name' field
    }
    
    return render(request, 'Sales.html', context)
    
import requests

# @csrf_exempt
# def save_sale(request):
#     if request.method == 'POST':
#         data = json.loads(request.body)
#         sid = data.get('salesman')
#         cid = data.get('customer')
#         products_sold = data.get('products', [])
#         total_price = float(data.get('total_price', 0))
#         discount_percent = float(data.get('discount', 0))
#         less_input = float(data.get('less', 0))
#         payment_received = float(data.get('payment_received', 0))
#         due = float(data.get('due', 0))

#         # Validate required fields
#         if not sid or not cid:
#             return JsonResponse({'error': 'Salesman and Customer IDs are required.'}, status=400)

#         # Calculate total less from all products
#         total_less_products = sum(float(p.get('less', 0)) for p in products_sold)
#         # Final less is sum of all product less + less input
#         final_less = total_less_products + less_input

#         # Get salesman
#         try:
#             salesman = Salesman.objects.get(id=sid)
#             commission_rate = float(salesman.comission)
#             salesman_name = salesman.name
#             salesman_code = salesman.code
#         except Salesman.DoesNotExist:
#             return JsonResponse({'error': 'Salesman not found.'}, status=404)

#         # Get customer
#         try:
#             customer = Customer.objects.get(id=cid)
#             customer_name = customer.name
#             customer_phone = customer.phone
#             advance_amount = float(customer.Advance or 0)
#             customer_due = float(customer.due or 0)
#         except Customer.DoesNotExist:
#             return JsonResponse({'error': 'Customer not found.'}, status=404)
#         except ValueError:
#             return JsonResponse({'error': 'Invalid Customer ID.'}, status=400)

#         # Generate invoice number
#         # Get the last invoice number for this salesman
#         last_sale = Sale.objects.filter(
#             salesman=salesman,
#             invoice_number__startswith=salesman_code
#         ).order_by('-invoice_number').first()

#         if last_sale and last_sale.invoice_number:
#             # Extract the serial number (last part) and increment it
#             try:
#                 last_serial = int(last_sale.invoice_number.split('-')[-1])
#                 new_serial = last_serial + 1
#             except (IndexError, ValueError):
#                 new_serial = 1
#         else:
#             new_serial = 1

#         # Format the new invoice number: SALESMAN_CODE-SERIAL
#         invoice_number = f"{salesman_code}-{new_serial:04d}"

#         # --- Handle advance and payment: Always use advance first, then payment ---
#         total_due = due  # Amount that needs to be paid for this sale
#         advance_used = 0
#         payment_used = 0

#         if advance_amount >= total_due:
#             # Advance fully covers the due
#             advance_used = total_due
#             customer.Advance -= advance_used
#             payment_used = 0
#             due = 0
#         else:
#             # Use all advance, the rest from payment
#             advance_used = advance_amount
#             customer.Advance = 0
#             remaining_due = total_due - advance_used
#             if payment_received >= remaining_due:
#                 payment_used = remaining_due
#                 payment_received -= remaining_due
#                 due = 0
#             else:
#                 payment_used = payment_received
#                 due = remaining_due - payment_received
#                 payment_received = 0

#         # Update customer due and paid
#         customer.due = customer_due + due
#         customer.Paid += payment_used
#         customer.save()

#         # Update salesman commission
#         commission_amount = float(commission_rate / 100) * float(data.get('payment_received', 0))
#         salesman.salescomission += commission_amount
#         salesman.save()

#         # Update product stock and sales
#         for product in products_sold:
#             product_id = product.get('id')
#             quantity_sold = float(product.get('quantity', 0))
#             if product_id and quantity_sold:
#                 try:
#                     prod = Product.objects.get(id=product_id)
#                     prod.total_stock -= quantity_sold
#                     prod.total_sales += quantity_sold
#                     prod.save()
#                 except Product.DoesNotExist:
#                     continue

#         # Save sale record with correct less value and invoice number
#         sale = Sale.objects.create(
#             salesman=salesman,
#             customer=customer,
#             products=products_sold,
#             total_price=total_price,
#             discount=(discount_percent / 100) * total_price,
#             less=final_less,  # Save sum of all product less + less input
#             payment_received=payment_used,
#             due=due,
#             date=datetime.now().date(),
#             time=datetime.now().time(),
#             comission=commission_amount,
#             invoice_number=invoice_number  # Add the generated invoice number
#         )

#         # --- SMS Sending Section ---
#         try:
#             # Compose SMS message
#             msg = (
#                 f"Dear {customer_name},\n"
#                 f"Thank you for your purchase.\n"
#                 f"Invoice: {invoice_number}\n"  # Add invoice number to SMS
#                 f"Total: {total_price:.2f} Tk\n"
#                 f"Discount: {(discount_percent / 100) * total_price:.2f} Tk\n"
#                 f"Less: {final_less:.2f} Tk\n"
#                 f"Paid: {payment_used:.2f} Tk\n"
#                 f"Due: {due:.2f} Tk\n"
#                 f"- Rahmaniya Pump"
#             )
#             # Format phone number for SMS API (ensure country code)
#             phone = str(customer_phone)
#             payload = {
#                 'api_key': 'ld96r4ak7OfIQs3f1Ov4jlwvF7HwLVkLyHb7XW7i',
#                 'msg': msg,
#                 'to': phone
#             }
#             url = "https://api.sms.net.bd/sendsms"
#             response = requests.post(url, data=payload, timeout=10)
#             print("SMS API response:", response.text)
            
#         except Exception as sms_error:
#             print("SMS sending error:", sms_error)

#         return JsonResponse({'status': 'success', 'message': 'Sale data saved and SMS sent.'}, status=200)
#     else:
#         return JsonResponse({'error': 'POST request required.'}, status=400)


@csrf_exempt
def save_sale(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        
        sid = data.get('salesman')
        cid = data.get('customer')
        products_sold = data.get('products', [])
        total_price = float(data.get('total_price', 0))
        discount_percent = float(data.get('discount', 0))
        less_input = float(data.get('less', 0))
        payment_received = float(data.get('payment_received', 0))
        due = float(data.get('due', 0))

        # Validate required fields
        if not sid or not cid:
            return JsonResponse({'error': 'Salesman and Customer IDs are required.'}, status=400)

        # Validate products list
        if not products_sold or len(products_sold) == 0:
            return JsonResponse({'error': 'At least one product is required.'}, status=400)

        # --- CHECK PRODUCT STOCK FIRST (before any data modifications) ---
        for product in products_sold:
            product_id = product.get('id')
            quantity_sold = float(product.get('quantity', 0))
            
            if not product_id:
                return JsonResponse({'error': 'Product ID is required for all products.'}, status=400)
            
            if quantity_sold <= 0:
                return JsonResponse({'error': 'Product quantity must be greater than 0.'}, status=400)
            
            try:
                prod = Product.objects.get(id=product_id)
                if prod.total_stock <= 0:
                    return JsonResponse({'error': 'No product in stock', 'message': f'Product "{prod.name}" is out of stock.'}, status=400)
                if quantity_sold > prod.total_stock:
                    return JsonResponse({'error': 'Insufficient stock', 'message': f'Product "{prod.name}" has only {prod.total_stock} units in stock, but {quantity_sold} units were requested.'}, status=400)
            except Product.DoesNotExist:
                return JsonResponse({'error': 'Product not found', 'message': f'Product with ID {product_id} not found.'}, status=404)

        # Calculate total less from all products
        total_less_products = sum(float(p.get('less', 0)) for p in products_sold)
        # Final less is sum of all product less + less input
        final_less = total_less_products + less_input

        # Calculate due on backend (ignore due from frontend)
        discount_amount = (discount_percent / 100) * total_price
        sale_due = total_price - discount_amount-less_input
        if sale_due < 0:
            sale_due = 0

        # Get salesman
        try:
            salesman = Salesman.objects.get(id=sid)
            commission_rate = float(salesman.comission)
            salesman_name = salesman.name
            salesman_code = salesman.code
        except Salesman.DoesNotExist:
            return JsonResponse({'error': 'Salesman not found.'}, status=404)

        # Get customer and use calculated due/advance (initial + sales + adai)
        try:
            customer = Customer.objects.get(id=cid)
            customer_name = customer.name
            customer_phone = customer.phone
            _current_due, current_advance = get_customer_calculated_due_advance(customer)
            advance_amount = current_advance
        except Customer.DoesNotExist:
            return JsonResponse({'error': 'Customer not found.'}, status=404)
        except ValueError:
            return JsonResponse({'error': 'Invalid Customer ID.'}, status=400)

        # Generate invoice number
        last_sale = Sale.objects.filter(
            salesman=salesman,
            invoice_number__startswith=salesman_code
        ).order_by('-invoice_number').first()

        if last_sale and last_sale.invoice_number:
            try:
                last_serial = int(last_sale.invoice_number.split('-')[-1])
                new_serial = last_serial + 1
            except (IndexError, ValueError):
                new_serial = 1
        else:
            new_serial = 1

        invoice_number = f"{salesman_code}-{new_serial:04d}"

        # Use sale date from request or current date (accept 'sale_date' or 'saleDate')
        sale_date_str = (data.get('sale_date') or data.get('saleDate') or '').strip()
        if isinstance(sale_date_str, str) and len(sale_date_str) >= 10:
            try:
                sale_date = datetime.strptime(sale_date_str[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                sale_date = datetime.now().date()
        else:
            sale_date = datetime.now().date()
        sale_time = datetime.now().time()

        # --- Handle advance and payment: Only apply to this sale's due, not old due ---
        # sale_due is already calculated above
        advance_used = 0
        payment_used = 0

        # Only use advance if payment_received is not provided or is less than total_price
        if payment_received == 0 or payment_received < total_price:
            if advance_amount >= sale_due:
                advance_used = sale_due
                payment_used = 0
                sale_due = 0
            else:
                advance_used = advance_amount
                remaining_due = sale_due - advance_used
                if payment_received >= remaining_due:
                    payment_used = remaining_due
                    payment_received -= remaining_due
                    sale_due = 0
                else:
                    payment_used = payment_received
                    sale_due = remaining_due - payment_received
        else:
            if payment_received >= sale_due:
                payment_used = sale_due
                payment_received -= sale_due
                sale_due = 0
            else:
                payment_used = payment_received
                sale_due = sale_due - payment_received

        # Customer.due and Customer.Advance are initial only (not updated here). Only update Paid.
        customer.Paid += payment_used
        customer.save()

        # Commission is calculated from DB (sum of Sale.comission + Adai.sales_comission), so do not update salesman.salescomission here.
        commission_amount = float(commission_rate / 100) * payment_used

        # Update product stock and sales
        for product in products_sold:
            product_id = product.get('id')
            quantity_sold = float(product.get('quantity', 0))
            if product_id and quantity_sold:
                try:
                    prod = Product.objects.get(id=product_id)
                    prod.total_stock -= quantity_sold
                    prod.total_sales += quantity_sold
                    prod.save()
                except Product.DoesNotExist:
                    continue

        # Save sale record with correct less value and invoice number
        sale = Sale.objects.create(
            salesman=salesman,
            customer=customer,
            products=products_sold,
            total_price=total_price+final_less-less_input,
            discount=(discount_percent / 100) * total_price,
            less=final_less,  # final_less (unchangable)
            total_less_products=total_less_products,
            less_input=less_input,
            payment_received=float(data.get('payment_received', 0)),
            advance_used=advance_used,
            due=sale_due,
            date=sale_date,
            time=sale_time,
            comission=commission_amount,
            invoice_number=invoice_number
        )

        # --- SMS Sending Section ---
        try:
            msg = (
                f"Dear {customer_name},\n"
                f"Thank you for your purchase.\n"
                f"Invoice: {invoice_number}\n"
                f"Total: {total_price:.2f} Tk\n"
                f"Discount: {(discount_percent / 100) * total_price:.2f} Tk\n"
                f"Less: {final_less:.2f} Tk\n"
                f"Paid: {payment_used:.2f} Tk\n"
                f"Due: {sale_due:.2f} Tk\n"
                f"- Rahmaniya Pump"
            )
            phone = str(customer_phone)
            payload = {
                'api_key': 'ld96r4ak7OfIQs3f1Ov4jlwvF7HwLVkLyHb7XW7i',
                'msg': msg,
                'to': phone
            }
            url = "https://api.sms.net.bd/sendsms"
            response = requests.post(url, data=payload, timeout=10)
        except Exception as sms_error:
            pass

        return JsonResponse({'status': 'success', 'message': 'Sale data saved and SMS sent.'}, status=200)
    else:
        return JsonResponse({'error': 'POST request required.'}, status=400)

def all_sales(request):
    sales_data = []
    selected_month = None
    selected_year = None
    selected_salesman = None

    if request.method == 'POST':
        # Get the selected salesman, month, and year from the form
        selected_salesman = request.POST.get('salesman')
        selected_month = int(request.POST.get('month'))
        selected_year = int(request.POST.get('year'))

        # Start with base query
        sales_query = Sale.objects.all()

        # Apply filters
        if selected_salesman:
            sales_query = sales_query.filter(salesman_id=selected_salesman)
        if selected_month and selected_year:
            sales_query = sales_query.filter(date__year=selected_year, date__month=selected_month)

        sales = sales_query
    else:
        # Default: Show all sales if no filter is applied
        sales = Sale.objects.all().order_by('-date')

    for sale in sales:
        sales_data.append({
            'id': sale.id,
            'salesman': sale.salesman.name if sale.salesman else '',
            'customer': sale.customer.name if sale.customer else '',
            'products': sale.products,
            'total_price': (sale.total_price),
            'discount': sale.discount,
            'less': sale.less,
            'payment_received': sale.payment_received,
            'due': sale.due,
            'date': sale.date.strftime('%Y-%m-%d') if sale.date else '',
            'time': sale.time.strftime('%H:%M:%S') if sale.time else '',
            'comission': sale.comission,
            'invoice_number': sale.invoice_number if sale.invoice_number else 'N/A',
            'advance_used': float(sale.advance_used or 0),
        })

    # Get all salesmen for the filter dropdown
    salesmen = Salesman.objects.all()

    # Pass months and years for the filter dropdown
    context = {
        'sales': sales_data,
        'salesmen': salesmen,
        'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
        'years': range(2020, 2031),
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_salesman': selected_salesman
    }
    return render(request, 'All_sales.html', context)

def all_orders(request):
    """View to display all orders"""
    orders = Order.objects.all()
    return render(request, 'order.html', {'orders': orders})

@csrf_exempt
def export_all_sales_excel(request):
    """Export all sales data to Excel file with filters"""
    try:
        # Get filter parameters (same as all_sales view)
        selected_month = request.GET.get('month')
        selected_year = request.GET.get('year')
        selected_salesman = request.GET.get('salesman')
        
        # Start with base query
        sales_query = Sale.objects.all()
        
        # Apply filters (same logic as all_sales)
        if selected_salesman:
            sales_query = sales_query.filter(salesman_id=selected_salesman)
        if selected_month and selected_year:
            sales_query = sales_query.filter(date__year=int(selected_year), date__month=int(selected_month))
        
        sales = sales_query.order_by('-date', '-time')
        
        # Prepare data for Excel
        excel_data = []
        for sale in sales:
            # Format products as string
            products_str = ""
            if sale.products:
                product_list = []
                for product in sale.products:
                    product_name = product.get('name', '')
                    quantity = product.get('quantity', 0)
                    price = product.get('price', 0)
                    product_list.append(f"{product_name} (Qty: {quantity}, Price: {price})")
                products_str = "; ".join(product_list)
            
            excel_data.append({
                'Invoice Number': sale.invoice_number if sale.invoice_number else 'N/A',
                'Date': sale.date.strftime('%Y-%m-%d') if sale.date else '',
                'Time': sale.time.strftime('%H:%M:%S') if sale.time else '',
                'Salesman': sale.salesman.name if sale.salesman else '',
                'Customer': sale.customer.name if sale.customer else '',
                'Products': products_str,
                'Total Price': float(sale.total_price or 0),
                'Discount': float(sale.discount or 0),
                'Less': float(sale.less or 0),
                'Net Amount': float((sale.total_price or 0) - (sale.discount or 0) - (sale.less or 0)),
                'Payment Received': float(sale.payment_received or 0),
                'Due': float(sale.due or 0),
                'Commission': float(sale.comission or 0),
            })
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='All Sales')
        
        # Prepare response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
        # Generate filename with filters
        filename_parts = ['sales_export']
        if selected_salesman:
            try:
                salesman = Salesman.objects.get(id=selected_salesman)
                filename_parts.append(salesman.name.replace(' ', '_'))
            except:
                pass
        if selected_month and selected_year:
            filename_parts.append(f"{int(selected_year)}_{int(selected_month):02d}")
        filename_parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
        
        response['Content-Disposition'] = f'attachment; filename="{"_".join(filename_parts)}.xlsx"'
        
        return response
    except Exception as e:
        messages.error(request, f'Error exporting sales: {str(e)}')
        return redirect('all_sales')

@csrf_exempt
def delete_sale(request, sale_id):
    if request.method == 'POST':  # Only allow POST requests
        try:
            with transaction.atomic():
                # Get the sale and related objects
                sale = Sale.objects.get(id=sale_id)
                customer = sale.customer
                salesman = sale.salesman
                
                
                # Get the original amounts
                original_due = float(sale.due or 0)
                original_paid = float(sale.payment_received or 0)
                original_commission = float(sale.comission or 0)
                
                # Update customer: only reverse Paid (Customer.due/Advance are initial-only, not updated)
                if customer:
                    customer.Paid -= original_paid
                    customer.Paid = max(0, customer.Paid)
                    customer.save()

                # Update salesman
                if salesman:
                    
                    salesman.salescomission -= original_commission
                    salesman.save()
                   
                
                # Restore product quantities before deleting the sale
                if sale.products:
                    for product_data in sale.products:
                        product_id = product_data.get('id')
                        quantity_sold = float(product_data.get('quantity', 0))
                        if product_id and quantity_sold:
                            try:
                                prod = Product.objects.get(id=product_id)
                                # Restore stock (add back the quantity that was sold)
                                prod.total_stock += quantity_sold
                                # Reduce total sales (subtract the quantity that was sold)
                                prod.total_sales -= quantity_sold
                                # Ensure total_sales doesn't go negative
                                if prod.total_sales < 0:
                                    prod.total_sales = 0
                                prod.save()
                            except Product.DoesNotExist:
                                continue
                
                # Delete the sale (customer due/advance are calculated from sales+adai, no recalculation needed)
                sale.delete()
                messages.success(request, "Sale deleted successfully!")
        except Sale.DoesNotExist:
            print(f"Sale {sale_id} not found")
            messages.error(request, "Sale not found!")
        except Exception as e:
            
            messages.error(request, f"Error deleting sale: {e}")
    else:
        print(f"Invalid request method: {request.method}")
        messages.error(request, "Invalid request method. Use POST to delete.")
    
    return redirect('all_sales')


async def generate_pdf_async(html_content):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
              executable_path=str("ms-playwright/chromium-1117/chrome-win"),
              args=["--no-sandbox"]
          )
        # browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_content)
        pdf = await page.pdf()
        await browser.close()
        return pdf


from django.shortcuts import get_object_or_404

# def download_cash_memo(request, sale_id):
#     try:
#         # Get sale data from Django ORM
#         sale = get_object_or_404(Sale, id=sale_id)
#         customer = sale.customer
#         salesman = sale.salesman

#         # Calculate previous due (customer.due before this sale)
#         # previous_due = customer's due before this bill
#         previous_due = (customer.due or 0) - (sale.due or 0)
#         # Total due for this bill = previous due + this bill's due
#         total_due = previous_due + (sale.due or 0)

#         # Calculate net bill
#         net_bill = (sale.total_price or 0)

#         # Prepare products list (if you store as JSON, otherwise adjust as needed)
#         products = sale.products if hasattr(sale, 'products') else []

#         context = {
#             'sale': sale,
#             'salesman': salesman,
#             'customer': customer,
#             'total_bill':(sale.total_price or 0)+(sale.discount or 0)+(sale.less or 0),
#             'products': products,
#             'net_bill': net_bill,
#             'total_due': total_due,
#             'previous_due': previous_due,
#             'customer_advance': customer.Advance or 0,
#         }

#         html_string = render_to_string('Memo.html', context)
#         return HttpResponse(html_string, content_type='text/html')

#     except Exception as e:
#         return HttpResponse(f"Error generating HTML memo: {str(e)}", status=500)

def download_cash_memo(request, sale_id):
    try:
        # Get sale data from Django ORM
        sale = get_object_or_404(Sale, id=sale_id)
        customer = sale.customer
        salesman = sale.salesman
        

        # Use calculated due; previous_due = current calculated due minus this sale's due
        current_due, current_adv = get_customer_calculated_due_advance(customer)
        previous_due = current_due - (sale.due or 0)
        if previous_due < 0:
            previous_due = 0
        total_due = previous_due + (sale.due or 0)
        print("due bole dao:", total_due)

        # Net sale = same as get_sale_net_amount (total - discount - effective_less)
        net_bill = get_sale_net_amount(sale)
        mot_bill = sale.total_price
        total_less_per_unit = 0
        who_less = 0
        if sale.products:
            for item in sale.products:
                lp = float(item.get('lessPerUnit', 0) or 0)
                qty = float(item.get('quantity', 0) or 0)
                total_less_per_unit += lp * qty
                if lp > 0:
                    who_less += 1
        effective_less = (float(sale.less or 0) - total_less_per_unit) if who_less > 0 else float(sale.less or 0)

        products = sale.products if hasattr(sale, 'products') else []

        context = {
            'sale': sale,
            'mot_bill': mot_bill,
            'salesman': salesman,
            'customer': customer,
            'products': products,
            'net_bill': net_bill,
            'total_due': current_due,
            'previous_due': previous_due,
            'customer_advance': current_adv or 0,
            'less': effective_less,
        }

        html_string = render_to_string('Memo.html', context)
        return HttpResponse(html_string, content_type='text/html')

    except Exception as e:
        return HttpResponse(f"Error generating HTML memo: {str(e)}", status=500)
def stockaddjust(request):
    # Retrieve products from the Product model
    products = Product.objects.all()
    products_data = [
        {
            'id': product.id,
            'code': product.code,
            'name': product.name,
            'full_name': f"{product.code} - {product.name} ({product.size})",
            'rate': product.rate,
            'size': product.size,
            'total_stock': product.total_stock,
            # Add other fields as needed
        }
        for product in products
    ]
    context = {
        'products': products_data,
    }
    
    return render(request, 'stockadd.html', context)

@csrf_exempt
def update_stock(request):
    """Handle stock updates for selected product (JSON version) and send SMS on update"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            product_id = data.get('product_id')
            quantity = data.get('quantity')
            

            # Validate inputs
            if not product_id or not quantity:
                return JsonResponse({'status': 'error', 'error': 'Missing required fields'})

            quantity = int(quantity)
            if quantity <= 0:
                return JsonResponse({'status': 'error', 'error': 'Quantity must be positive'})

            # Update stock in the Product model
            try:
                product = Product.objects.get(id=product_id)
                product.total_stock += quantity
                product.save()
            except Product.DoesNotExist:
                return JsonResponse({'status': 'error', 'error': 'Product not found'})

            # --- SMS Sending Section ---
            try:
                # Compose SMS message
                msg = (
                    f"Stock Updated!\n"
                    f"Product: {product.name}\n"
                    f"Added: {quantity}\n"
                    f"Current Stock: {product.total_stock}\n"
                    f"- Rahmaniya Pump"
                )
                # Set your admin/manager phone number here (must be in 8801XXXXXXXXX format)
                admin_phone = "01857333003"  # Change to your admin/manager number
                payload = {
                    'api_key': 'ld96r4ak7OfIQs3f1Ov4jlwvF7HwLVkLyHb7XW7i',
                    'msg': msg,
                    'to': admin_phone
                }
                url = "https://api.sms.net.bd/sendsms"
                response = requests.post(url, data=payload, timeout=10)
               
            except Exception as sms_error:
                print("SMS sending error:", sms_error)

            return JsonResponse({'status': 'success'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})
def salesaddjust(request):
    # Retrieve salesmen from the Salesman model
    salesman_data = [
        {
            'id': salesman.id,
            'name': salesman.name,
            'code': salesman.code,
            'area': salesman.area,
            # Add other fields as needed
        }
        for salesman in Salesman.objects.all()
    ]

    # Filter customers by selected salesman (like pos_dashboard)
    selected_salesman_id = request.GET.get('salesman') or request.POST.get('salesman')
    if selected_salesman_id:
        try:
            selected_salesman = Salesman.objects.get(id=selected_salesman_id)
            code_range = selected_salesman.code
            if '-' in code_range:
                start_code, end_code = code_range.split('-')
                try:
                    start_code = int(start_code)
                    end_code = int(end_code)
                    filtered_customers = [
                        c for c in Customer.objects.all()
                        if c.code.isdigit() and start_code <= int(c.code) <= end_code
                    ]
                except ValueError:
                    filtered_customers = Customer.objects.none()
            else:
                filtered_customers = Customer.objects.none()
        except Salesman.DoesNotExist:
            filtered_customers = Customer.objects.none()
    else:
        filtered_customers = Customer.objects.all()

    customers_data = [
        {
            'id': customer.id,
            'name': customer.name,
            'code': customer.code,
            'area': customer.area,
            # Add other fields as needed
        }
        for customer in filtered_customers
    ]

    # Retrieve adai records from the Adai model
    adai_data = [
        {
            'id': adai.id,
            'salesman': adai.salesman.name if adai.salesman else '',
            'customer': adai.customer.name if adai.customer else '',
            'due': adai.due,
            'advance': adai.advance,
            'date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
            'sales_comission': adai.sales_comission,
            # Add other fields as needed
        }
        for adai in Adai.objects.all().order_by('-date')
    ]

    context = {
        'salesman': salesman_data,    # Each salesman should include a 'name' field
        'customers': customers_data,  # Each customer should include a 'name' field
        'adai': adai_data,
    }
    
    return render(request, 'addsales.html', context)

@csrf_exempt
def export_adai_excel(request):
    """Export all Adai records to Excel file"""
    try:
        # Get all Adai records
        adai_records = Adai.objects.all().order_by('-date')
        
        # Prepare data for Excel
        excel_data = []
        for adai in adai_records:
            excel_data.append({
                'Invoice Number': adai.invoice_number if adai.invoice_number else 'N/A',
                'Date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
                'Salesman': adai.salesman.name if adai.salesman else '',
                'Customer': adai.customer.name if adai.customer else '',
                'Due': float(adai.due or 0),
                'Advance': float(adai.advance or 0),
                'Sales Commission': float(adai.sales_comission or 0),
            })
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Adai Records')
        
        # Prepare response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="adai_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        
        return response
    except Exception as e:
        messages.error(request, f'Error exporting Adai records: {str(e)}')
        return redirect('salesaddjust')

@csrf_exempt
def delete_adai(request, adai_id):
    if request.method == 'POST':
        try:
            # Fetch the Adai record to get advance, due, customer, and salesman details
            adai = Adai.objects.get(id=adai_id)
            advance_amount = float(adai.advance or 0)
            due_amount = float(adai.due or 0)
            customer = adai.customer
            salesman = adai.salesman

            # Customer.due/Advance are calculated from sales+adai; do not update them here.
            if salesman:
                salesman.salescomission -= float(adai.sales_comission or 0)
                if salesman.salescomission < 0:
                    salesman.salescomission = 0
                salesman.save()

            adai.delete()
            return redirect('salesaddjust')
        except Adai.DoesNotExist:
            # Always redirect after POST, even if record not found
            return redirect('salesaddjust')
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})



@csrf_exempt
def update_sales(request):
    """Handle due/advance updates for a customer and record Adai (JSON version)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            customer_id = data.get('product_id')
            salesman_id = data.get('salesmanname')
            dashboard_date_str = data.get('date')
            quantity = float(data.get('quantity', 0))
            money_type = data.get('money_type')

            # Validate inputs
            if not customer_id or not salesman_id or not quantity:
                return JsonResponse({'status': 'error', 'error': 'Missing required fields'})

            quantity = float(quantity)
            if quantity <= 0:
                return JsonResponse({'status': 'error', 'error': 'Quantity must be positive'})

            # Retrieve customer and salesman
            try:
                customer = Customer.objects.get(id=customer_id)
            except Customer.DoesNotExist:
                return JsonResponse({'status': 'error', 'error': 'Customer not found'})

            try:
                salesman = Salesman.objects.get(id=salesman_id)
            except Salesman.DoesNotExist:
                return JsonResponse({'status': 'error', 'error': 'Salesman not found'})

            commission_rate = float(salesman.comission)
            adai_date = datetime.strptime(dashboard_date_str, "%Y-%m-%d").date() if dashboard_date_str else datetime.now().date()

            current_due, current_advance = get_customer_calculated_due_advance(customer)

            from django.db import transaction
            with transaction.atomic():
                if int(money_type) == 1:  # Handling 'Due' (customer pays due)
                    if current_due <= 0:
                        return JsonResponse({'status': 'error', 'error': 'Customer has no due to update.'})
                    if quantity >= current_due:
                        advance_to_add = quantity - current_due
                        paid_due = current_due
                    else:
                        paid_due = quantity
                        advance_to_add = 0

                    adai = Adai.objects.create(
                        due=paid_due,
                        advance=advance_to_add,
                        date=adai_date,
                        salesman=salesman,
                        customer=customer,
                        sales_comission=(commission_rate / 100) * quantity
                    )

                else:  # Handling 'Advance'
                    if current_due > 0:
                        return JsonResponse({'status': 'error', 'error': 'Please clear due first.'})
                    adai = Adai.objects.create(
                        due=0,
                        advance=quantity,
                        date=adai_date,
                        salesman=salesman,
                        customer=customer,
                        sales_comission=(commission_rate / 100) * quantity
                    )

                commission_amount = (commission_rate / 100) * quantity
                # Commission is calculated from DB (Sale.comission + Adai.sales_comission), so do not update salesman.salescomission here.

                # Return updated calculated due/advance (from sales+adai)
                new_due, new_advance = get_customer_calculated_due_advance(customer)
                return JsonResponse({
                    'status': 'success',
                    'message': 'Transaction completed successfully',
                    'details': {
                        'customer_due': new_due,
                        'customer_advance': new_advance,
                        'commission_added': commission_amount
                    }
                })

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'error': 'Invalid JSON data'}, status=400)
        except ValueError as ve:
            return JsonResponse({'status': 'error', 'error': str(ve)}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
def update_adai(request, adai_id):
    if request.method == 'POST':
        try:
            # Parse the updated data from the request
            data = json.loads(request.body)
            new_due = data.get('due')  # Keep as None if not provided
            new_advance = data.get('advance')  # Keep as None if not provided

            # Ensure `due` and `advance` are numbers
            new_due = float(new_due) if new_due is not None else None
            new_advance = float(new_advance) if new_advance is not None else None

            # Fetch the existing adai record
            adai = Adai.objects.get(id=adai_id)
            old_due = float(adai.due or 0)
            old_advance = float(adai.advance or 0)
            customer = adai.customer
            salesman = adai.salesman

            if not customer or not salesman:
                return JsonResponse({'status': 'error', 'message': 'Customer or Salesman not found.'})

            due_difference = (new_due - old_due) if new_due is not None else 0
            advance_difference = (new_advance - old_advance) if new_advance is not None else 0

            if due_difference > 0:
                current_due, _ = get_customer_calculated_due_advance(customer)
                if current_due < due_difference:
                    return JsonResponse({'status': 'error', 'message': 'Customer due cannot be negative.'})

            # Customer.due/Advance are initial-only; do not update here.

            commission_rate = float(salesman.comission or 0)
            commission_difference_due = (commission_rate / 100) * due_difference
            commission_difference_advance = (commission_rate / 100) * advance_difference
            total_commission_difference = commission_difference_due + commission_difference_advance
            if total_commission_difference != 0:
                salesman.salescomission += total_commission_difference
                salesman.save()

            # Update the adai record with the new values (only update provided fields)
            if new_due is not None:
                adai.due = new_due
            if new_advance is not None:
                adai.advance = new_advance

            # Update the sales_comission in the adai record
            adai.sales_comission = float(adai.sales_comission or 0) + total_commission_difference
            adai.save()

            return JsonResponse({'status': 'success', 'message': 'Adai, customer, and salesman data updated successfully.'})
        except Adai.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Adai record not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

@csrf_exempt
def update_adai(request, adai_id):
    if request.method == 'POST':
        try:
            # Parse the updated data from the request
            data = json.loads(request.body)
            new_due = data.get('due')  # Keep as None if not provided
            new_advance = data.get('advance')  # Keep as None if not provided

            # Ensure `due` and `advance` are numbers
            new_due = float(new_due) if new_due is not None else None
            new_advance = float(new_advance) if new_advance is not None else None

            # Fetch the existing adai record
            adai = Adai.objects.get(id=adai_id)
            old_due = float(adai.due or 0)
            old_advance = float(adai.advance or 0)
            customer = adai.customer
            salesman = adai.salesman

            if not customer or not salesman:
                return JsonResponse({'status': 'error', 'message': 'Customer or Salesman not found.'})

            due_difference = (new_due - old_due) if new_due is not None else 0
            advance_difference = (new_advance - old_advance) if new_advance is not None else 0

            if due_difference > 0:
                current_due, _ = get_customer_calculated_due_advance(customer)
                if current_due < due_difference:
                    return JsonResponse({'status': 'error', 'message': 'Customer due cannot be negative.'})

            # Customer.due/Advance are initial-only; do not update here.

            commission_rate = float(salesman.comission or 0)
            commission_difference_due = (commission_rate / 100) * due_difference
            commission_difference_advance = (commission_rate / 100) * advance_difference
            total_commission_difference = commission_difference_due + commission_difference_advance
            if total_commission_difference != 0:
                salesman.salescomission += total_commission_difference
                salesman.save()

            # Update the adai record with the new values (only update provided fields)
            if new_due is not None:
                adai.due = new_due
            if new_advance is not None:
                adai.advance = new_advance

            # Update the sales_comission in the adai record
            adai.sales_comission = float(adai.sales_comission or 0) + total_commission_difference
            adai.save()

            return JsonResponse({'status': 'success', 'message': 'Adai, customer, and salesman data updated successfully.'})
        except Adai.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Adai record not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})



@csrf_exempt
def transaction_list(request):
    if request.method == 'POST':
        # Check if this is a new bank account creation
        if 'bank_name' in request.POST:
            # Creating a new bank account
            bank_name = request.POST.get('bank_name')
            branch_name = request.POST.get('branch_name')
            account_number = request.POST.get('account_number')
            opening_balance = float(request.POST.get('opening_balance', 0))
            
            if bank_name and branch_name and account_number:
                # Create new bank account
                bank_account = BankAccount.objects.create(
                    bank_name=bank_name,
                    branch_name=branch_name,
                    account_number=account_number,
                    opening_balance=opening_balance,
                    current_balance=opening_balance
                )
                messages.success(request, 'Bank account created successfully!')
        else:
            # Adding a new transaction
            bank_account_id = request.POST.get('bank_account')
            date = request.POST.get('transactionDate')
            narration = request.POST.get('narration')
            transaction_type = request.POST.get('transaction_type')
            amount = float(request.POST.get('amount', 0))
            
            if bank_account_id and date and narration and transaction_type and amount:
                try:
                    bank_account = BankAccount.objects.get(id=bank_account_id)
                    Transaction.objects.create(
                        bank_account=bank_account,
                        date=date,
                        narration=narration,
                        transaction_type=transaction_type,
                        amount=amount
                    )
                    messages.success(request, 'Transaction added successfully!')
                except BankAccount.DoesNotExist:
                    messages.error(request, 'Bank account not found!')
            
        return redirect('transaction_list')
    
    # Get filter parameters
    selected_bank = request.GET.get('ledger_bank')
    selected_month = request.GET.get('ledger_month')
    selected_year = request.GET.get('ledger_year')

    # Filter transactions for ledger
    ledger_transactions = None
    if selected_bank and selected_month and selected_year:
        ledger_transactions = Transaction.objects.filter(
            bank_account_id=selected_bank,
            date__year=selected_year,
            date__month=selected_month
        ).order_by('date')
    
    # Fetch all bank accounts and their transactions
    bank_accounts = BankAccount.objects.all()
    transactions = Transaction.objects.all().order_by('-date')
    
    # Generate month and year options
    months = [
        {'number': 1, 'name': 'January'},
        {'number': 2, 'name': 'February'},
        {'number': 3, 'name': 'March'},
        {'number': 4, 'name': 'April'},
        {'number': 5, 'name': 'May'},
        {'number': 6, 'name': 'June'},
        {'number': 7, 'name': 'July'},
        {'number': 8, 'name': 'August'},
        {'number': 9, 'name': 'September'},
        {'number': 10, 'name': 'October'},
        {'number': 11, 'name': 'November'},
        {'number': 12, 'name': 'December'}
    ]
    years = range(2020, datetime.now().year + 1)
    
    context = {
        'bank_accounts': bank_accounts,
        'transactions': transactions,
        'ledger_transactions': ledger_transactions,
        'selected_bank': selected_bank,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months': months,
        'years': years
    }
    return render(request, 'bankinfo.html', context)

@csrf_exempt
def delete_transaction(request, transaction_id):
    if request.method == 'POST':
        try:
            transaction = Transaction.objects.get(id=transaction_id)
            # Reverse the transaction's effect on the bank account balance
            bank_account = transaction.bank_account
            if transaction.transaction_type == 'debit':
                bank_account.current_balance = float(bank_account.current_balance) + float(transaction.amount)
            else:  # credit
                bank_account.current_balance = float(bank_account.current_balance) - float(transaction.amount)
            bank_account.save()
            
            # Delete the transaction
            transaction.delete()
            messages.success(request, 'Transaction deleted successfully!')
        except Transaction.DoesNotExist:
            messages.error(request, 'Transaction not found!')
    return redirect('transaction_list')

@csrf_exempt
def salesmanpayment(request):
    if request.method == 'POST':
        # Adding a new salesman
        name = request.POST.get('name')
        code = request.POST.get('code')
        area = request.POST.get('area')
        phone = request.POST.get('phone')
        nid = request.POST.get('nid')
        comission = float(request.POST.get('comission')) if request.POST.get('comission') else 0.0
        totalcomission = float(request.POST.get('totalcomission')) if request.POST.get('totalcomission') else 0.0
        
        if name and code and area and phone and nid:
            Salesman.objects.create(
                name=name,
                code=code,
                area=area,
                phone=phone,
                nid=nid,
                comission=comission,
                salescomission=totalcomission
            )
            return redirect('salesman_list')

    # Fetching all salesmen
    salesmen_list = Salesman.objects.all()
    return render(request, 'Salesman.html', {'salesmen': salesmen_list})

@csrf_exempt
def delete_salesmanpayment(request, salesman_id):
    if request.method == 'POST':
        try:
            salesman = Salesman.objects.get(id=salesman_id)
            salesman.delete()
        except Salesman.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('salesman_list')
    
    
def salespayjust(request):
    salesmen = Salesman.objects.all()
    now = datetime.now()
    sales_data = []
    for salesman in salesmen:
        # Sum salary payments for current month
        month_salary_paid = SalesmanSalaryPayment.objects.filter(
            salesman=salesman,
            date__year=now.year,
            date__month=now.month
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        sales_data.append({
            'id': salesman.id,
            'name': salesman.name,
            'code': salesman.code,
            'area': salesman.area,
            'phone': salesman.phone,
            'nid': salesman.nid,
            'comission': salesman.comission,
            'salescomission': salesman.salescomission,
            'Due': salesman.Due,
            'Paid': salesman.Paid,
            'basic_salary': getattr(salesman, 'basic_salary', 0),
            'month_salary_paid': month_salary_paid,
        })
    context = {
        'salesman': sales_data,
    }
   
    return render(request, 'salesmanpayment.html', context)


@csrf_exempt
def salesman_pay(request):
    """Handle commission or salary payment for a salesman (JSON version)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            salesman_id = data.get('product_id')
            quantity = float(data.get('quantity', 0))
            payment_type = data.get('payment_type', 'commission')
            date_str = data.get('date')
            from datetime import datetime
            payment_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now().date()

            # Validate inputs
            if not salesman_id or not quantity:
                return JsonResponse({'status': 'error', 'error': 'Missing required fields'})
            if quantity <= 0:
                return JsonResponse({'status': 'error', 'error': 'Quantity must be positive'})

            # Update salesman's commission or salary
            try:
                salesman = Salesman.objects.get(id=salesman_id)
                if payment_type == 'salary':
                    # Save salary payment
                    SalesmanSalaryPayment.objects.create(
                        salesman=salesman,
                        amount=quantity,
                        date=payment_date
                    )
                    return JsonResponse({'status': 'success'})
                else:
                    # Commission payment (existing logic)
                    if salesman.salescomission >= quantity:
                        salesman.salescomission -= quantity
                        salesman.Paid += quantity
                        salesman.save()
                        return JsonResponse({'status': 'success'})
                    else:
                        return JsonResponse({'status': 'error', 'error': 'Insufficient commission to pay.'})
            except Salesman.DoesNotExist:
                return JsonResponse({'status': 'error', 'error': 'Salesman not found'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})



@csrf_exempt
def expence_list(request):
    if request.method == 'POST':
        # Create a new supplier with initial due or advance
        date = request.POST.get('transactionDate')
        suplier = request.POST.get('suplier')
        debit = float(request.POST.get('debit') or 0)  # Due
        credit = float(request.POST.get('credit') or 0) # Advance
        # Only create if supplier does not exist
        if suplier and not Expence.objects.filter(suplier=suplier).exists():
            from datetime import datetime
            Expence.objects.create(
                date=date if date else datetime.now().date(),
                narration="Initial Balance",
                due=debit,
                advance=credit,
                total_pay=0,
                suplier=suplier
            )
        return redirect('expence_list')

    # Fetch all unique suppliers and calculate their running balances
    suppliers = Expence.objects.values_list('suplier', flat=True).distinct()
    expence_list_data = []
    
    for supplier in suppliers:
        if not supplier:
            continue
            
        # Get all expenses for this supplier
        expenses = Expence.objects.filter(suplier=supplier)
        
        # Calculate sum of all advance and due
        total_advance = sum(e.advance for e in expenses)
        total_due = sum(e.due for e in expenses)
        
        # Net balance = Advance - Due
        net_balance = total_advance - total_due
        
        if net_balance > 0:
            current_advance = net_balance
            current_due = 0
        else:
            current_advance = 0
            current_due = abs(net_balance)
            
        expence_list_data.append({
            'suplier': supplier,
            'advance': current_advance,
            'due': current_due,
        })
        
    return render(request, 'expence_list.html', {'expence_list': expence_list_data})
    
@csrf_exempt
def delete_supplier(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            supplier_name = data.get('name')
            if not supplier_name:
                return JsonResponse({'status': 'error', 'error': 'Supplier name is required'})
            # Delete all expenses associated with this supplier name
            Expence.objects.filter(suplier=supplier_name).delete()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})

@csrf_exempt
def update_supplier(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            supplier_name = data.get('original_name')  # name from request body, not URL (avoids slash/encoding issues)
            new_name = data.get('name')
            new_due = float(data.get('due', 0))
            new_advance = float(data.get('advance', 0))

            if not supplier_name:
                return JsonResponse({'status': 'error', 'error': 'Original supplier name is required'})
            if not new_name:
                return JsonResponse({'status': 'error', 'error': 'Supplier name is required'})

            # If name changed, update all existing records
            if new_name != supplier_name:
                Expence.objects.filter(suplier=supplier_name).update(suplier=new_name)
                # Use the new name for the rest of the operations
                supplier_name = new_name

            # Calculate current aggregate due and advance
            expenses = Expence.objects.filter(suplier=supplier_name)
            total_advance_current = sum(e.advance for e in expenses)
            total_due_current = sum(e.due for e in expenses)
            
            # Net balance logic: 
            # If net > 0, it means we have overall advance.
            # If net < 0, it means we have overall due.
            net_balance_current = total_advance_current - total_due_current
            net_balance_new = new_advance - new_due

            difference = net_balance_new - net_balance_current
            
            if difference != 0:
                # Add an adjustment expense to reconcile the sum
                adjustment_advance = difference if difference > 0 else 0
                adjustment_due = abs(difference) if difference < 0 else 0
                
                from datetime import datetime
                Expence.objects.create(
                    suplier=supplier_name,
                    date=datetime.now().date(),
                    narration="Balance Adjustment from Edit",
                    advance=adjustment_advance,
                    due=adjustment_due,
                    total_pay=0
                )

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})


@csrf_exempt
def delete_expence(request, transaction_id):
    if request.method == 'POST':
        try:
            expence = Expence.objects.get(id=transaction_id)
            expence.delete()
        except Expence.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('expence_list')

@csrf_exempt
def add_expence(request):
    """
    - GET: Show form with unique supplier list.
    - POST (JSON): Add due/advance for selected supplier (must exist).
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            suplier = data.get('suplier')
            date = data.get('date')
            narration = data.get('narration', '')
            amount = float(data.get('amount', 0))
            money_type = int(data.get('money_type', 0))

            if not suplier or not date or not amount or not money_type:
                return JsonResponse({'status': 'error', 'error': 'Missing required fields'})

            # Only allow if supplier exists
            if not Expence.objects.filter(suplier=suplier).exists():
                return JsonResponse({'status': 'error', 'error': 'Supplier does not exist. Please create in Expense List.'})

            due = amount if money_type == 1 else 0
            advance = amount if money_type == 2 else 0

            Expence.objects.create(
                suplier=suplier,
                date=date,
                narration=narration,
                due=due,
                advance=advance,
                total_pay=0
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    # GET: Show unique supplier list for dropdown
    suplier_list = Expence.objects.values_list('suplier', flat=True).distinct()
    expence_list = Expence.objects.all().order_by('-date')
    return render(request, 'add_expence.html', {
        'expence_list': expence_list,
        'suplier_list': suplier_list,
    })

@csrf_exempt
def update_expence(request, expence_id):
    """
    Update an expense record by ID (for editing from modal).
    Accepts JSON with any of: suplier, narration, due, advance, total_pay, date.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            expence = Expence.objects.get(id=expence_id)
            # Update only provided fields
            if 'due' in data and data['due'] is not None:
                expence.due = float(data['due'])
            if 'advance' in data and data['advance'] is not None:
                expence.advance = float(data['advance'])
            if 'total_pay' in data and data['total_pay'] is not None:
                expence.total_pay = float(data['total_pay'])
            if 'narration' in data and data['narration'] is not None:
                expence.narration = data['narration']
            if 'suplier' in data and data['suplier'] is not None:
                expence.suplier = data['suplier']
            if 'date' in data and data['date'] is not None:
                expence.date = data['date']
            expence.save()
            return JsonResponse({'status': 'success', 'message': 'Expense updated successfully.'})
        except Expence.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Expense record not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

@csrf_exempt
def filter_sales(request):
    """Salesman report: filter by salesman and period (all_time, last_month, custom month). Uses GET."""
    today = datetime.now().date()
    current_year = today.year
    months = [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)]
    years = list(range(current_year, current_year - 11, -1))
    salesmen_list = [{'id': s.id, 'name': s.name} for s in Salesman.objects.all()]

    # Parse GET params (or use defaults for initial load)
    salesman_id = request.GET.get('salesman')
    period = (request.GET.get('period') or 'all_time').strip().lower()
    filter_year = None
    filter_month = None
    selected_month = today.month
    selected_year = current_year

    if period == 'last_month':
        if today.month == 1:
            filter_year = today.year - 1
            filter_month = 12
        else:
            filter_year = today.year
            filter_month = today.month - 1
        selected_month = filter_month
        selected_year = filter_year
    elif period == 'custom':
        try:
            my = request.GET.get('month')
            yr = request.GET.get('year')
            if my and yr:
                filter_month = int(my)
                filter_year = int(yr)
                if 1 <= filter_month <= 12 and filter_year >= 2000:
                    selected_month = filter_month
                    selected_year = filter_year
                else:
                    period = 'all_time'
                    filter_month = filter_year = None
            else:
                period = 'all_time'
        except (ValueError, TypeError):
            period = 'all_time'
            filter_month = filter_year = None

    # Period label for display
    if period == 'all_time':
        period_label = 'All time'
    elif period == 'last_month':
        period_label = f'Last month ({calendar.month_name[filter_month]} {filter_year})'
    else:
        period_label = f'{calendar.month_name[selected_month]} {selected_year}'

    # If no salesman selected, return form only
    if not salesman_id:
        return render(request, 'salesmanreport.html', {
            'salesmen': salesmen_list,
            'months': months,
            'years': years,
            'period': period,
            'selected_month': selected_month,
            'selected_year': selected_year,
        })

    try:
        salesman = Salesman.objects.get(id=salesman_id)
    except (Salesman.DoesNotExist, ValueError):
        return render(request, 'salesmanreport.html', {
            'salesmen': salesmen_list,
            'months': months,
            'years': years,
            'period': period,
            'selected_month': selected_month,
            'selected_year': selected_year,
        })

    # Base querysets filtered by salesman and optionally by date
    sale_qs = Sale.objects.filter(salesman=salesman)
    adai_qs = Adai.objects.filter(salesman=salesman)
    if filter_year and filter_month:
        sale_qs = sale_qs.filter(date__year=filter_year, date__month=filter_month)
        adai_qs = adai_qs.filter(date__year=filter_year, date__month=filter_month)

    sales = sale_qs.order_by('date')
    adai_records = adai_qs.order_by('date')

    # Build filtered_sales with products_text
    filtered_sales = []
    for sale in sales:
        products_text_parts = []
        if sale.products:
            for item in sale.products:
                pid = item.get('id')
                qty = item.get('quantity', 0)
                name = item.get('name') or item.get('product_name')
                if not name and pid:
                    try:
                        p = Product.objects.get(id=pid)
                        name = getattr(p, 'name', f'Product #{pid}')
                    except Product.DoesNotExist:
                        name = f'Product #{pid}'
                if name:
                    products_text_parts.append(f"{name} x {qty}")
        products_text = ', '.join(products_text_parts) if products_text_parts else ''
        filtered_sales.append({
            'date': sale.date.strftime('%Y-%m-%d') if sale.date else '',
            'customer': sale.customer.name if sale.customer else '',
            'total_price': sale.total_price,
            'discount': sale.discount,
            'payment_received': sale.payment_received,
            'due': sale.due,
            'comission': sale.comission,
            'invoice_number': sale.invoice_number or 'N/A',
            'products_text': products_text,
        })

    filtered_adai = [
        {
            'date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
            'customer': adai.customer.name if adai.customer else '',
            'due': adai.due,
            'advance': adai.advance,
        }
        for adai in adai_records
    ]

    # Summary totals (same definitions as salesman list)
    total_collection = sum((a.due or 0) + (a.advance or 0) for a in adai_records)
    total_paid_sales = sum(s.payment_received or 0 for s in sales)
    total_sales = total_collection + total_paid_sales
    total_commission = sum(s.comission or 0 for s in sales) + sum(a.sales_comission or 0 for a in adai_records)
    total_sales_due = sum(s.due or 0 for s in sales)
    total_advance_used = sum(s.advance_used or 0 for s in sales)
    total_adai_due = sum(a.due or 0 for a in adai_records)
    total_adai_advance = sum(a.advance or 0 for a in adai_records)

    # Customers involved in this filtered report (sales + adai) for this salesman
    sale_customer_ids = set(sale_qs.exclude(customer__isnull=True).values_list('customer_id', flat=True))
    adai_customer_ids = set(adai_qs.exclude(customer__isnull=True).values_list('customer_id', flat=True))
    customer_ids = sale_customer_ids | adai_customer_ids
    report_customers = Customer.objects.filter(id__in=customer_ids) if customer_ids else Customer.objects.none()

    total_customer_initial_due = sum(c.due or 0 for c in report_customers)
    total_customer_advance = sum(c.Advance or 0 for c in report_customers)

    # Requested due formula:
    # (sales due + customer initial due) -
    # (customer advance + adai.due + adai.advance - sales.advance_used)
    total_due = (total_sales_due + total_customer_initial_due) - (
        total_customer_advance + total_adai_due + total_adai_advance - total_advance_used
    )
    total_due = max(0, total_due)

    return render(request, 'salesmanreport.html', {
        'salesman_name': salesman.name,
        'salesman_id': salesman.id,
        'filtered_sales': filtered_sales,
        'filtered_adai': filtered_adai,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'period': period,
        'period_label': period_label,
        'total_collection': total_collection,
        'total_paid_sales': total_paid_sales,
        'total_sales': total_sales,
        'total_commission': total_commission,
        'total_due': total_due,
        'months': months,
        'years': years,
        'salesmen': salesmen_list,
    })

@csrf_exempt
def filter_adai(request):
    if request.method == 'POST':
        # Get the selected customer, month, and year from the form
        customer_id = request.POST.get('customer')
        selected_month = int(request.POST.get('month'))
        selected_year = int(request.POST.get('year'))

        # Fetch the customer details
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Customer not found.'})

        # Fetch adai records for the selected customer and date
        adai_records = Adai.objects.filter(
            customer=customer,
            date__year=selected_year,
            date__month=selected_month
        )
        filtered_adai = [
            {
                'date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
                'salesman': adai.salesman.name if adai.salesman else '',
                'due': adai.due,
                'advance': adai.advance,
                'sales_comission': adai.sales_comission,
            }
            for adai in adai_records
        ]

        return render(request, 'adai_filter.html', {
            'customer_name': customer.name,
            'filtered_adai': filtered_adai,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
            'years': range(2020, 2031),
        })

    # Default view (GET request)
    customers = Customer.objects.all()
    customer_list = [{'id': c.id, 'name': c.name} for c in customers]
    return render(request, 'adai_filter.html', {
        'customers': customer_list,
        'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
        'years': range(2020, 2031),
    })
    
    
@csrf_exempt
def filter_customer_sales(request):
    if request.method == 'POST':
        # Get the selected customer, month, and year from the form
        customer_id = request.POST.get('customer')
        selected_month = int(request.POST.get('month'))
        selected_year = int(request.POST.get('year'))

        # Fetch the customer details
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Customer not found.'})

        # Fetch sales records for the selected customer and date
        sales_records = Sale.objects.filter(
            customer=customer,
            date__year=selected_year,
            date__month=selected_month
        )
        calc_due, calc_adv = get_customer_calculated_due_advance(customer)
        if calc_due > 0:
            cutomer_balance = calc_due
        elif calc_adv > 0:
            cutomer_balance = -(calc_adv)
        else:
            cutomer_balance = 0
        balance_after = get_balance_after_each_sale(customer)
        filtered_sales = []
        for sale in sales_records:
            bal = balance_after.get(sale.id, {'due': 0, 'advance': 0})
            filtered_sales.append({
                'date': sale.date.strftime('%Y-%m-%d'),
                'cutomer_balance': cutomer_balance,
                'salesman': sale.salesman.name if sale.salesman else '',
                'total_price': float(sale.total_price or 0),
                'discount': sale.discount,
                'payment_received': sale.payment_received,
                'less': sale.less,
                'net_sale': get_sale_net_amount(sale),
                'invoice_number': sale.invoice_number or 'N/A',
                'products': sale.products if sale.products else [],
                'balance_due': bal['due'],
                'balance_advance': bal['advance'],
            })
        
        return render(request, 'filter_customer_sales.html', {
            'customer_name': customer.name,
            'filtered_sales': filtered_sales,
            'customer_due': get_customer_calculated_due_advance(customer)[0],
            'customer_balance':cutomer_balance,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
            'years': range(2020, 2031),
        })

    # Default view (GET request)
    customers = Customer.objects.all()
    customer_list = [{'id': c.id, 'name': c.name} for c in customers]
    return render(request, 'filter_customer_sales.html', {
        'customers': customer_list,
        'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
        'years': range(2020, 2031),
    })

ADMIN_CREDENTIALS_PATH = Path(settings.BASE_DIR) / "admin_credentials.json"
PASSWORD_RESET_EMAIL = "ipassword@rahmaniyapump.com"


def _ensure_admin_credentials_file():
    if ADMIN_CREDENTIALS_PATH.exists():
        return
    default_data = {
        "username": "admin",
        "password_hash": make_password("password123"),
    }
    ADMIN_CREDENTIALS_PATH.write_text(json.dumps(default_data, indent=2), encoding="utf-8")


def _load_admin_credentials():
    _ensure_admin_credentials_file()
    try:
        raw = json.loads(ADMIN_CREDENTIALS_PATH.read_text(encoding="utf-8"))
        username = str(raw.get("username") or "admin")
        password_hash = str(raw.get("password_hash") or "")
        if not password_hash:
            password_hash = make_password("password123")
            _save_admin_credentials(username, password_hash)
        return {"username": username, "password_hash": password_hash}
    except Exception:
        fallback = {"username": "admin", "password_hash": make_password("password123")}
        _save_admin_credentials(fallback["username"], fallback["password_hash"])
        return fallback


def _save_admin_credentials(username, password_hash):
    data = {"username": username, "password_hash": password_hash}
    ADMIN_CREDENTIALS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def login_view(request):
    if request.session.get("is_logged_in"):
        return redirect("dashboard")

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        creds = _load_admin_credentials()

        # Check credentials
        if hmac.compare_digest(username, creds["username"]) and check_password(password, creds["password_hash"]):
            # Set session variable to track login
            request.session['is_logged_in'] = True
            request.session['username'] = username
            request.session.set_expiry(60 * 60 * 12)  # 12 hours
            return redirect("dashboard")  # Redirect to the dashboard
        else:
            return render(request, "login.html", {"error": "Invalid username or password"})

    return render(request, "login.html")


@require_POST
def request_password_reset_code(request):
    _load_admin_credentials()
    reset_code = f"{random.randint(100000, 999999)}"
    expires_at = (timezone.now() + timedelta(minutes=10)).isoformat()

    request.session["admin_reset_code"] = reset_code
    request.session["admin_reset_email"] = PASSWORD_RESET_EMAIL
    request.session["admin_reset_expires_at"] = expires_at
    request.session["admin_reset_verified"] = False

    try:
        send_mail(
            subject="Rahmaniya Admin Password Reset Code",
            message=f"Your reset code is: {reset_code}\nThis code expires in 10 minutes.",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[PASSWORD_RESET_EMAIL],
            fail_silently=False,
        )
        messages.success(request, f"Reset code sent to {PASSWORD_RESET_EMAIL}.", extra_tags="auth")
    except Exception as e:
        messages.error(request, f"Could not send reset code email: {e}", extra_tags="auth")

    return redirect("login")


@require_POST
def reset_admin_credentials(request):
    submitted_code = (request.POST.get("code") or "").strip()
    new_username = (request.POST.get("new_username") or "").strip()
    new_password = request.POST.get("new_password") or ""
    confirm_password = request.POST.get("confirm_password") or ""

    session_code = request.session.get("admin_reset_code")
    expires_at_raw = request.session.get("admin_reset_expires_at")

    if not session_code or not expires_at_raw:
        messages.error(request, "Reset code নেই। আগে 'Send Reset Code' চাপুন।", extra_tags="auth")
        return redirect("login")

    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
    except Exception:
        messages.error(request, "Invalid reset session. আবার কোড নিন।", extra_tags="auth")
        return redirect("login")

    if timezone.now() > expires_at:
        messages.error(request, "Reset code expired. নতুন কোড নিন।", extra_tags="auth")
        return redirect("login")

    if not hmac.compare_digest(submitted_code, session_code):
        messages.error(request, "Invalid reset code.", extra_tags="auth")
        return redirect("login")

    if not new_username:
        messages.error(request, "New username is required.", extra_tags="auth")
        return redirect("login")

    if len(new_password) < 6:
        messages.error(request, "Password must be at least 6 characters.", extra_tags="auth")
        return redirect("login")

    if new_password != confirm_password:
        messages.error(request, "Password and confirm password do not match.", extra_tags="auth")
        return redirect("login")

    _save_admin_credentials(new_username, make_password(new_password))
    for key in ("admin_reset_code", "admin_reset_email", "admin_reset_expires_at", "admin_reset_verified"):
        if key in request.session:
            del request.session[key]

    messages.success(request, "Username and password updated successfully. Please login.", extra_tags="auth")
    return redirect("login")

@require_POST
def logout_view(request):
    # Clear session data
    request.session.flush()
    return redirect("login")


@csrf_exempt
def customer_ledger(request):
    """
    Customer ledger built only from Sales and Adai, in chronological order.
    Opening balance = initial_due - initial_advance + sum(debit) - sum(credit) for all events before selected year.
    Balance convention: positive = customer owes (due), negative = advance.
    """
    customers = Customer.objects.all()
    years = range(2020, 2031)
    ledger_rows = []
    customer_name = ""
    selected_year = None
    opening_balance = 0
    total_added = 0
    total_spent = 0
    current_balance = 0

    if request.method == "POST":
        customer_id = request.POST.get("customer")
        year = request.POST.get("year")

        if customer_id and year:
            selected_year = int(year)
            try:
                customer = Customer.objects.get(id=customer_id)
                customer_name = customer.name
                initial_due = float(customer.due or 0)
                initial_advance = float(customer.Advance or 0)

                # Single source: all events from Sales + Adai (already sorted by date)
                all_events = get_customer_ledger_events(customer)

                # Opening balance = initial + replay all events before selected year
                # Balance = what customer owes: +debit -credit (debit = sale adds owe, credit = payment reduces)
                opening_balance = initial_due - initial_advance
                for ev in all_events:
                    if ev['date'].year < selected_year:
                        opening_balance = opening_balance + ev['debit'] - ev['credit']

                # Events in selected year only
                year_events = [e for e in all_events if e['date'].year == selected_year]

                # Build ledger rows with running balance
                balance = opening_balance
                ledger_rows = []
                for ev in year_events:
                    balance = balance + ev['debit'] - ev['credit']
                    particulars = ev['particulars'] + (' - ' + ev['desc'] if ev.get('desc') else '')
                    ledger_rows.append({
                        'date': ev['date'].strftime('%d/%m/%y'),
                        'particulars': particulars,
                        'debit': ev['debit'],
                        'credit': ev['credit'],
                        'balance': balance,
                        'invoice_number': ev['invoice_number'],
                        'spend_money': ev['debit'] if ev['debit'] else None,
                        'add_money': ev['credit'] if ev['credit'] else None,
                    })

                total_added = sum(e['credit'] for e in year_events)
                total_spent = sum(e['debit'] for e in year_events)
                current_balance = balance

            except Customer.DoesNotExist:
                customer_name = ""
                ledger_rows = []
                opening_balance = 0
                total_added = 0
                total_spent = 0
                current_balance = 0

    context = {
        'customers': customers,
        'years': years,
        'ledger_rows': ledger_rows,
        'customer_name': customer_name,
        'selected_year': selected_year,
        'opening_balance': opening_balance,
        'total_added': total_added,
        'total_spent': total_spent,
        'current_balance': current_balance,
    }
    return render(request, 'ledger_customer.html', context)

@csrf_exempt
def supplier_ledger(request):
    # Get unique supplier list from Expence
    suppliers = Expence.objects.values_list('suplier', flat=True).distinct()
    years = range(2020, 2031)
    ledger_rows = []
    supplier_name = ""
    selected_year = None
    opening_balance = 0

    if request.method == "POST":
        supplier = request.POST.get("supplier")
        year = request.POST.get("year")

        if supplier and year:
            selected_year = int(year)
            supplier_name = supplier

            # Get all expenses for this supplier in the selected year
            expenses = Expence.objects.filter(suplier=supplier, date__year=selected_year)

            # Get all previous expenses for opening balance
            prev_expenses = Expence.objects.filter(suplier=supplier, date__year__lt=selected_year)

            # Calculate opening balance (Advance - Due up to previous year)
            opening_advance = sum(e.advance for e in prev_expenses)
            opening_due = sum(e.due for e in prev_expenses)
            opening_balance = opening_advance - opening_due

            # Gather all transactions for the year
            transactions = []
            for exp in expenses:
                # Debit: Due (you owe supplier), Credit: Advance (you paid in advance)
                transactions.append({
                    "date": exp.date,
                    "particulars": exp.narration or "Expense",
                    "debit": exp.due,
                    "credit": exp.advance,
                })

            # Sort all transactions by date
            transactions.sort(key=lambda x: x["date"] or "")

            # Build ledger rows with running balance
            balance = opening_balance
            for t in transactions:
                balance = balance + (t["credit"] or 0) - (t["debit"] or 0)
                ledger_rows.append({
                    "date": t["date"].strftime("%d/%m/%y") if t["date"] else "",
                    "particulars": t["particulars"],
                    "debit": t["debit"] if t["debit"] else "",
                    "credit": t["credit"] if t["credit"] else "",
                    "balance": balance,
                })

    context = {
        "suppliers": suppliers,
        "years": years,
        "ledger_rows": ledger_rows,
        "supplier_name": supplier_name,
        "selected_year": selected_year,
        "opening_balance": opening_balance,
    }
    return render(request, "ledger_supplier.html", context)

def _salesman_report_date_filter(period, month_param, year_param):
    """Resolve period (all_time, last_month, custom) to filter_month, filter_year and period label. Returns (filter_month, filter_year, month_name, year_label)."""
    today = datetime.now().date()
    if period == 'all_time':
        return None, None, 'All time', ''
    if period == 'last_month':
        if today.month == 1:
            fy, fm = today.year - 1, 12
        else:
            fy, fm = today.year, today.month - 1
        return fm, fy, calendar.month_name[fm], str(fy)
    # custom
    try:
        m = int(month_param or 0)
        y = int(year_param or 0)
        if 1 <= m <= 12 and y >= 2000:
            return m, y, calendar.month_name[m], str(y)
    except (ValueError, TypeError):
        pass
    return None, None, 'All time', ''


@csrf_exempt
def download_salesman_report(request):
    """Download salesman report (PDF/print). Supports period=all_time, last_month, custom (month+year)."""
    salesman_name = request.GET.get('salesman')
    period = (request.GET.get('period') or 'all_time').strip().lower()
    month_param = request.GET.get('month')
    year_param = request.GET.get('year')

    if not salesman_name:
        return HttpResponse("Missing parameter: salesman", status=400)
    try:
        salesman = Salesman.objects.get(name=salesman_name)
    except Salesman.DoesNotExist:
        return HttpResponse("Salesman not found", status=404)

    filter_month, filter_year, month_name, year_label = _salesman_report_date_filter(period, month_param, year_param)

    sale_qs = Sale.objects.filter(salesman=salesman)
    adai_qs = Adai.objects.filter(salesman=salesman)
    if filter_month is not None and filter_year is not None:
        sale_qs = sale_qs.filter(date__year=filter_year, date__month=filter_month)
        adai_qs = adai_qs.filter(date__year=filter_year, date__month=filter_month)

    sales = list(sale_qs.order_by('date'))
    adai_records = list(adai_qs.order_by('date'))

    total_sales_amount = sum(sale.total_price or 0 for sale in sales)
    total_collection = sum(sale.payment_received or 0 for sale in sales) + sum((a.due or 0) + (a.advance or 0) for a in adai_records)
    total_commission = sum(sale.comission or 0 for sale in sales) + sum(a.sales_comission or 0 for a in adai_records)
    all_sales = Sale.objects.filter(salesman=salesman)
    total_due = sum(sale.due or 0 for sale in all_sales) - total_collection

    sales_data = [
        {
            'date': sale.date.strftime('%Y-%m-%d') if sale.date else '',
            'customer': sale.customer.name if sale.customer else '',
            'total_price': sale.total_price,
            'payment_received': sale.payment_received,
            'due': sale.due,
            'invoice_number': sale.invoice_number or 'N/A',
            'commission': sale.comission,
        }
        for sale in sales
    ]
    adai_data = [
        {
            'date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
            'customer': adai.customer.name if adai.customer else '',
            'due': adai.due,
            'advance': adai.advance,
        }
        for adai in adai_records
    ]

    context = {
        'salesman_name': salesman_name,
        'month_name': month_name,
        'year': year_label,
        'current_date': datetime.now().strftime('%Y-%m-%d'),
        'total_sales': total_sales_amount,
        'total_collection': total_collection,
        'total_commission': total_commission,
        'total_due': total_due,
        'sales': sales_data,
        'adai_records': adai_data,
    }
    return render(request, 'salesman_report_template.html', context)


def export_salesman_report_excel(request):
    """Export salesman report to Excel. Supports period=all_time, last_month, custom (month+year)."""
    salesman_name = request.GET.get('salesman')
    period = (request.GET.get('period') or 'all_time').strip().lower()
    month_param = request.GET.get('month')
    year_param = request.GET.get('year')

    if not salesman_name:
        return HttpResponse("Missing parameter: salesman", status=400)
    try:
        salesman = Salesman.objects.get(name=salesman_name)
    except Salesman.DoesNotExist:
        return HttpResponse("Invalid salesman", status=404)

    filter_month, filter_year, month_name, year_label = _salesman_report_date_filter(period, month_param, year_param)

    sale_qs = Sale.objects.filter(salesman=salesman)
    adai_qs = Adai.objects.filter(salesman=salesman)
    if filter_month is not None and filter_year is not None:
        sale_qs = sale_qs.filter(date__year=filter_year, date__month=filter_month)
        adai_qs = adai_qs.filter(date__year=filter_year, date__month=filter_month)

    sales = sale_qs.order_by('date')
    adai_records = adai_qs.order_by('date')

    sales_data = []
    for sale in sales:
        sales_data.append({
            'Invoice Number': sale.invoice_number or 'N/A',
            'Date': sale.date.strftime('%Y-%m-%d') if sale.date else '',
            'Customer': sale.customer.name if sale.customer else '',
            'Total Amount': float(sale.total_price or 0),
            'Payment Received': float(sale.payment_received or 0),
            'Due': float(sale.due or 0),
            'Commission': float(sale.comission or 0),
        })
    adai_data = []
    for adai in adai_records:
        adai_data.append({
            'Date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
            'Customer': adai.customer.name if adai.customer else '',
            'Due Collection': float(adai.due or 0),
            'Advance': float(adai.advance or 0),
        })
    df_sales = pd.DataFrame(sales_data)
    df_adai = pd.DataFrame(adai_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_sales.to_excel(writer, index=False, sheet_name='Sales')
        df_adai.to_excel(writer, index=False, sheet_name='Collection (Adai)')
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    safe_name = salesman_name.replace(' ', '_')
    period_suffix = 'all_time' if (filter_month is None or filter_year is None) else f"{filter_year}_{filter_month:02d}"
    response['Content-Disposition'] = f'attachment; filename="salesman_report_{safe_name}_{period_suffix}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
    return response


def export_salesman_payment_excel(request):
    """Export salesman payment summary (commission, salary paid, Paid, Due) to Excel."""
    now = datetime.now()
    salesmen = Salesman.objects.all()
    excel_data = []
    for salesman in salesmen:
        month_salary_paid = SalesmanSalaryPayment.objects.filter(
            salesman=salesman,
            date__year=now.year,
            date__month=now.month
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        excel_data.append({
            'Name': salesman.name,
            'Code': salesman.code,
            'Area': salesman.area or '',
            'Phone': salesman.phone or '',
            'Commission Rate %': float(salesman.comission or 0),
            'Total Commission': float(salesman.salescomission or 0),
            'Salary This Month': float(month_salary_paid),
            'Basic Salary': float(getattr(salesman, 'basic_salary', 0) or 0),
            'Paid': float(salesman.Paid or 0),
            'Due': float(salesman.Due or 0),
        })
    df = pd.DataFrame(excel_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Salesmen')
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="salesman_payment_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
    return response


@csrf_exempt
def salesman_login(request):
    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code")
        
        try:
            salesman = Salesman.objects.get(name=name, code=code)
            request.session['salesman_id'] = salesman.id
            request.session['salesman_name'] = salesman.name
            return redirect('salesman_pos')
        except Salesman.DoesNotExist:
            return render(request, "salesman_login.html", {"error": "Invalid name or code"})
    
    return render(request, "salesman_login.html")

@require_POST
def salesman_logout(request):
    if 'salesman_id' in request.session:
        del request.session['salesman_id']
        del request.session['salesman_name']
    return redirect('salesman_login')

def salesman_pos(request):
    # Check if salesman is logged in
    if 'salesman_id' not in request.session:
        return redirect('salesman_login')
    
    salesman_id = request.session['salesman_id']
    try:
        salesman = Salesman.objects.get(id=salesman_id)
    except Salesman.DoesNotExist:
        return redirect('salesman_login')

    # Retrieve products from the Product model
    products = Product.objects.all()
    products_data = [
        {
            'id': product.id,
            'name': product.name,
            'rate': product.rate,
            'size': product.size,
            'total_stock': product.total_stock,
        }
        for product in products
    ]

    # Retrieve customers from the Customer model
    customers = Customer.objects.all()
    customers_data = []
    for customer in customers:
        calc_due, calc_adv = get_customer_calculated_due_advance(customer)
        customers_data.append({
            'id': customer.id,
            'name': customer.name,
            'code': customer.code,
            'area': customer.area,
            'due': calc_due,
            'Advance': calc_adv,
        })

    context = {
        'products': products_data,
        'customers': customers_data,
        'salesman': {
            'id': salesman.id,
            'name': salesman.name,
            'code': salesman.code,
        }
    }
    return render(request, 'salesman_pos.html', context)

@csrf_exempt
def save_pending_sale(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            sid = data.get('salesman')
            cid = data.get('customer')
            products_sold = data.get('products', [])
            total_price = float(data.get('total_price', 0))
            discount_percent = float(data.get('discount', 0))
            less_input = float(data.get('less', 0))
            payment_received = float(data.get('payment_received', 0))
            due = float(data.get('due', 0))

            # Calculate total less from all products
            total_less_products = sum(float(p.get('less', 0)) for p in products_sold)
            final_less = total_less_products + less_input

            try:
                salesman = Salesman.objects.get(id=sid)
                customer = Customer.objects.get(id=cid)
            except (Salesman.DoesNotExist, Customer.DoesNotExist):
                return JsonResponse({'status': 'error', 'error': 'Salesman or Customer not found.'}, status=404)

            # Get the last invoice number from both Sale and PendingSale models
            last_server_sale = Sale.objects.filter(
                salesman=salesman
            ).order_by('-invoice_number').first()

            last_pending_sale = PendingSale.objects.filter(
                salesman=salesman
            ).order_by('-invoice_number').first()

            # Initialize max_serial
            max_serial = 0

            # Check server sales
            if last_server_sale and last_server_sale.invoice_number:
                try:
                    server_serial = int(last_server_sale.invoice_number[len(salesman.code):])
                    max_serial = max(max_serial, server_serial)
                except (ValueError):
                    pass

            # Check pending sales
            if last_pending_sale and last_pending_sale.invoice_number:
                try:
                    pending_serial = int(last_pending_sale.invoice_number[len(salesman.code):])
                    max_serial = max(max_serial, pending_serial)
                except (ValueError):
                    pass

            # Generate new serial number
            new_serial = max_serial + 1
            invoice_number = f"{salesman.code}{new_serial:04d}"

            # Calculate commission
            commission_amount = float(salesman.comission / 100) * float(payment_received)

            # Create pending sale
            pending_sale = PendingSale.objects.create(
                salesman=salesman,
                customer=customer,
                products=products_sold,
                total_price=total_price,
                discount=(discount_percent / 100) * total_price,
                less=final_less,  # final_less (unchangable)
                total_less_products=total_less_products,
                less_input=less_input,
                payment_received=payment_received,
                due=due,
                comission=commission_amount,
                invoice_number=invoice_number
            )

            return JsonResponse({
                'status': 'success',
                'message': 'Sale request submitted for approval.',
                'invoice_number': invoice_number
            })

        return JsonResponse({'status': 'error', 'error': 'Invalid request method.'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'error': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

def pending_sales(request):
    # Check if user is admin
    if 'salesman_id' in request.session:
        return redirect('salesman_pos')
    
    pending_sales = PendingSale.objects.filter(status='pending').order_by('-date', '-time')
    return render(request, 'pending_sales.html', {'pending_sales': pending_sales})

@csrf_exempt
def approve_sale(request, sale_id):
    if request.method == 'POST':
        try:
            pending_sale = PendingSale.objects.get(id=sale_id)
            
            # Get the last invoice number from both Sale and PendingSale models
            last_server_sale = Sale.objects.filter(
                salesman=pending_sale.salesman
            ).order_by('-invoice_number').first()

            last_pending_sale = PendingSale.objects.filter(
                salesman=pending_sale.salesman
            ).order_by('-invoice_number').first()

            # Initialize max_serial
            max_serial = 0

            # Check server sales
            if last_server_sale and last_server_sale.invoice_number:
                try:
                    server_serial = int(last_server_sale.invoice_number[len(pending_sale.salesman.code):])
                    max_serial = max(max_serial, server_serial)
                except (ValueError):
                    pass

            # Check pending sales
            if last_pending_sale and last_pending_sale.invoice_number:
                try:
                    pending_serial = int(last_pending_sale.invoice_number[len(pending_sale.salesman.code):])
                    max_serial = max(max_serial, pending_serial)
                except (ValueError):
                    pass

            # Generate new serial number
            new_serial = max_serial + 1
            new_invoice_number = f"{pending_sale.salesman.code}{new_serial:04d}"
            
            # Create actual sale with new invoice number
            sale = Sale.objects.create(
                salesman=pending_sale.salesman,
                customer=pending_sale.customer,
                products=pending_sale.products,
                total_price=pending_sale.total_price,
                discount=pending_sale.discount,
                less=pending_sale.less,
                total_less_products=getattr(pending_sale, 'total_less_products', 0),
                less_input=getattr(pending_sale, 'less_input', 0),
                payment_received=pending_sale.payment_received,
                due=pending_sale.due,
                date=pending_sale.date,
                time=pending_sale.time,
                comission=pending_sale.comission,
                invoice_number=new_invoice_number
            )

            # Update customer Paid only (Customer.due/Advance are initial-only; balance is calculated from sales+adai)
            customer = pending_sale.customer
            customer.Paid += pending_sale.payment_received
            customer.save()

            # Update salesman commission
            salesman = pending_sale.salesman
            salesman.salescomission += pending_sale.comission
            salesman.save()

            # Update product stock
            for product in pending_sale.products:
                try:
                    prod = Product.objects.get(id=product['id'])
                    prod.total_stock -= float(product['quantity'])
                    prod.total_sales += float(product['quantity'])
                    prod.save()
                except Product.DoesNotExist:
                    continue

            # Mark pending sale as approved
            pending_sale.status = 'approved'
            pending_sale.save()

            return JsonResponse({'status': 'success'})
        except PendingSale.DoesNotExist:
            return JsonResponse({'error': 'Sale not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method.'}, status=400)

@csrf_exempt
def reject_sale(request, sale_id):
    if request.method == 'POST':
        try:
            pending_sale = PendingSale.objects.get(id=sale_id)
            pending_sale.status = 'rejected'
            pending_sale.save()
            return JsonResponse({'status': 'success'})
        except PendingSale.DoesNotExist:
            return JsonResponse({'error': 'Sale not found.'}, status=404)

    return JsonResponse({'error': 'Invalid request method.'}, status=400)

def upload_products(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            excel_file = request.FILES['excel_file']
            
            
            
            # Read Excel file
            df = pd.read_excel(excel_file)
            
            # List of exact column names from the Excel file
            excel_column_names = ['Code', 'Name', 'Size', 'Rate', 'Add Stock', 'Production Cost', 'Total Sales', 'Total Stock']
            
            # Check for missing columns in the DataFrame
            missing_excel_columns = [col for col in excel_column_names if col not in df.columns]
            if missing_excel_columns:
                messages.error(request, f'Missing required columns in Excel file: {", ".join(missing_excel_columns)}. Please ensure your Excel has these exact column headers.')
                return redirect('upload_products')
            
            success_count = 0
            error_count = 0
            error_details = []
            
            for index, row in df.iterrows():
                try:
                    # Convert values to appropriate types and handle NaN using Excel column names
                    code = str(row['Code']) if pd.notna(row['Code']) else ''
                    name = str(row['Name']) if pd.notna(row['Name']) else ''
                    size = str(row['Size']) if pd.notna(row['Size']) else ''
                    rate = float(row['Rate']) if pd.notna(row['Rate']) else 0.0
                    add_stock = float(row['Add Stock']) if pd.notna(row['Add Stock']) else 0.0
                    production_cost = float(row['Production Cost']) if pd.notna(row['Production Cost']) else 0.0
                    total_sales = float(row['Total Sales']) if pd.notna(row['Total Sales']) else 0.0
                    total_stock = float(row['Total Stock']) if pd.notna(row['Total Stock']) else 0.0
                    
                    # Validate required fields
                    if not code or not name:
                        raise ValueError("Code and Name are required fields for each product.")
                    
                    product, created = Product.objects.update_or_create(
                        code=code,
                        defaults={
                            'name': name,
                            'size': size,
                            'rate': rate,
                            'add_stock': add_stock,
                            'production_cost': production_cost,
                            'total_sales': total_sales,
                            'total_stock': total_stock
                        }
                    )
                    
                    success_count += 1
                    
                    
                except Exception as e:
                    error_count += 1
                    error_msg = f"Row {index + 2}: {str(e)}"
                    error_details.append(error_msg)
                    print(f"Error processing row {index + 2}: {str(e)}")
            
            if success_count > 0:
                messages.success(request, f'Successfully uploaded {success_count} products')
            if error_count > 0:
                messages.warning(request, f'Failed to upload {error_count} products')
                for error in error_details[:5]:  # Show first 5 errors
                    messages.error(request, error)
                if len(error_details) > 5:
                    messages.error(request, f"... and {len(error_details) - 5} more errors")
            
            return redirect('product_list')
            
        except Exception as e:
            error_msg = f'Error processing file: {str(e)}'
            print(error_msg)  # Print to console for debugging
            messages.error(request, error_msg)
            return redirect('upload_products')
            
    return render(request, 'upload_products.html')

@csrf_exempt
def product_report(request):
    # Get all products for the dropdown
    products = Product.objects.all()
    
    if request.method == 'POST':
        product_id = request.POST.get('product')
        selected_month = int(request.POST.get('month'))
        selected_year = int(request.POST.get('year'))
        
        try:
            product = Product.objects.get(id=product_id)
            
            # Get all sales for the selected product in the given month/year
            sales = Sale.objects.filter(
                date__year=selected_year,
                date__month=selected_month
            )
            
            # Process sales to find product-specific data
            product_sales = []
            total_quantity = 0
            total_amount = 0
            
            for sale in sales:
                if sale.products:  # Check if products field exists
                    for item in sale.products:
                        if item.get('id') == product_id:
                            quantity = float(item.get('quantity', 0))
                            price = float(item.get('price', 0))
                            total_quantity += quantity
                            total_amount += quantity * price
                            
                            product_sales.append({
                                'date': sale.date.strftime('%Y-%m-%d'),
                                'customer': sale.customer.name if sale.customer else 'N/A',
                                'quantity': quantity,
                                'price': price,
                                'total': quantity * price,
                                'invoice': sale.invoice_number or 'N/A'
                            })
            
            context = {
                'products': products,
                'selected_product': product,
                'selected_month': selected_month,
                'selected_year': selected_year,
                'product_sales': product_sales,
                'total_quantity': total_quantity,
                'total_amount': total_amount,
                'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
                'years': range(2020, 2031),
            }
            
        except Product.DoesNotExist:
            messages.error(request, "Product not found!")
            context = {
                'products': products,
                'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
                'years': range(2020, 2031),
            }
    else:
        context = {
            'products': products,
            'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
            'years': range(2020, 2031),
        }
    
    return render(request, 'product_report.html', context)

# @csrf_exempt
# def marketing_cost(request):
#     from django.contrib import messages
#     from .models import Customer
#     if request.method == 'POST':
#         date = request.POST.get('date')
#         salesman_id = request.POST.get('salesman')
#         customer_id = request.POST.get('customer')
#         invoice_number = request.POST.get('invoice')
#         expense_type = request.POST.get('expense_type')
#         amount = request.POST.get('amount')
#         try:
#             salesman = Salesman.objects.get(id=salesman_id)
#             customer = Customer.objects.get(id=customer_id)
#             MarketingCost.objects.create(
#                 date=date,
#                 salesman=salesman,
#                 customer_name=customer.name,
#                 invoice_number=invoice_number,
#                 expense_type=expense_type,
#                 amount=amount
#             )
#             messages.success(request, 'Marketing cost entry added successfully!')
#             return redirect('marketing_cost')
#         except Salesman.DoesNotExist:
#             messages.error(request, 'Salesman not found!')
#         except Customer.DoesNotExist:
#             messages.error(request, 'Customer not found!')
#         except Exception as e:
#             messages.error(request, f'Error: {e}')
#     salesmen = Salesman.objects.all()
#     customers = Customer.objects.all()
#     invoices = Sale.objects.filter(invoice_number__isnull=False).exclude(invoice_number='').order_by('-date')
#     return render(request, 'marketing_cost.html', {'salesmen': salesmen, 'customers': customers, 'invoices': invoices})


@csrf_exempt
def marketing_cost(request):
    from django.contrib import messages
    from .models import Customer
    # Filter customers by selected salesman (like pos_dashboard)
    selected_salesman_id = request.GET.get('salesman') or request.POST.get('salesman')
    if selected_salesman_id:
        try:
            selected_salesman = Salesman.objects.get(id=selected_salesman_id)
            code_range = selected_salesman.code
            if '-' in code_range:
                start_code, end_code = code_range.split('-')
                try:
                    start_code = int(start_code)
                    end_code = int(end_code)
                    filtered_customers = [
                        c for c in Customer.objects.all()
                        if c.code.isdigit() and start_code <= int(c.code) <= end_code
                    ]
                except ValueError:
                    filtered_customers = Customer.objects.none()
            else:
                filtered_customers = Customer.objects.none()
        except Salesman.DoesNotExist:
            filtered_customers = Customer.objects.none()
    else:
        filtered_customers = Customer.objects.all()

    if request.method == 'POST':
        date = request.POST.get('date')
        salesman_id = request.POST.get('salesman')
        customer_id =0
        invoice_number =0
        expense_type = request.POST.get('expense_type')
        amount = request.POST.get('amount')
        try:
            salesman = Salesman.objects.get(id=salesman_id)
            # customer = Customer.objects.get(id=customer_id)
            MarketingCost.objects.create(
                date=date,
                salesman=salesman,
                customer_name='null',
                invoice_number=invoice_number,
                expense_type=expense_type,
                amount=amount
            )
            messages.success(request, 'Marketing cost entry added successfully!')
            return redirect('marketing_cost')
        except Salesman.DoesNotExist:
            messages.error(request, 'Salesman not found!')
        except Customer.DoesNotExist:
            messages.error(request, 'Customer not found!')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    salesmen = Salesman.objects.all()
    invoices = Sale.objects.filter(invoice_number__isnull=False).exclude(invoice_number='').order_by('-date')
    return render(request, 'marketing_cost.html', {'salesmen': salesmen, 'customers': filtered_customers, 'invoices': invoices})
@csrf_exempt
def marketing_cost_list(request):
    from .models import MarketingCost, Salesman
    from django.contrib import messages
    salesmen = Salesman.objects.all()
    selected_salesman = request.GET.get('salesman', '')
    selected_month = request.GET.get('month', '')
    marketing_costs = MarketingCost.objects.all().order_by('-date')
    if selected_salesman:
        marketing_costs = marketing_costs.filter(salesman_id=selected_salesman)
    if selected_month:
        try:
            year, month = selected_month.split('-')
            marketing_costs = marketing_costs.filter(
                date__year=int(year),
                date__month=int(month)
            )
        except (ValueError, TypeError):
            messages.error(request, 'Invalid month filter format.')
    context = {
        'salesmen': salesmen,
        'selected_salesman': selected_salesman,
        'selected_month': selected_month,
        'marketing_costs': marketing_costs,
    }
    return render(request, 'marketing_cost_list.html', context)

@csrf_exempt
def delete_marketing_cost(request, cost_id):
    from .models import MarketingCost
    from django.contrib import messages
    if request.method == 'POST':
        try:
            cost = MarketingCost.objects.get(id=cost_id)
            cost.delete()
            messages.success(request, 'Marketing cost entry deleted successfully!')
        except MarketingCost.DoesNotExist:
            messages.error(request, 'Marketing cost entry not found!')
    return redirect(reverse('marketing_cost_list'))

@csrf_exempt
def profit_report(request):
    from .models import Sale, MarketingCost, Product
    from django.db.models import Sum
    from datetime import datetime
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    sales = Sale.objects.all().order_by('-date')
    if start_date:
        sales = sales.filter(date__gte=start_date)
    if end_date:
        sales = sales.filter(date__lte=end_date)
    profit_rows = []
    total_product_costing = 0
    total_marketing_cost = 0
    total_sales = 0
    total_profit = 0
    for sale in sales:
        # Marketing cost for this invoice (total marketing cost for this invoice)
        marketing_cost = MarketingCost.objects.filter(
            invoice_number=sale.invoice_number
        ).aggregate(total=Sum('amount'))['total'] or 0
        # Add salesman commission for this sale
        total_marketing_and_commission = marketing_cost + float(sale.comission or 0)
        if sale.products:
            for item in sale.products:
                try:
                    prod = Product.objects.get(id=item.get('id'))
                    qty = float(item.get('quantity', 0))
                    product_costing = prod.production_cost * qty
                    selling_price = float(item.get('price', 0)) * qty
                    profit = selling_price - product_costing - total_marketing_and_commission
                    profit_rows.append({
                        'date': sale.date,
                        'invoice_number': sale.invoice_number or 'N/A',
                        'customer_name': sale.customer.name if sale.customer else '',
                        'product_name': prod.name,
                        'product_quantity': qty,
                        'salesman_name': sale.salesman.name if sale.salesman else '',
                        'product_costing': f"{product_costing:.2f}",
                        'marketing_cost': f"{total_marketing_and_commission:.2f}",
                        'selling_price': f"{selling_price:.2f}",
                        'profit': f"{profit:.2f}",
                    })
                    total_product_costing += product_costing
                    total_marketing_cost += total_marketing_and_commission
                    total_sales += selling_price
                    total_profit += profit
                except Product.DoesNotExist:
                    continue
    context = {
        'profit_rows': profit_rows,
        'start_date': start_date,
        'end_date': end_date,
        'total_product_costing': f"{total_product_costing:.2f}",
        'total_marketing_cost': f"{total_marketing_cost:.2f}",
        'total_sales': f"{total_sales:.2f}",
        'total_profit': f"{total_profit:.2f}",
    }
    return render(request, 'profit_report.html', context)

@csrf_exempt
@require_POST
def update_customer(request, customer_id):
    import json
    from django.http import JsonResponse, HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'], 'This endpoint only accepts POST requests.')
    try:
        data = json.loads(request.body)
        customer = Customer.objects.get(id=customer_id)
        # Update all editable fields
        customer.name = data.get('name', customer.name)
        customer.code = data.get('code', customer.code)
        customer.area = data.get('area', customer.area)
        customer.phone = data.get('phone', customer.phone)
        customer.nid = data.get('nid', customer.nid)
        # Numeric fields
        try:
            customer.due = float(data.get('due', customer.due))
        except (TypeError, ValueError):
            pass
        try:
            customer.Advance = float(data.get('Advance', customer.Advance))
        except (TypeError, ValueError):
            pass
        try:
            customer.Paid = float(data.get('Paid', customer.Paid))
        except (TypeError, ValueError):
            pass
        customer.save()
        current_due, current_advance = get_customer_calculated_due_advance(customer)
        return JsonResponse({
            'status': 'success',
            'due': current_due,
            'Advance': current_advance,
            'Paid': customer.Paid,
        })
    except Customer.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Customer not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
@require_POST
def update_salesman(request, salesman_id):
    import json
    from django.http import JsonResponse
    from .models import Salesman
    try:
        data = json.loads(request.body)
        salesman = Salesman.objects.get(id=salesman_id)
        salesman.name = data.get('name', salesman.name)
        salesman.code = data.get('code', salesman.code)
        salesman.area = data.get('area', salesman.area)
        salesman.phone = data.get('phone', salesman.phone)
        try:
            salesman.comission = float(data.get('comission', salesman.comission))
        except (TypeError, ValueError):
            pass
        try:
            salesman.salescomission = float(data.get('salescomission', salesman.salescomission))
        except (TypeError, ValueError):
            pass
        try:
            salesman.basic_salary = float(data.get('basic_salary', getattr(salesman, 'basic_salary', 0)))
        except (TypeError, ValueError):
            pass
        salesman.save()
        return JsonResponse({'status': 'success'})
    except Salesman.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Salesman not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        
        
@csrf_exempt
def update_product(request, product_id):
    if request.method == 'POST':
        try:
            product = Product.objects.get(id=product_id)
            for field in ['code', 'name', 'size', 'rate', 'production_cost', 'total_sales', 'total_stock']:
                value = request.POST.get(field)
                if value is not None:
                    if field in ['rate', 'production_cost', 'total_sales', 'total_stock']:
                        value = float(value or 0)
                    setattr(product, field, value)
            # Handle image URL
            image_url = request.POST.get('image', '').strip()
            if image_url:
                product.image = image_url
            elif 'image' in request.POST:
                # If image field is present but empty, clear it
                product.image = None
            product.save()
        except Product.DoesNotExist:
            pass
        return redirect('product_list')
    return redirect('product_list')
    
@csrf_exempt
def update_transaction(request, transaction_id):
    if request.method == 'POST':
        try:
            from .models import Transaction, BankAccount
            transaction = Transaction.objects.get(id=transaction_id)
            bank_account_id = request.POST.get('bank_account')
            date = request.POST.get('transactionDate')
            narration = request.POST.get('narration')
            transaction_type = request.POST.get('transaction_type')
            amount = float(request.POST.get('amount', 0) or 0)
            if bank_account_id:
                try:
                    bank_account = BankAccount.objects.get(id=bank_account_id)
                    transaction.bank_account = bank_account
                except BankAccount.DoesNotExist:
                    pass
            if date:
                transaction.date = date
            if narration is not None:
                transaction.narration = narration
            if transaction_type:
                transaction.transaction_type = transaction_type
            transaction.amount = amount
            transaction.save()
        except Transaction.DoesNotExist:
            pass
        return redirect('transaction_list')
    return redirect('transaction_list')

# ==================== ECOMMERCE VIEWS ====================

def cart(request):
    """
    View to render the shopping cart page
    """
    return render(request, 'cart.html')

def checkout(request):
    """
    View to render the checkout page
    """
    return render(request, 'checkout.html')

@csrf_exempt
def place_order(request):
    """
    View to process and save the order
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Extract order data
            customer_name = data.get('customer_name', '')
            customer_email = data.get('customer_email', '')
            customer_phone = data.get('customer_phone', '')
            shipping_address = data.get('shipping_address', '')
            city = data.get('city', '')
            postal_code = data.get('postal_code', '')
            payment_method = data.get('payment_method', 'cash_on_delivery')
            notes = data.get('notes', '')
            products = data.get('products', [])
            subtotal = float(data.get('subtotal', 0))
            shipping_cost = float(data.get('shipping', 0))
            discount = float(data.get('discount', 0))
            
            # Validate required fields
            if not customer_name or not customer_email or not customer_phone:
                return JsonResponse({'status': 'error', 'error': 'Customer information is required.'}, status=400)
            
            if not shipping_address or not city or not postal_code:
                return JsonResponse({'status': 'error', 'error': 'Shipping address is required.'}, status=400)
            
            if not products or len(products) == 0:
                return JsonResponse({'status': 'error', 'error': 'No products in order.'}, status=400)
            
            # Validate product stock
            for product in products:
                product_id = product.get('id')
                quantity = float(product.get('quantity', 0))
                
                if product_id and quantity > 0:
                    try:
                        prod = Product.objects.get(id=product_id)
                        if prod.total_stock < quantity:
                            return JsonResponse({
                                'status': 'error',
                                'error': f'Insufficient stock for {prod.name}. Only {prod.total_stock} units available.'
                            }, status=400)
                    except Product.DoesNotExist:
                        return JsonResponse({
                            'status': 'error',
                            'error': f'Product with ID {product_id} not found.'
                        }, status=404)
            
            # Generate order number
            from datetime import datetime
            order_number = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{datetime.now().microsecond}"
            
            # Calculate total
            total_price = subtotal + shipping_cost - discount
            
            # Create order
            from .models import Order
            order = Order.objects.create(
                order_number=order_number,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                shipping_address=shipping_address,
                city=city,
                postal_code=postal_code,
                products=products,
                total_price=total_price,
                discount=discount,
                shipping_cost=shipping_cost,
                payment_method=payment_method,
                payment_received=0,  # Will be received on delivery
                status='pending',
                notes=notes
            )
            
            # Update product stock and sales
            for product in products:
                product_id = product.get('id')
                quantity = float(product.get('quantity', 0))
                
                if product_id and quantity > 0:
                    try:
                        prod = Product.objects.get(id=product_id)
                        prod.total_stock -= quantity
                        prod.total_sales += quantity
                        prod.save()
                    except Product.DoesNotExist:
                        continue
            
            return JsonResponse({
                'status': 'success',
                'message': 'Order placed successfully!',
                'order_number': order_number,
                'order_id': order.id
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'error': f'An error occurred: {str(e)}'
            }, status=500)
    
    return JsonResponse({'status': 'error', 'error': 'POST request required.'}, status=400)

@csrf_exempt
def api_products(request):
    """
    API endpoint to get all products with stock information
    """
    if request.method == 'GET':
        products = Product.objects.all()
        products_data = []
        for product in products:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'code': product.code,
                'price': float(product.rate),
                'stock': float(product.total_stock),
                'size': product.size,
                'image': product.image if product.image else None
            })
        return JsonResponse(products_data, safe=False)
    return JsonResponse({'error': 'GET request required.'}, status=400)

@csrf_exempt
def api_product_detail(request, product_id):
    """
    API endpoint to get a single product's details
    """
    if request.method == 'GET':
        try:
            product = Product.objects.get(id=product_id)
            return JsonResponse({
                'id': product.id,
                'name': product.name,
                'code': product.code,
                'price': float(product.rate),
                'stock': float(product.total_stock),
                'size': product.size,
                'image': product.image if product.image else None
            })
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found.'}, status=404)
    return JsonResponse({'error': 'GET request required.'}, status=400)