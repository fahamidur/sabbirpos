"""Invoice-based profit report calculations.

The current sales structure stores product lines in ``Sale.products``.
This service keeps all money calculations out of the view and returns one
summary row per invoice, with proportionately allocated product details.
"""

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db.models import Sum

from main.models import MarketingCost, Product, Sale


MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    """Convert an existing float, string or null value to a money Decimal."""
    try:
        return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def quantity_value(value):
    """Convert quantity values without forcing two decimal places."""
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _filtered_sales(start_date=None, end_date=None):
    sales = (
        Sale.objects
        .select_related("customer", "salesman")
        .all()
        .order_by("-date", "-time", "-id")
    )

    if start_date:
        sales = sales.filter(date__gte=start_date)
    if end_date:
        sales = sales.filter(date__lte=end_date)

    return sales


def _marketing_cost_map(invoice_numbers):
    """Return all marketing costs in one query, grouped by invoice number."""
    result = defaultdict(lambda: ZERO)

    if not invoice_numbers:
        return result

    rows = (
        MarketingCost.objects
        .filter(invoice_number__in=invoice_numbers)
        .values("invoice_number")
        .annotate(total=Sum("amount"))
    )

    for row in rows:
        result[row["invoice_number"]] = money(row["total"])

    return result


def _product_map(sales):
    """Load all products referenced by the selected invoices in one query."""
    product_ids = set()

    for sale in sales:
        for item in sale.products or []:
            product_id = item.get("id")
            if product_id is not None:
                try:
                    product_ids.add(int(product_id))
                except (TypeError, ValueError):
                    continue

    return Product.objects.in_bulk(product_ids)


def _line_discount(item, quantity):
    """Read the saved line discount, with support for older sale records."""
    if item.get("less") not in (None, ""):
        return max(ZERO, money(item.get("less")))

    return max(ZERO, money(item.get("lessPerUnit")) * quantity)


def _build_product_line(item, product):
    quantity = max(Decimal("0"), quantity_value(item.get("quantity")))
    mrp_per_unit = max(ZERO, money(item.get("price")))
    gross_mrp = (mrp_per_unit * quantity).quantize(MONEY, rounding=ROUND_HALF_UP)

    product_discount = min(gross_mrp, _line_discount(item, quantity))
    discount_per_unit = (
        (product_discount / quantity).quantize(MONEY, rounding=ROUND_HALF_UP)
        if quantity > 0 else ZERO
    )
    selling_after_product_discount = max(ZERO, gross_mrp - product_discount)

    # Newer records may carry a historical cost. Older records use the
    # current Product.production_cost because the existing schema does not
    # save production cost on each sale line.
    saved_cost = item.get("production_cost")
    if saved_cost in (None, ""):
        cost_per_unit = money(product.production_cost) if product else ZERO
        costing_source = "Current product cost" if product else "Cost unavailable"
    else:
        cost_per_unit = max(ZERO, money(saved_cost))
        costing_source = "Saved sale cost"

    total_cost = (cost_per_unit * quantity).quantize(MONEY, rounding=ROUND_HALF_UP)

    product_name = (
        item.get("product")
        or item.get("name")
        or item.get("product_name")
        or (product.name if product else "Deleted product")
    )

    return {
        "product_name": product_name,
        "quantity": quantity,
        "mrp_per_unit": mrp_per_unit,
        "gross_mrp": gross_mrp,
        "discount_per_unit": discount_per_unit,
        "product_discount": product_discount,
        "selling_after_product_discount": selling_after_product_discount,
        "cost_per_unit": cost_per_unit,
        "total_cost": total_cost,
        "costing_source": costing_source,
        "allocated_percentage_discount": ZERO,
        "allocated_fixed_discount": ZERO,
        "allocated_bulk_discount": ZERO,
        "final_selling_price": ZERO,
        "allocated_commission": ZERO,
        "allocated_marketing_cost": ZERO,
        "profit": ZERO,
    }


def _allocate_invoice_values(lines, percentage_discount, fixed_discount,
                             commission, marketing_cost):
    """Allocate invoice-wide values across products and reconcile rounding."""
    if not lines:
        return

    subtotal = sum(
        (line["selling_after_product_discount"] for line in lines),
        ZERO,
    )

    values = {
        "allocated_percentage_discount": percentage_discount,
        "allocated_fixed_discount": fixed_discount,
        "allocated_commission": commission,
        "allocated_marketing_cost": marketing_cost,
    }

    running = {key: ZERO for key in values}

    for index, line in enumerate(lines):
        is_last = index == len(lines) - 1
        base = line["selling_after_product_discount"]
        share = (base / subtotal) if subtotal > 0 else (Decimal("1") / len(lines))

        for field, total in values.items():
            if is_last:
                allocated = total - running[field]
            else:
                allocated = (total * share).quantize(MONEY, rounding=ROUND_HALF_UP)
                running[field] += allocated
            line[field] = max(ZERO, allocated)

        line["allocated_bulk_discount"] = (
            line["allocated_percentage_discount"]
            + line["allocated_fixed_discount"]
        )
        line["final_selling_price"] = max(
            ZERO,
            line["selling_after_product_discount"]
            - line["allocated_bulk_discount"],
        )
        line["profit"] = (
            line["final_selling_price"]
            - line["total_cost"]
            - line["allocated_commission"]
            - line["allocated_marketing_cost"]
        ).quantize(MONEY, rounding=ROUND_HALF_UP)


