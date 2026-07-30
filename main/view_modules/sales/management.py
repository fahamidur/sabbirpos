"""Sales views: management."""

from ..common import *
from ..catalogue import product_list

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
