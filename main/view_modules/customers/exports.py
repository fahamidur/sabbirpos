"""Customers views: exports."""

from ..common import *

@csrf_exempt
def export_customers_excel(request):
    """Export all customer data to Excel file"""
    try:
        # Fetch all customers
        customers = Customer.objects.all()
        
        # Fetch all sales for calculating totals
        sales_data = Sale.objects.all()
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        # Calculate total and current month purchases for each customer
        customer_totals = {}
        for sale in sales_data:
            customer_obj = sale.customer
            sale_date = sale.date
            total_price = float(sale.total_price or 0)
            
            if customer_obj:
                customer_name = customer_obj.name
                if customer_name not in customer_totals:
                    customer_totals[customer_name] = {'total_buy': 0, 'current_month_buy': 0}
                
                customer_totals[customer_name]['total_buy'] += total_price
                
                if sale_date.year == current_year and sale_date.month == current_month:
                    customer_totals[customer_name]['current_month_buy'] += total_price
        
        # Prepare data for Excel (use calculated due/advance)
        excel_data = []
        for customer in customers:
            customer_name = customer.name
            calc_due, calc_adv = get_customer_calculated_due_advance(customer)
            excel_data.append({
                'Name': customer.name,
                'Code': customer.code,
                'Area': customer.area,
                'Phone': customer.phone,
                'NID': customer.nid,
                'Due': float(calc_due),
                'Advance': float(calc_adv),
                'Paid': float(customer.Paid or 0),
                'Total Buy': customer_totals.get(customer_name, {}).get('total_buy', 0),
                'Current Month Buy': customer_totals.get(customer_name, {}).get('current_month_buy', 0),
            })
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Customers')
        
        # Prepare response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="customers_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        
        return response
    except Exception as e:
        messages.error(request, f'Error exporting customers: {str(e)}')
        return redirect('customer_list')
