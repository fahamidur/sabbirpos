"""Sales views: listing."""

from ..common import *
from ..catalogue import product_list

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
