"""Sales views: pos."""

from ..common import *
from ..catalogue import product_list

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
