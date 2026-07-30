"""Dashboard views."""

from .common import *

def homepage(request):
    """
    View to render the ecommerce homepage (homepage.html)
    This is a public-facing page that displays products
    """
    products = Product.objects.all().order_by('id')  # Get all products
    return render(request, 'homepage.html', {'products': products})


def dashboard(request):
    # Default to the current date if no filter is applied
    selected_date = datetime.now()
    selected_month = selected_date.month
    selected_year = selected_date.year

    if request.method == "POST":
        # Get the selected month and year from the form
        selected_month = int(request.POST.get("month", selected_month))
        selected_year = int(request.POST.get("year", selected_year))

    # Calculate the previous month and year
    if selected_month == 1:
        previous_month = 12
        previous_year = selected_year - 1
    else:
        previous_month = selected_month - 1
        previous_year = selected_year

    # Initialize aggregates for sales
    total_sale_all = 0
    total_commission_all = 0
    total_discount_all = 0
    total_sales_due = 0
    total_payment_received = 0
    total_advance_used = 0

    current_month_sale = 0
    current_month_commission = 0
    current_month_discount = 0
    current_month_sales_due = 0
    current_month_payment_received = 0
    current_month_advance_used = 0

    previous_month_sale = 0
    previous_month_commission = 0
    previous_month_discount = 0
    previous_month_sales_due = 0
    previous_month_payment_received = 0
    previous_month_advance_used = 0

    # Initialize aggregates for adai
    total_due_adai = 0
    total_advance_adai = 0

    current_month_due_adai = 0
    current_month_advance_adai = 0

    previous_month_due_adai = 0
    previous_month_advance_adai = 0

    # Track customers per period (from sales + adai) for due formula
    all_customer_ids = set()
    current_month_customer_ids = set()
    previous_month_customer_ids = set()

    # Process sales data from Sale model
    sales_data = Sale.objects.all()
    for sale in sales_data:
        sale_total = float(sale.total_price or 0)
        sale_commission = float(sale.discount or 0)
        sale_discount = float(sale.less or 0)
        sale_due = float(sale.due or 0)
        sale_payment_received = float(sale.payment_received or 0)
        sale_advance_used = float(sale.advance_used or 0)
        sale_date = sale.date

        total_sale_all += sale_total
        total_commission_all += sale_commission
        total_discount_all += sale_discount
        total_sales_due += sale_due
        total_payment_received += sale_payment_received
        total_advance_used += sale_advance_used
        if sale.customer_id:
            all_customer_ids.add(sale.customer_id)
        if sale_date:
            # Current month data
            if sale_date.year == selected_year and sale_date.month == selected_month:
                current_month_sale += sale_total
                current_month_commission += sale_commission
                current_month_discount += sale_discount
                current_month_sales_due += sale_due
                current_month_payment_received += sale_payment_received
                current_month_advance_used += sale_advance_used
                if sale.customer_id:
                    current_month_customer_ids.add(sale.customer_id)

            # Previous month data
            if sale_date.year == previous_year and sale_date.month == previous_month:
                previous_month_sale += sale_total
                previous_month_commission += sale_commission
                previous_month_discount += sale_discount
                previous_month_sales_due += sale_due
                previous_month_payment_received += sale_payment_received
                previous_month_advance_used += sale_advance_used
                if sale.customer_id:
                    previous_month_customer_ids.add(sale.customer_id)

    # Process adai data from Adai model
    adai_data = Adai.objects.all()
    for adai in adai_data:
        adai_due = float(adai.due or 0)
        adai_advance = float(adai.advance or 0)
        adai_date = adai.date

        total_due_adai += adai_due
        total_advance_adai += adai_advance
        if adai.customer_id:
            all_customer_ids.add(adai.customer_id)

        if adai_date:
            # Current month data
            if adai_date.year == selected_year and adai_date.month == selected_month:
                current_month_due_adai += adai_due
                current_month_advance_adai += adai_advance
                if adai.customer_id:
                    current_month_customer_ids.add(adai.customer_id)

            # Previous month data
            if adai_date.year == previous_year and adai_date.month == previous_month:
                previous_month_due_adai += adai_due
                previous_month_advance_adai += adai_advance
                if adai.customer_id:
                    previous_month_customer_ids.add(adai.customer_id)

    # Customer initial due/advance sums for each period's involved customers
    all_customers = Customer.objects.filter(id__in=all_customer_ids) if all_customer_ids else Customer.objects.none()
    current_month_customers = Customer.objects.filter(id__in=current_month_customer_ids) if current_month_customer_ids else Customer.objects.none()
    previous_month_customers = Customer.objects.filter(id__in=previous_month_customer_ids) if previous_month_customer_ids else Customer.objects.none()

    total_customer_initial_due = sum(float(c.due or 0) for c in all_customers)
    total_customer_advance = sum(float(c.Advance or 0) for c in all_customers)
    current_month_customer_initial_due = sum(float(c.due or 0) for c in current_month_customers)
    current_month_customer_advance = sum(float(c.Advance or 0) for c in current_month_customers)
    previous_month_customer_initial_due = sum(float(c.due or 0) for c in previous_month_customers)
    previous_month_customer_advance = sum(float(c.Advance or 0) for c in previous_month_customers)

    # Due formula for all-time/current/previous:
    # (sales_due + customer_initial_due) - (customer_advance + adai_due + adai_advance - advance_used)
    total_due = (total_sales_due + total_customer_initial_due) - (
        total_customer_advance + total_due_adai + total_advance_adai - total_advance_used
    )
    current_month_due = (current_month_sales_due + current_month_customer_initial_due) - (
        current_month_customer_advance + current_month_due_adai + current_month_advance_adai - current_month_advance_used
    )
    previous_month_due = (previous_month_sales_due + previous_month_customer_initial_due) - (
        previous_month_customer_advance + previous_month_due_adai + previous_month_advance_adai - previous_month_advance_used
    )

    # If negative, show 0
    total_due = max(0.0, float(total_due or 0))
    current_month_due = max(0.0, float(current_month_due or 0))
    previous_month_due = max(0.0, float(previous_month_due or 0))

    # Calculate total opening advance (for advance section cards)
    from django.db.models import Sum
    total_opening_advance = Customer.objects.aggregate(t=Sum('Advance'))['t'] or 0
    # অগ্রিম জমা মোট: গ্রাহকের ইনিশিয়াল অগ্রিম + সব Adai.advance (Adjust Sales)
    advance_adai_all_time = float(total_opening_advance or 0) + float(total_advance_adai or 0)
    # অগ্রিম ব্যবহৃত হলে (Sale.advance_used) অগ্রিম জমা থেকে কাটতে হবে
    advance_adai_all_time_after_used = max(0.0, float(advance_adai_all_time or 0) - float(total_advance_used or 0))
    # current_month_due can be negative (no max constraint)
    # Remove previous_month_due from context if present

    # Prepare context for the template
    context = {
        "selected_month": selected_month,
        "selected_year": selected_year,
        "months": [{"number": i, "name": calendar.month_name[i]} for i in range(1, 13)],
        "years": range(2020, 2031),
        "total_sales": {
            "previous_month": previous_month_sale,
            "current_month": current_month_sale,
            "all_time": total_sale_all,
        },
        "total_commission": {
            "previous_month": previous_month_commission,
            "current_month": current_month_commission,
            "all_time": total_commission_all,
        },
        "after_discount": {
            "previous_month": previous_month_sale - previous_month_commission-previous_month_discount,
            "current_month": current_month_sale - current_month_commission-current_month_discount,
            "all_time": total_sale_all - total_commission_all-total_discount_all,
        },
        "less": {
            "previous_month": previous_month_discount,
            "current_month": current_month_discount,
            "all_time": total_discount_all,
        },
        "due": {
            "previous_month": previous_month_due,
            "current_month": current_month_due,
            "all_time": total_due,
        },
        "payment_received": {
            "previous_month": previous_month_payment_received,
            "current_month": current_month_payment_received,
            "all_time": total_payment_received,
        },
        "due_adai": {
            "previous_month": previous_month_due_adai,
            "current_month": current_month_due_adai,
            "all_time": total_due_adai,
        },
        "advance_adai": {
            "previous_month": max(0.0, float(previous_month_advance_adai or 0) - float(previous_month_advance_used or 0)),
            "current_month": max(0.0, float(current_month_advance_adai or 0) - float(current_month_advance_used or 0)),
            "all_time": advance_adai_all_time_after_used,
        },
        "mot_adai": {
            "previous_month": previous_month_advance_adai+previous_month_due_adai+previous_month_payment_received,
            "current_month": current_month_advance_adai+current_month_due_adai+current_month_payment_received,
            # চলতি মাসের মতো: আদায়ে অগ্রিম+বাকি আদায় + বিক্রিতে পেমেন্ট (Customer.Advance বাদ)
            "all_time": float(total_advance_adai or 0) + float(total_due_adai or 0) + float(total_payment_received or 0),
        },
    }

    return render(request, "Report.html", context)


