"""Salesmen views: reports."""

from ..common import *
from ..common import _salesman_report_date_filter

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
