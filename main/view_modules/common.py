"""Shared imports, constants and helper functions for split Django views."""

from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db import models
from django.http import HttpResponse
from django.template.loader import render_to_string
from playwright.async_api import async_playwright
import asyncio
from main.models import Salesman
from main.models import Product
from main.models import Customer, Sale,Adai
from main.models import Transaction
from main.models import Expence,PendingSale
from main.models import BankAccount
from main.models import MarketingCost
from main.models import SalesmanSalaryPayment
from main.models import Order
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
import requests
from django.shortcuts import get_object_or_404
ADMIN_CREDENTIALS_PATH = Path(settings.BASE_DIR) / "admin_credentials.json"
PASSWORD_RESET_EMAIL = "ipassword@rahmaniyapump.com"

def _save_admin_credentials(username, password_hash):
    data = {"username": username, "password_hash": password_hash}
    ADMIN_CREDENTIALS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _ensure_admin_credentials_file():
    if ADMIN_CREDENTIALS_PATH.exists():
        return
    default_data = {
        "username": "admin",
        "password_hash": make_password("password123"),
    }
    ADMIN_CREDENTIALS_PATH.write_text(json.dumps(default_data, indent=2), encoding="utf-8")


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


def index(request):
    """
    View to render the company website homepage (index.html)
    This is a public-facing page that doesn't require authentication
    """
    return render(request, 'index.html')


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


