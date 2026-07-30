"""Inventory views."""

from .common import *

def stockaddjust(request):
    # Retrieve products from the Product model
    products = Product.objects.all()
    products_data = [
        {
            'id': product.id,
            'code': product.code,
            'name': product.name,
            'full_name': f"{product.code} - {product.name} ({product.size})",
            'rate': product.rate,
            'size': product.size,
            'total_stock': product.total_stock,
            # Add other fields as needed
        }
        for product in products
    ]
    context = {
        'products': products_data,
    }
    
    return render(request, 'stockadd.html', context)


@csrf_exempt
def update_stock(request):
    """Handle stock updates for selected product (JSON version) and send SMS on update"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            product_id = data.get('product_id')
            quantity = data.get('quantity')
            

            # Validate inputs
            if not product_id or not quantity:
                return JsonResponse({'status': 'error', 'error': 'Missing required fields'})

            quantity = int(quantity)
            if quantity <= 0:
                return JsonResponse({'status': 'error', 'error': 'Quantity must be positive'})

            # Update stock in the Product model
            try:
                product = Product.objects.get(id=product_id)
                product.total_stock += quantity
                product.save()
            except Product.DoesNotExist:
                return JsonResponse({'status': 'error', 'error': 'Product not found'})

            # --- SMS Sending Section ---
            try:
                # Compose SMS message
                msg = (
                    f"Stock Updated!\n"
                    f"Product: {product.name}\n"
                    f"Added: {quantity}\n"
                    f"Current Stock: {product.total_stock}\n"
                    f"- Rahmaniya Pump"
                )
                # Set your admin/manager phone number here (must be in 8801XXXXXXXXX format)
                admin_phone = "01857333003"  # Change to your admin/manager number
                payload = {
                    'api_key': 'ld96r4ak7OfIQs3f1Ov4jlwvF7HwLVkLyHb7XW7i',
                    'msg': msg,
                    'to': admin_phone
                }
                url = "https://api.sms.net.bd/sendsms"
                response = requests.post(url, data=payload, timeout=10)
               
            except Exception as sms_error:
                print("SMS sending error:", sms_error)

            return JsonResponse({'status': 'success'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})


