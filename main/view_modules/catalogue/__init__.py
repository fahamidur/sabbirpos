"""Public exports for the catalogue view package."""

from .management import product_list, delete_product, upload_products, update_product
from .details import product_detail
from .reports import product_report
from .api import api_products, api_product_detail

__all__ = [name for name in globals() if not name.startswith("_")]
