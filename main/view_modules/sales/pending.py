"""Sales views: pending."""

from ..common import *
from ..catalogue import product_list

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
                less=final_less,  # final_less (unchangable)
                total_less_products=total_less_products,
                less_input=less_input,
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
                total_less_products=getattr(pending_sale, 'total_less_products', 0),
                less_input=getattr(pending_sale, 'less_input', 0),
                payment_received=pending_sale.payment_received,
                due=pending_sale.due,
                date=pending_sale.date,
                time=pending_sale.time,
                comission=pending_sale.comission,
                invoice_number=new_invoice_number
            )

            # Update customer Paid only (Customer.due/Advance are initial-only; balance is calculated from sales+adai)
            customer = pending_sale.customer
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
