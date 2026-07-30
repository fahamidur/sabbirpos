"""Catalogue views: reports."""

from ..common import *

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
