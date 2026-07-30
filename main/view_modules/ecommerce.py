"""Ecommerce views."""

from .common import *

def cart(request):
    """
    View to render the shopping cart page
    """
    return render(request, 'cart.html')


def checkout(request):
    """
    View to render the checkout page
    """
    return render(request, 'checkout.html')


@csrf_exempt
def place_order(request):
    """
    View to process and save the order
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Extract order data
            customer_name = data.get('customer_name', '')
            customer_email = data.get('customer_email', '')
            customer_phone = data.get('customer_phone', '')
            shipping_address = data.get('shipping_address', '')
            city = data.get('city', '')
            postal_code = data.get('postal_code', '')
            payment_method = data.get('payment_method', 'cash_on_delivery')
            notes = data.get('notes', '')
            products = data.get('products', [])
            subtotal = float(data.get('subtotal', 0))
            shipping_cost = float(data.get('shipping', 0))
            discount = float(data.get('discount', 0))
            
            # Validate required fields
            if not customer_name or not customer_email or not customer_phone:
                return JsonResponse({'status': 'error', 'error': 'Customer information is required.'}, status=400)
            
            if not shipping_address or not city or not postal_code:
                return JsonResponse({'status': 'error', 'error': 'Shipping address is required.'}, status=400)
            
            if not products or len(products) == 0:
                return JsonResponse({'status': 'error', 'error': 'No products in order.'}, status=400)
            
            # Validate product stock
            for product in products:
                product_id = product.get('id')
                quantity = float(product.get('quantity', 0))
                
                if product_id and quantity > 0:
                    try:
                        prod = Product.objects.get(id=product_id)
                        if prod.total_stock < quantity:
                            return JsonResponse({
                                'status': 'error',
                                'error': f'Insufficient stock for {prod.name}. Only {prod.total_stock} units available.'
                            }, status=400)
                    except Product.DoesNotExist:
                        return JsonResponse({
                            'status': 'error',
                            'error': f'Product with ID {product_id} not found.'
                        }, status=404)
            
            # Generate order number
            from datetime import datetime
            order_number = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{datetime.now().microsecond}"
            
            # Calculate total
            total_price = subtotal + shipping_cost - discount
            
            # Create order
            from main.models import Order
            order = Order.objects.create(
                order_number=order_number,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                shipping_address=shipping_address,
                city=city,
                postal_code=postal_code,
                products=products,
                total_price=total_price,
                discount=discount,
                shipping_cost=shipping_cost,
                payment_method=payment_method,
                payment_received=0,  # Will be received on delivery
                status='pending',
                notes=notes
            )
            
            # Update product stock and sales
            for product in products:
                product_id = product.get('id')
                quantity = float(product.get('quantity', 0))
                
                if product_id and quantity > 0:
                    try:
                        prod = Product.objects.get(id=product_id)
                        prod.total_stock -= quantity
                        prod.total_sales += quantity
                        prod.save()
                    except Product.DoesNotExist:
                        continue
            
            return JsonResponse({
                'status': 'success',
                'message': 'Order placed successfully!',
                'order_number': order_number,
                'order_id': order.id
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'error': f'An error occurred: {str(e)}'
            }, status=500)
    
    return JsonResponse({'status': 'error', 'error': 'POST request required.'}, status=400)


