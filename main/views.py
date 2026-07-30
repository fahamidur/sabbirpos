"""Compatibility facade for the refactored view modules.

Existing imports from main.views continue to work.
"""

from .view_modules.authentication import login_view, request_password_reset_code, reset_admin_credentials, logout_view, salesman_login, salesman_logout
from .view_modules.dashboard import homepage, dashboard
from .view_modules.catalogue import product_detail, product_list, delete_product, upload_products, product_report, update_product, api_products, api_product_detail
from .view_modules.customers import customer_list, upload_customers, export_customers_excel, delete_customer, filter_customer_sales, customer_ledger, update_customer
from .view_modules.salesmen import salesman_list, delete_salesman, download_salesman_report, export_salesman_report_excel, export_salesman_payment_excel, salesman_pos, update_salesman
from .view_modules.sales import pos_dashboard, save_sale, all_sales, all_orders, export_all_sales_excel, delete_sale, download_cash_memo, salesaddjust, update_sales, save_pending_sale, pending_sales, approve_sale, reject_sale
from .view_modules.inventory import stockaddjust, update_stock
from .view_modules.collections import export_adai_excel, delete_adai, update_adai, update_adai, filter_adai
from .view_modules.finance import transaction_list, delete_transaction, salesmanpayment, delete_salesmanpayment, salespayjust, salesman_pay, expence_list, delete_supplier, update_supplier, delete_expence, add_expence, update_expence, supplier_ledger, update_transaction
from .view_modules.reports import filter_sales, profit_report
from .view_modules.marketing import marketing_cost, marketing_cost_list, delete_marketing_cost
from .view_modules.ecommerce import cart, checkout, place_order

__all__ = [name for name in globals() if not name.startswith("_")]