def _invoice_row(sale, product_map, marketing_cost):
    lines = []

    for item in sale.products or []:
        product_id = item.get("id")
        try:
            product = product_map.get(int(product_id)) if product_id is not None else None
        except (TypeError, ValueError):
            product = None
        lines.append(_build_product_line(item, product))

    gross_mrp = sum((line["gross_mrp"] for line in lines), ZERO)
    product_discount = sum((line["product_discount"] for line in lines), ZERO)
    subtotal_after_product_discount = sum(
        (line["selling_after_product_discount"] for line in lines), ZERO
    )

    # Sale.discount already stores the calculated monetary discount amount.
    percentage_discount = max(ZERO, money(sale.discount))
    fixed_discount = max(ZERO, money(getattr(sale, "less_input", 0)))

    # Discounts cannot reduce an invoice below zero. Percentage discount is
    # applied first, followed by the fixed invoice discount.
    percentage_discount = min(subtotal_after_product_discount, percentage_discount)
    remaining_after_percentage = max(
        ZERO, subtotal_after_product_discount - percentage_discount
    )
    fixed_discount = min(remaining_after_percentage, fixed_discount)
    bulk_discount = percentage_discount + fixed_discount

    net_selling_price = max(
        ZERO, subtotal_after_product_discount - bulk_discount
    )
    total_cost = sum((line["total_cost"] for line in lines), ZERO)
    commission = max(ZERO, money(sale.comission))

    _allocate_invoice_values(
        lines,
        percentage_discount,
        fixed_discount,
        commission,
        marketing_cost,
    )

    profit = (
        net_selling_price - total_cost - commission - marketing_cost
    ).quantize(MONEY, rounding=ROUND_HALF_UP)

    # Reconcile the final product profit to the authoritative invoice profit.
    if lines:
        product_profit_total = sum((line["profit"] for line in lines), ZERO)
        difference = profit - product_profit_total
        lines[-1]["profit"] = (lines[-1]["profit"] + difference).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )

    discount_percent = (
        (percentage_discount / subtotal_after_product_discount * Decimal("100"))
        .quantize(MONEY, rounding=ROUND_HALF_UP)
        if subtotal_after_product_discount > 0 else ZERO
    )

    return {
        "id": sale.id,
        "date": sale.date,
        "invoice_number": sale.invoice_number or "N/A",
        "customer_name": sale.customer.name if sale.customer else "",
        "salesman_name": sale.salesman.name if sale.salesman else "",
        "products": lines,
        "product_count": len(lines),
        "gross_mrp": gross_mrp,
        "product_discount": product_discount,
        "subtotal_after_product_discount": subtotal_after_product_discount,
        "percentage_discount": percentage_discount,
        "discount_percent": discount_percent,
        "fixed_discount": fixed_discount,
        "bulk_discount": bulk_discount,
        "net_selling_price": net_selling_price,
        "total_cost": total_cost,
        "commission": commission,
        "marketing_cost": marketing_cost,
        "profit": profit,
    }


def build_profit_report(start_date=None, end_date=None):
    """Build invoice rows and report totals for the selected date range."""
    sales = list(_filtered_sales(start_date, end_date))
    invoice_numbers = [
        sale.invoice_number for sale in sales if sale.invoice_number
    ]
    marketing_costs = _marketing_cost_map(invoice_numbers)
    products = _product_map(sales)

    invoices = [
        _invoice_row(
            sale,
            products,
            marketing_costs[sale.invoice_number] if sale.invoice_number else ZERO,
        )
        for sale in sales
    ]

    totals = {
        "gross_mrp": sum((row["gross_mrp"] for row in invoices), ZERO),
        "product_discount": sum(
            (row["product_discount"] for row in invoices), ZERO
        ),
        "bulk_discount": sum((row["bulk_discount"] for row in invoices), ZERO),
        "net_selling_price": sum(
            (row["net_selling_price"] for row in invoices), ZERO
        ),
        "total_cost": sum((row["total_cost"] for row in invoices), ZERO),
        "commission": sum((row["commission"] for row in invoices), ZERO),
        "marketing_cost": sum(
            (row["marketing_cost"] for row in invoices), ZERO
        ),
        "profit": sum((row["profit"] for row in invoices), ZERO),
    }

    return {"invoices": invoices, "totals": totals}
