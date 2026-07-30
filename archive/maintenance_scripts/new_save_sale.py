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

        # Calculate total less from all products
        total_less_products = sum(float(p.get('less', 0)) for p in products_sold)
        # Final less is sum of all product less + less input
        final_less = total_less_products + less_input
        print(final_less, total_less_products, less_input)

        # Calculate net amount after discount and less
        discount_amount = (discount_percent / 100) * total_price
        net_amount = total_price - discount_amount - final_less
        if net_amount < 0:
            net_amount = 0

        # Get salesman
        try:
            salesman = Salesman.objects.get(id=sid)
            commission_rate = float(salesman.comission)
            salesman_name = salesman.name
            salesman_code = salesman.code
        except Salesman.DoesNotExist:
            return JsonResponse({'error': 'Salesman not found.'}, status=404)

        # Get customer
        try:
            customer = Customer.objects.get(id=cid)
            customer_name = customer.name
            customer_phone = customer.phone
            customer_due = float(customer.due or 0)
            customer_advance = float(customer.Advance or 0)
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

        # --- NEW PAYMENT LOGIC ---
        # Calculate how much customer needs to pay
        total_required = net_amount
        
        # Calculate new due and advance
        if customer_due > 0:
            # Customer has existing due
            if total_required > payment_received:
                # Not enough payment, add to due
                new_due = customer_due + (total_required - payment_received)
                new_advance = customer_advance
                payment_used = payment_received
            else:
                # Payment covers the amount, reduce due
                excess_payment = payment_received - total_required
                new_due = max(0, customer_due - excess_payment)
                new_advance = customer_advance + max(0, excess_payment - customer_due)
                payment_used = payment_received
        else:
            # Customer has no existing due
            if total_required > payment_received:
                # Not enough payment, add to due
                new_due = total_required - payment_received
                new_advance = customer_advance
                payment_used = payment_received
            else:
                # Payment covers the amount, add excess to advance
                excess_payment = payment_received - total_required
                new_due = 0
                new_advance = customer_advance + excess_payment
                payment_used = payment_received

        # Update customer
        customer.due = new_due
        customer.Advance = new_advance
        customer.Paid += payment_used
        customer.save()

        # Update salesman commission
        commission_amount = float(commission_rate / 100) * payment_used
        salesman.salescomission += commission_amount
        salesman.save()

        # Check product stock before processing sale
        for product in products_sold:
            product_id = product.get('id')
            quantity_sold = float(product.get('quantity', 0))
            if product_id and quantity_sold:
                try:
                    prod = Product.objects.get(id=product_id)
                    if prod.total_stock <= 0:
                        return JsonResponse({'error': 'No product in stock', 'message': f'Product "{prod.name}" is out of stock.'}, status=400)
                    if quantity_sold > prod.total_stock:
                        return JsonResponse({'error': 'Insufficient stock', 'message': f'Product "{prod.name}" has only {prod.total_stock} units in stock, but {quantity_sold} units were requested.'}, status=400)
                except Product.DoesNotExist:
                    return JsonResponse({'error': 'Product not found', 'message': 'One or more products not found.'}, status=404)

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

        # Save sale record
        sale = Sale.objects.create(
            salesman=salesman,
            customer=customer,
            products=products_sold,
            total_price=total_price,
            discount=discount_amount,
            less=final_less,
            payment_received=payment_used,
            due=new_due - customer_due,  # Only the new due from this sale
            date=datetime.now().date(),
            time=datetime.now().time(),
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
                f"Discount: {discount_amount:.2f} Tk\n"
                f"Less: {final_less:.2f} Tk\n"
                f"Net Amount: {net_amount:.2f} Tk\n"
                f"Paid: {payment_used:.2f} Tk\n"
                f"New Due: {new_due:.2f} Tk\n"
                f"New Advance: {new_advance:.2f} Tk\n"
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
            print("SMS API response:", response.text)
            
        except Exception as sms_error:
            print("SMS sending error:", sms_error)

        return JsonResponse({'status': 'success', 'message': 'Sale data saved and SMS sent.'}, status=200)
    else:
        return JsonResponse({'error': 'POST request required.'}, status=400)
