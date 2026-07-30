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

from django.http import JsonResponse
import json
from datetime import datetime
from django.contrib import messages
import calendar
import pandas as pd
from django.urls import reverse
from django.db.models import Sum
from django.views.decorators.http import require_POST



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
    total_due = 0
    total_payment_received = 0

    current_month_sale = 0
    current_month_commission = 0
    current_month_discount = 0
    current_month_due = 0
    current_month_payment_received = 0

    previous_month_sale = 0
    previous_month_commission = 0
    previous_month_discount = 0
    previous_month_due = 0
    previous_month_payment_received = 0

    # Initialize aggregates for adai
    total_due_adai = 0
    total_advance_adai = 0

    current_month_due_adai = 0
    current_month_advance_adai = 0

    previous_month_due_adai = 0
    previous_month_advance_adai = 0

    # Process sales data from Sale model
    sales_data = Sale.objects.all()
    for sale in sales_data:
        sale_total = float(sale.total_price or 0)
        sale_commission = float(sale.discount or 0)
        sale_discount = float(sale.less or 0)
        sale_due = float(sale.due or 0)
        sale_payment_received = float(sale.payment_received or 0)
        sale_date = sale.date

        total_sale_all += sale_total
        total_commission_all += sale_commission
        total_discount_all += sale_discount
        total_due += sale_due
        total_payment_received += sale_payment_received
        print(sale_total,sale_commission,sale_discount,sale_due,sale_payment_received)
        if sale_date:
            # Current month data
            if sale_date.year == selected_year and sale_date.month == selected_month:
                current_month_sale += sale_total
                current_month_commission += sale_commission
                current_month_discount += sale_discount
                current_month_due += sale_due
                current_month_payment_received += sale_payment_received

            # Previous month data
            if sale_date.year == previous_year and sale_date.month == previous_month:
                previous_month_sale += sale_total
                previous_month_commission += sale_commission
                previous_month_discount += sale_discount
                previous_month_due += sale_due
                previous_month_payment_received += sale_payment_received

    # Process adai data from Adai model
    adai_data = Adai.objects.all()
    for adai in adai_data:
        adai_due = float(adai.due or 0)
        adai_advance = float(adai.advance or 0)
        adai_date = adai.date

        total_due_adai += adai_due
        total_advance_adai += adai_advance

        if adai_date:
            # Current month data
            if adai_date.year == selected_year and adai_date.month == selected_month:
                current_month_due_adai += adai_due
                current_month_advance_adai += adai_advance

            # Previous month data
            if adai_date.year == previous_year and adai_date.month == previous_month:
                previous_month_due_adai += adai_due
                previous_month_advance_adai += adai_advance

    # Calculate total due by subtracting collected dues (adai) from sales dues
    total_due = total_due - total_due_adai
    current_month_due = current_month_due - current_month_due_adai
    previous_month_due = previous_month_due - previous_month_due_adai

    # Ensure due amounts don't go negative
    total_due = max(0, total_due)
    current_month_due = max(0, current_month_due)
    previous_month_due = max(0, previous_month_due)

    # Calculate total due and advance by summing all Customer dues and advances
    from django.db.models import Sum
    total_due = Customer.objects.aggregate(total_due=Sum('due'))['total_due'] or 0
    total_advance = Customer.objects.aggregate(total_advance=Sum('Advance'))['total_advance'] or 0
    current_month_due = max(0, current_month_due)
    # Remove previous_month_due from context if present

    # Prepare context for the template
    context = {
        "selected_month": selected_month,
        "selected_year": selected_year,
        "months": [{"number": i, "name": calendar.month_name[i]} for i in range(1, 13)],
        "years": range(2020, 2031),
        "total_sales": {
            "previous_month": previous_month_sale+previous_month_discount,
            "current_month": current_month_sale+current_month_discount,
            "all_time": total_sale_all+total_discount_all,
        },
        "total_commission": {
            "previous_month": previous_month_commission,
            "current_month": current_month_commission,
            "all_time": total_commission_all,
        },
        "after_discount": {
            "previous_month": previous_month_sale - previous_month_commission,
            "current_month": current_month_sale - current_month_commission,
            "all_time": total_sale_all - total_commission_all,
        },
        "less": {
            "previous_month": previous_month_discount,
            "current_month": current_month_discount,
            "all_time": total_discount_all,
        },
        "due": {
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
            "previous_month": previous_month_advance_adai,
            "current_month": current_month_advance_adai,
            "all_time": total_advance_adai,
        },
        "mot_adai": {
            "previous_month": previous_month_advance_adai+previous_month_due_adai+previous_month_payment_received,
            "current_month": current_month_advance_adai+current_month_due_adai+current_month_payment_received,
            "all_time": total_advance_adai+total_due_adai+total_payment_received,
        },
    }

    return render(request, "Report.html", context)

