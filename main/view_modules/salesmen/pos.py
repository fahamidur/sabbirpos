"""Salesmen views: pos."""

from ..common import *

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
