"""Customers views: reports."""

from ..common import *

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
