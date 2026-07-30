"""Catalogue views: api."""

from ..common import *

@csrf_exempt
def api_products(request):
    """
    API endpoint to get all products with stock information
    """
    if request.method == 'GET':
        products = Product.objects.all()
        products_data = []
        for product in products:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'code': product.code,
                'price': float(product.rate),
                'stock': float(product.total_stock),
                'size': product.size,
                'image': product.image if product.image else None
            })
        return JsonResponse(products_data, safe=False)
    return JsonResponse({'error': 'GET request required.'}, status=400)

@csrf_exempt
def api_product_detail(request, product_id):
    """
    API endpoint to get a single product's details
    """
    if request.method == 'GET':
        try:
            product = Product.objects.get(id=product_id)
            return JsonResponse({
                'id': product.id,
                'name': product.name,
                'code': product.code,
                'price': float(product.rate),
                'stock': float(product.total_stock),
                'size': product.size,
                'image': product.image if product.image else None
            })
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found.'}, status=404)
    return JsonResponse({'error': 'GET request required.'}, status=400)
