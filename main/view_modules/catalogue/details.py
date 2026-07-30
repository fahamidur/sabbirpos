"""Catalogue views: details."""

from ..common import *

def product_detail(request, product_id):
    """
    View to render the product detail page
    """
    try:
        product = Product.objects.get(id=product_id)
        # Get related products (other products in the same category or similar)
        related_products = Product.objects.exclude(id=product_id).order_by('?')[:4]
        return render(request, 'product_detail.html', {
            'product': product,
            'related_products': related_products
        })
    except Product.DoesNotExist:
        return redirect('homepage')
