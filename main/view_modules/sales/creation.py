"""Sales views: creation."""

from ..common import *
from ..catalogue import product_list

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

        # Validate products list
        if not products_sold or len(products_sold) == 0:
            return JsonResponse({'error': 'At least one product is required.'}, status=400)

        # --- CHECK PRODUCT STOCK FIRST (before any data modifications) ---
        for product in products_sold:
            product_id = product.get('id')
            quantity_sold = float(product.get('quantity', 0))
            
            if not product_id:
                return JsonResponse({'error': 'Product ID is required for all products.'}, status=400)
            
            if quantity_sold <= 0:
                return JsonResponse({'error': 'Product quantity must be greater than 0.'}, status=400)
            
            try:
                prod = Product.objects.get(id=product_id)
                if prod.total_stock <= 0:
                    return JsonResponse({'error': 'No product in stock', 'message': f'Product "{prod.name}" is out of stock.'}, status=400)
                if quantity_sold > prod.total_stock:
                    return JsonResponse({'error': 'Insufficient stock', 'message': f'Product "{prod.name}" has only {prod.total_stock} units in stock, but {quantity_sold} units were requested.'}, status=400)
            except Product.DoesNotExist:
                return JsonResponse({'error': 'Product not found', 'message': f'Product with ID {product_id} not found.'}, status=404)

        # Calculate total less from all products
        total_less_products = sum(float(p.get('less', 0)) for p in products_sold)
        # Final less is sum of all product less + less input
        final_less = total_less_products + less_input

        # Calculate due on backend (ignore due from frontend)
        discount_amount = (discount_percent / 100) * total_price
        sale_due = total_price - discount_amount-less_input
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

        # Get customer and use calculated due/advance (initial + sales + adai)
        try:
            customer = Customer.objects.get(id=cid)
            customer_name = customer.name
            customer_phone = customer.phone
            _current_due, current_advance = get_customer_calculated_due_advance(customer)
            advance_amount = current_advance
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

        # Use sale date from request or current date (accept 'sale_date' or 'saleDate')
        sale_date_str = (data.get('sale_date') or data.get('saleDate') or '').strip()
        if isinstance(sale_date_str, str) and len(sale_date_str) >= 10:
            try:
                sale_date = datetime.strptime(sale_date_str[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                sale_date = datetime.now().date()
        else:
            sale_date = datetime.now().date()
        sale_time = datetime.now().time()

        # --- Handle advance and payment: Only apply to this sale's due, not old due ---
        # sale_due is already calculated above
        advance_used = 0
        payment_used = 0

        # Only use advance if payment_received is not provided or is less than total_price
        if payment_received == 0 or payment_received < total_price:
            if advance_amount >= sale_due:
                advance_used = sale_due
                payment_used = 0
                sale_due = 0
            else:
                advance_used = advance_amount
                remaining_due = sale_due - advance_used
                if payment_received >= remaining_due:
                    payment_used = remaining_due
                    payment_received -= remaining_due
                    sale_due = 0
                else:
                    payment_used = payment_received
                    sale_due = remaining_due - payment_received
        else:
            if payment_received >= sale_due:
                payment_used = sale_due
                payment_received -= sale_due
                sale_due = 0
            else:
                payment_used = payment_received
                sale_due = sale_due - payment_received

        # Customer.due and Customer.Advance are initial only (not updated here). Only update Paid.
        customer.Paid += payment_used
        customer.save()

        # Commission is calculated from DB (sum of Sale.comission + Adai.sales_comission), so do not update salesman.salescomission here.
        commission_amount = float(commission_rate / 100) * payment_used

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
            total_price=total_price+final_less-less_input,
            discount=(discount_percent / 100) * total_price,
            less=final_less,  # final_less (unchangable)
            total_less_products=total_less_products,
            less_input=less_input,
            payment_received=float(data.get('payment_received', 0)),
            advance_used=advance_used,
            due=sale_due,
            date=sale_date,
            time=sale_time,
            comission=commission_amount,
            invoice_number=invoice_number
        )

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
        except Exception as sms_error:
            pass

        return JsonResponse({'status': 'success', 'message': 'Sale data saved and SMS sent.'}, status=200)
    else:
        return JsonResponse({'error': 'POST request required.'}, status=400)