@csrf_exempt
def salesman_list(request):
    if request.method == 'POST':
        # Adding a new salesman
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

    # Fetching all salesmen
    salesmen_list = Salesman.objects.all()
    # Calculate adai (sum of due and advance) for each salesman
    salesmen_with_adai = []
    for salesman in salesmen_list:
        adai_records = Adai.objects.filter(salesman=salesman)
        total_due = sum(a.due for a in adai_records)
        total_advance = sum(a.advance for a in adai_records)
        total_adai = total_due + total_advance
        s = {
            'id': salesman.id,
            'name': salesman.name,
            'code': salesman.code,
            'area': salesman.area,
            'phone': salesman.phone,
            'comission': salesman.comission,
            'basic_salary': getattr(salesman, 'basic_salary', 0),
            'salescomission': salesman.salescomission,
            'adai': total_adai,
        }
        s['json'] = json.dumps(s)
        salesmen_with_adai.append(s)
    return render(request, 'Salesman.html', {'salesmen': salesmen_with_adai})

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
        # Adding a new customer
        name = request.POST.get('name')
        code = request.POST.get('code')
        area = request.POST.get('area')
        phone = request.POST.get('phone')
        nid = request.POST.get('nid')
        due = float(request.POST.get('due', 0) or 0)
        if name and code and area and phone and nid:
            Customer.objects.create(
                name=name,
                code=code,
                area=area,
                phone=phone,
                nid=nid,
                due=due,
                Advance=0,
                Paid=0
            )
            return redirect('customer_list')

    # Fetching all customers
    customers = Customer.objects.all()

    # Fetching all sales
    sales_data = Sale.objects.all()

    # Calculate total and current month purchases for each customer
    customer_totals = {}
    current_month = datetime.now().month
    current_year = datetime.now().year

    for sale in sales_data:
        customer_obj = sale.customer
        sale_date = sale.date
        total_price = float(sale.total_price or 0)

        if customer_obj:
            customer_name = customer_obj.name
            if customer_name not in customer_totals:
                customer_totals[customer_name] = {'total_buy': 0, 'current_month_buy': 0}

            # Add to total purchases
            customer_totals[customer_name]['total_buy'] += total_price

            # Add to current month purchases if the sale is in the current month and year
            if sale_date.year == current_year and sale_date.month == current_month:
                customer_totals[customer_name]['current_month_buy'] += total_price

    # Merge customer totals into the customer list
    customer_list_data = []
    for customer in customers:
        customer_name = customer.name
        customer_dict = {
            'id': customer.id,
            'name': customer.name,
            'code': customer.code,
            'area': customer.area,
            'phone': customer.phone,
            'nid': customer.nid,
            'due': customer.due,
            'Advance': customer.Advance,
            'Paid': customer.Paid,
            'total_buy': customer_totals.get(customer_name, {}).get('total_buy', 0),
            'current_month_buy': customer_totals.get(customer_name, {}).get('current_month_buy', 0),
        }
        customer_dict['json'] = json.dumps(customer_dict)
        customer_list_data.append(customer_dict)

    # Pass the updated customer list to the template
    return render(request, 'Customer.html', {'customer': customer_list_data})

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

        # Ensure all required fields are provided
        if code and name and size and rate is not None and production_cost is not None:
            Product.objects.create(
                code=code,
                name=name,
                size=size,
                rate=rate,
                add_stock=0,
                production_cost=production_cost,
                total_sales=0,
                total_stock=0
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

    customers_data = [
        {
            'id': customer.id,
            'name': customer.name,
            'code': customer.code,
            'area': customer.area,
            'due': customer.due,           # <-- Add this line
            'Advance': customer.Advance,   # <-- And this line
            # Add other fields as needed
        }
        for customer in filtered_customers
    ]

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

        # Calculate total less from all products
        total_less_products = sum(float(p.get('less', 0)) for p in products_sold)
        # Final less is sum of all product less + less input
        final_less = total_less_products + less_input
        print(final_less,total_less_products,less_input)

        # Calculate due on backend (ignore due from frontend)
        discount_amount = (discount_percent / 100) * total_price
        print(discount_amount,discount_percent,total_price)
        sale_due = total_price - discount_amount
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

        # Get customer
        try:
            customer = Customer.objects.get(id=cid)
            customer_name = customer.name
            customer_phone = customer.phone
            advance_amount = float(customer.Advance or 0)
            customer_due = float(customer.due or 0)
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

        # --- Handle advance and payment: Only apply to this sale's due, not old due ---
        # sale_due is already calculated above
        advance_used = 0
        payment_used = 0

        # Only use advance if payment_received is not provided or is less than total_price
        if payment_received == 0 or payment_received < total_price:
            if advance_amount >= sale_due:
                advance_used = sale_due
                customer.Advance -= advance_used
                payment_used = 0
                sale_due = 0
            else:
                advance_used = advance_amount
                customer.Advance = 0
                remaining_due = sale_due - advance_used
                if payment_received >= remaining_due:
                    payment_used = remaining_due
                    payment_received -= remaining_due
                    sale_due = 0
                else:
                    payment_used = payment_received
                    sale_due = remaining_due - payment_received
                    # payment_received = 0
        else:
            # When payment_received >= total_price, don't use advance
            if payment_received >= sale_due:
                payment_used = sale_due
                payment_received -= sale_due
                sale_due = 0
            else:
                payment_used = payment_received
                sale_due = sale_due - payment_received

        # Update customer due and paid
        customer.due = customer_due + sale_due  # Always add this sale's due to old due
        customer.Paid += payment_used
        customer.save()
          # Print after updating due

        # Update salesman commission
        commission_amount = float(commission_rate / 100) * payment_used
        salesman.salescomission += commission_amount
        salesman.save()

        # Check product stock before processing sale
        for product in products_sold:
            product_id = product.get('id')
            quantity_sold = float(product.get('quantity', 0))
            if product_id and quantity_sold:
                try:
                    prod = Product.objects.get(id=product_id)
                    if prod.total_stock <= 0:
                        return JsonResponse({'error': 'No product in stock', 'message': f'Product "{prod.name}" is out of stock.'}, status=400)
                    if quantity_sold > prod.total_stock:
                        return JsonResponse({'error': 'Insufficient stock', 'message': f'Product "{prod.name}" has only {prod.total_stock} units in stock, but {quantity_sold} units were requested.'}, status=400)
                except Product.DoesNotExist:
                    return JsonResponse({'error': 'Product not found', 'message': 'One or more products not found.'}, status=404)

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
            total_price=total_price,
            discount=(discount_percent / 100) * total_price,
            less=final_less,  # Save sum of all product less + less input
            payment_received=float(data.get('payment_received', 0)),
            due=sale_due,
            date=datetime.now().date(),
            time=datetime.now().time(),
            comission=commission_amount,
            invoice_number=invoice_number  # Add the generated invoice number
        )
        print(payment_used,"hfhfe")
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
            print("SMS API response:", response.text)
            
        except Exception as sms_error:
            print("SMS sending error:", sms_error)

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
        sales = Sale.objects.all()

    for sale in sales:
        sales_data.append({
            'id': sale.id,
            'salesman': sale.salesman.name if sale.salesman else '',
            'customer': sale.customer.name if sale.customer else '',
            'products': sale.products,
            'total_price': (sale.total_price - sale.discount - sale.less),
            'discount': sale.discount,
            'less': sale.less,
            'payment_received': sale.payment_received,
            'due': sale.due,
            'date': sale.date.strftime('%Y-%m-%d') if sale.date else '',
            'time': sale.time.strftime('%H:%M:%S') if sale.time else '',
            'comission': sale.comission,
            'invoice_number': sale.invoice_number if sale.invoice_number else 'N/A'
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
                
                # Update customer
                if customer:
                    
                    # When deleting a sale, we need to:
                    # 1. Add the original due amount to advance (since it was paid)
                    # 2. Subtract the original paid amount from Paid
                    customer.Advance += original_due
                    customer.Paid -= original_paid
                    
                    # Ensure no negative values
                    customer.due = max(0, customer.due)
                    customer.Advance = max(0, customer.Advance)
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
                
                # Delete the sale
                sale.delete()
                
                messages.success(request, "Sale deleted successfully!")
                
                # Recalculate the customer's Advance and Due from all remaining records
                if customer:
                    from django.db.models import Sum
                    # Advance: sum of all Adai advances for this customer
                    total_advance = Adai.objects.filter(customer=customer).aggregate(total=Sum('advance'))['total'] or 0
                    # Due: sum of all Sale dues for this customer minus sum of all Adai dues for this customer
                    total_sale_due = Sale.objects.filter(customer=customer).aggregate(total=Sum('due'))['total'] or 0
                    total_adai_due = Adai.objects.filter(customer=customer).aggregate(total=Sum('due'))['total'] or 0
                    customer.Advance = total_advance
                    customer.due = total_sale_due - total_adai_due
                    if customer.due < 0:
                        customer.due = 0
                    customer.save()
                
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

def download_cash_memo(request, sale_id):
    try:
        # Get sale data from Django ORM
        sale = get_object_or_404(Sale, id=sale_id)
        customer = sale.customer
        salesman = sale.salesman

        # Calculate previous due (customer.due before this sale)
        # previous_due = customer's due before this bill
        previous_due = (customer.due or 0) - (sale.due or 0)
        # Total due for this bill = previous due + this bill's due
        total_due = previous_due + (sale.due or 0)

        # Calculate net bill
        net_bill = (sale.total_price or 0) - (sale.discount or 0) - (sale.less or 0)

        # Prepare products list (if you store as JSON, otherwise adjust as needed)
        products = sale.products if hasattr(sale, 'products') else []

        context = {
            'sale': sale,
            'salesman': salesman,
            'customer': customer,
            'products': products,
            'net_bill': net_bill,
            'total_due': total_due,
            'previous_due': previous_due,
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
            'name': product.name,
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
        for adai in Adai.objects.all()
    ]

    context = {
        'salesman': salesman_data,    # Each salesman should include a 'name' field
        'customers': customers_data,  # Each customer should include a 'name' field
        'adai': adai_data,
    }
    
    return render(request, 'addsales.html', context)

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

            # Update the customer's Advance if applicable
            if customer and advance_amount > 0:
                if customer.Advance >= advance_amount:
                    customer.Advance -= advance_amount
                    customer.save()

            # Update the salesman's commission
            if salesman:
                # Subtract only the commission that was originally added for this Adai
                salesman.salescomission -= float(adai.sales_comission or 0)
                if salesman.salescomission < 0:
                    salesman.salescomission = 0
                salesman.save()

            # Delete the adai record
            adai.delete()

            # Recalculate the customer's Advance and Due from all remaining records
            if customer:
                from django.db.models import Sum
                # Advance: sum of all Adai advances for this customer
                total_advance = Adai.objects.filter(customer=customer).aggregate(total=Sum('advance'))['total'] or 0
                # Due: sum of all Sale dues for this customer minus sum of all Adai dues for this customer
                total_sale_due = Sale.objects.filter(customer=customer).aggregate(total=Sum('due'))['total'] or 0
                total_adai_due = Adai.objects.filter(customer=customer).aggregate(total=Sum('due'))['total'] or 0
                customer.Advance = total_advance
                customer.due = total_sale_due - total_adai_due
                if customer.due < 0:
                    customer.due = 0
                customer.save()

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

            # Start transaction
            from django.db import transaction
            with transaction.atomic():
                if int(money_type) == 1:  # Handling 'Due' (customer pays due)
                    if customer.due <= 0:
                        return JsonResponse({'status': 'error', 'error': 'Customer has no due to update.'})
                    
                    # If payment is more than due, add extra to advance
                    if quantity >= customer.due:
                        advance_to_add = quantity - customer.due
                        paid_due = customer.due
                        customer.due = 0
                        customer.Advance += advance_to_add
                    else:
                        paid_due = quantity
                        advance_to_add = 0
                        customer.due -= quantity
                    customer.save()

                    # Create Adai record for due payment and advance
                    adai = Adai.objects.create(
                        due=paid_due,
                        advance=advance_to_add,
                        date=adai_date,
                        salesman=salesman,
                        customer=customer,
                        sales_comission=(commission_rate / 100) * quantity
                    )

                else:  # Handling 'Advance'
                    # If customer has due, do not allow advance entry
                    if customer.due > 0:
                        return JsonResponse({'status': 'error', 'error': 'Please clear due first.'})
                    # If customer has no due, allow advance entry
                    advance_to_use = quantity
                    due_paid = 0
                    advance_left = 0

                    customer.Advance += advance_to_use
                    advance_left = advance_to_use
                    customer.save()

                    # Create Adai record for advance payment
                    adai = Adai.objects.create(
                        due=due_paid,
                        advance=advance_left,
                        date=adai_date,
                        salesman=salesman,
                        customer=customer,
                        sales_comission=(commission_rate / 100) * quantity
                    )

                # Update salesman's commission
                commission_amount = (commission_rate / 100) * quantity
                salesman.salescomission += commission_amount
                salesman.save()

                # Log the transaction
               

                return JsonResponse({
                    'status': 'success',
                    'message': 'Transaction completed successfully',
                    'details': {
                        'customer_due': customer.due,
                        'customer_advance': customer.Advance,
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

            # Calculate the difference between the old and new values
            due_difference = (new_due - old_due) if new_due is not None else 0
            advance_difference = (new_advance - old_advance) if new_advance is not None else 0

            # Handle cases where the customer has no due
            if customer.due <= 0 and due_difference > 0:
                return JsonResponse({'status': 'error', 'message': 'Customer has no due to update.'})

            # Update the customer's due and advance if there are changes
            if due_difference != 0:
                customer_due_adjustment = -due_difference  # Reverse the sign of the difference
                if customer.due + customer_due_adjustment < 0:
                    return JsonResponse({'status': 'error', 'message': 'Customer due cannot be negative.'})
                customer.due += customer_due_adjustment
                customer.save()

            if advance_difference != 0:
                customer.Advance += advance_difference
                customer.save()

            # Update the salesman's commission
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

            # Calculate the difference between the old and new values
            due_difference = (new_due - old_due) if new_due is not None else 0
            advance_difference = (new_advance - old_advance) if new_advance is not None else 0

            # Handle cases where the customer has no due
            if customer.due <= 0 and due_difference > 0:
                return JsonResponse({'status': 'error', 'message': 'Customer has no due to update.'})

            # Update the customer's due and advance if there are changes
            if due_difference != 0:
                customer_due_adjustment = -due_difference  # Reverse the sign of the difference
                if customer.due + customer_due_adjustment < 0:
                    return JsonResponse({'status': 'error', 'message': 'Customer due cannot be negative.'})
                customer.due += customer_due_adjustment
                customer.save()

            if advance_difference != 0:
                customer.Advance += advance_difference
                customer.save()

            # Update the salesman's commission
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
        narration = request.POST.get('narration')
        suplier = request.POST.get('suplier')
        debit = float(request.POST.get('debit') or 0)
        credit = float(request.POST.get('credit') or 0)
        balance = float(request.POST.get('balance') or 0)
        # Only create if supplier does not exist
        if suplier and not Expence.objects.filter(suplier=suplier).exists():
            Expence.objects.create(
                date=date,
                narration=narration,
                due=debit,
                advance=credit,
                total_pay=balance,
                suplier=suplier
            )
        return redirect('expence_list')

    # Fetch all suppliers (one row per supplier)
    expence_list_data = Expence.objects.all()
    return render(request, 'expence_list.html', {'expence_list': expence_list_data})


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
    if request.method == 'POST':
        # Get the selected salesman, month, and year from the form
        salesman_id = request.POST.get('salesman')
        selected_month = int(request.POST.get('month'))
        selected_year = int(request.POST.get('year'))

        # Fetch the salesman details
        try:
            salesman = Salesman.objects.get(id=salesman_id)
        except Salesman.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Salesman not found.'})

        # Fetch sales for the selected salesman and date
        sales = Sale.objects.filter(
            salesman=salesman,
            date__year=selected_year,
            date__month=selected_month
        )
        filtered_sales = [
            {
                'date': sale.date.strftime('%Y-%m-%d'),
                'customer': sale.customer.name,
                'total_price': sale.total_price,
                'discount': sale.discount,
                'payment_received': sale.payment_received,
                'due': sale.due,
                'comission': sale.comission,
                'invoice_number': sale.invoice_number or 'N/A'
            }
            for sale in sales
        ]

        # Fetch adai data for the selected salesman and date
        adai_records = Adai.objects.filter(
            salesman=salesman,
            date__year=selected_year,
            date__month=selected_month
        )
        filtered_adai = [
            {
                'date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
                'customer': adai.customer.name if adai.customer else '',
                'due': adai.due,
                'advance': adai.advance,
            }
            for adai in adai_records
        ]

        return render(request, 'salesmanreport.html', {
            'salesman_name': salesman.name,
            'filtered_sales': filtered_sales,
            'filtered_adai': filtered_adai,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
            'years': range(2020, 2031),
        })

    # Default view (GET request)
    salesmen = Salesman.objects.all()
    salesmen_list = [{'id': s.id, 'name': s.name} for s in salesmen]
    return render(request, 'salesmanreport.html', {
        'salesmen': salesmen_list,
        'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
        'years': range(2020, 2031),
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
        filtered_sales = [
            {
                'date': sale.date.strftime('%Y-%m-%d'),
                'salesman': sale.salesman.name if sale.salesman else '',
                'total_price': sale.total_price,
                'discount': sale.discount,
                'payment_received': sale.payment_received,
                'due': sale.due,
                'invoice_number': sale.invoice_number or 'N/A'
            }
            for sale in sales_records
        ]

        return render(request, 'filter_customer_sales.html', {
            'customer_name': customer.name,
            'filtered_sales': filtered_sales,
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

# Hardcoded credentials
USERNAME = "admin"
PASSWORD = "password123"

@csrf_exempt
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        # Check credentials
        if username == USERNAME and password == PASSWORD:
            return redirect("dashboard")  # Redirect to the dashboard
        else:
            return render(request, "login.html", {"error": "Invalid username or password"})

    return render(request, "login.html")


@csrf_exempt
def customer_ledger(request):
    customers = Customer.objects.all()
    years = range(2020, 2031)
    ledger_rows = []
    customer_name = ""
    selected_year = None
    opening_balance = 0

    if request.method == "POST":
        customer_id = request.POST.get("customer")
        year = request.POST.get("year")

        if customer_id and year:
            selected_year = int(year)
            try:
                customer = Customer.objects.get(id=customer_id)
                customer_name = customer.name

                # Get all sales and adai for the customer in the selected year
                sales = Sale.objects.filter(customer=customer, date__year=selected_year)
                adais = Adai.objects.filter(customer=customer, date__year=selected_year)

                # Get all previous sales and adai for opening balance
                prev_sales = Sale.objects.filter(customer=customer, date__year__lt=selected_year)
                prev_adai = Adai.objects.filter(customer=customer, date__year__lt=selected_year)

                # Calculate opening balance (Credit - Debit up to previous year)
                opening_credit = sum(a.advance for a in prev_adai)
                opening_debit = sum(s.total_price for s in prev_sales) + sum(a.due for a in prev_adai)
                opening_balance = opening_credit - opening_debit

                # Gather all transactions (sales and adai) for the year
                transactions = []
                for sale in sales:
                    # Debit for the net sale (after discount and less)
                    transactions.append({
                        "date": sale.date,
                        "particulars": "Sale",
                        "debit": sale.total_price - sale.discount - sale.less,
                        "credit": 0,
                        "desc": ", ".join([p.get("name", "") for p in sale.products]) if sale.products else "",
                        "invoice_number": sale.invoice_number if sale.invoice_number else "N/A"
                    })
                    # Credit for payment received at sale time
                    if sale.payment_received and sale.payment_received > 0:
                        transactions.append({
                            "date": sale.date,
                            "particulars": "Payment at Sale",
                            "debit": 0,
                            "credit": sale.payment_received,
                            "desc": "",
                            "invoice_number": sale.invoice_number if sale.invoice_number else "N/A"
                        })
                for adai in adais:
                    if adai.due > 0:
                        transactions.append({
                            "date": adai.date,
                            "particulars": "Due Payment",
                            "debit": 0,
                            "credit": adai.due,
                            "desc": "",
                            "invoice_number": "Adai"
                        })
                    if adai.advance > 0:
                        transactions.append({
                            "date": adai.date,
                            "particulars": "Advance",
                            "debit": 0,
                            "credit": adai.advance,
                            "desc": "",
                            "invoice_number": "Adai"
                        })

                # --- Add Initial Due Adjustment if needed ---
                # Calculate due from all sales and adai (all time)
                calculated_due = sum(sale.due for sale in Sale.objects.filter(customer=customer))
                calculated_due -= sum(adai.due for adai in Adai.objects.filter(customer=customer))
                manual_adjustment = customer.due - calculated_due
                if manual_adjustment != 0:
                    transactions.append({
                        "date": None,
                        "particulars": "Initial Due Adjustment",
                        "debit": manual_adjustment if manual_adjustment > 0 else 0,
                        "credit": -manual_adjustment if manual_adjustment < 0 else 0,
                        "desc": "",
                        "invoice_number": "INIT-DUE"
                    })

                # Sort all transactions by date, putting None dates (adjustments) first
                def sort_key(x):
                    if x["date"] is None:
                        return (0, None)
                    return (1, x["date"])
                transactions.sort(key=sort_key)

                # Build ledger rows with running balance
                balance = opening_balance
                ledger_rows = []
                for t in transactions:
                    balance = balance + t["credit"] - t["debit"]
                    ledger_rows.append({
                        "date": t["date"].strftime("%d/%m/%y") if t["date"] else "",
                        "particulars": t["particulars"] + (" - " + t["desc"] if t["desc"] else ""),
                        "debit": t["debit"] if t["debit"] else 0,
                        "credit": t["credit"] if t["credit"] else 0,
                        "balance": balance,
                        "invoice_number": t["invoice_number"]
                    })

                # Calculate totals for the summary
                total_added = sum(row['credit'] or 0 for row in ledger_rows)
                total_spent = sum(row['debit'] or 0 for row in ledger_rows)
                current_balance = ledger_rows[-1]['balance'] if ledger_rows else opening_balance

            except Customer.DoesNotExist:
                customer_name = ""
                ledger_rows = []
                opening_balance = 0
                total_added = 0
                total_spent = 0
                current_balance = 0
        else:
            total_added = 0
            total_spent = 0
            current_balance = 0
    else:
        total_added = 0
        total_spent = 0
        current_balance = 0

    context = {
        "customers": customers,
        "years": years,
        "ledger_rows": ledger_rows,
        "customer_name": customer_name,
        "selected_year": selected_year,
        "opening_balance": opening_balance,
        "total_added": total_added,
        "total_spent": total_spent,
        "current_balance": current_balance,
    }
    return render(request, "ledger_customer.html", context)

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

@csrf_exempt
def download_salesman_report(request):
    salesman_name = request.GET.get('salesman')
    month = int(request.GET.get('month'))
    year = int(request.GET.get('year'))

    try:
        salesman = Salesman.objects.get(name=salesman_name)
        
        # Get sales data for selected month
        sales = Sale.objects.filter(
            salesman=salesman,
            date__year=year,
            date__month=month
        )
        
        # Get adai records for selected month
        adai_records = Adai.objects.filter(
            salesman=salesman,
            date__year=year,
            date__month=month
        )

        # Get all sales for total due calculation (all time)
        all_sales = Sale.objects.filter(salesman=salesman)

        # Calculate totals
        total_sales = sum(sale.total_price for sale in sales)  # Only for selected month
        total_collection = sum(sale.payment_received for sale in sales) + sum(adai.due for adai in adai_records)  # Only for selected month
        total_commission = sum(sale.comission for sale in sales)  # Only for selected month
        total_due = sum(sale.due for sale in all_sales)  # All time due

        # Format sales data
        sales_data = [
            {
                'date': sale.date.strftime('%Y-%m-%d'),
                'customer': sale.customer.name,
                'total_price': sale.total_price,
                'payment_received': sale.payment_received,
                'due': sale.due,
                'invoice_number': sale.invoice_number or 'N/A',
                'commission': sale.comission
            }
            for sale in sales
        ]

        # Format adai data
        adai_data = [
            {
                'date': adai.date.strftime('%Y-%m-%d'),
                'customer': adai.customer.name,
                'due': adai.due,
                'advance': adai.advance
            }
            for adai in adai_records
        ]

        context = {
            'salesman_name': salesman_name,
            'month_name': calendar.month_name[month],
            'year': year,
            'current_date': datetime.now().strftime('%Y-%m-%d'),
            'total_sales': total_sales,
            'total_collection': total_collection,
            'total_commission': total_commission,
            'total_due': total_due,
            'sales': sales_data,
            'adai_records': adai_data
        }

        return render(request, 'salesman_report_template.html', context)

    except Salesman.DoesNotExist:
        return HttpResponse("Salesman not found", status=404)
    except Exception as e:
        return HttpResponse(f"Error generating report: {str(e)}", status=500)

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

@csrf_exempt
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
    customers_data = [
        {
            'id': customer.id,
            'name': customer.name,
            'code': customer.code,
            'area': customer.area,
            'due': customer.due,
            'Advance': customer.Advance,
        }
        for customer in customers
    ]

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
                less=final_less,
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
                payment_received=pending_sale.payment_received,
                due=pending_sale.due,
                date=pending_sale.date,
                time=pending_sale.time,
                comission=pending_sale.comission,
                invoice_number=new_invoice_number
            )

            # Update customer due and paid
            customer = pending_sale.customer
            customer.due += pending_sale.due
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
        customer_id = request.POST.get('customer')
        invoice_number = request.POST.get('invoice')
        expense_type = request.POST.get('expense_type')
        amount = request.POST.get('amount')
        try:
            salesman = Salesman.objects.get(id=salesman_id)
            customer = Customer.objects.get(id=customer_id)
            MarketingCost.objects.create(
                date=date,
                salesman=salesman,
                customer_name=customer.name,
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
    selected_date = request.GET.get('date', '')
    marketing_costs = MarketingCost.objects.all().order_by('-date')
    if selected_salesman:
        marketing_costs = marketing_costs.filter(salesman_id=selected_salesman)
    if selected_date:
        marketing_costs = marketing_costs.filter(date=selected_date)
    context = {
        'salesmen': salesmen,
        'selected_salesman': selected_salesman,
        'selected_date': selected_date,
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
        return JsonResponse({'status': 'success'})
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