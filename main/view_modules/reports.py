"""Reports views."""

from .common import *
from .marketing import marketing_cost

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
def profit_report(request):
    from main.models import Sale, MarketingCost, Product
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


