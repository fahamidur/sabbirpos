"""Sales views: exports."""

from ..common import *
from ..catalogue import product_list

@csrf_exempt
def export_all_sales_excel(request):
    """Export all sales data to Excel file with filters"""
    try:
        # Get filter parameters (same as all_sales view)
        selected_month = request.GET.get('month')
        selected_year = request.GET.get('year')
        selected_salesman = request.GET.get('salesman')
        
        # Start with base query
        sales_query = Sale.objects.all()
        
        # Apply filters (same logic as all_sales)
        if selected_salesman:
            sales_query = sales_query.filter(salesman_id=selected_salesman)
        if selected_month and selected_year:
            sales_query = sales_query.filter(date__year=int(selected_year), date__month=int(selected_month))
        
        sales = sales_query.order_by('-date', '-time')
        
        # Prepare data for Excel
        excel_data = []
        for sale in sales:
            # Format products as string
            products_str = ""
            if sale.products:
                product_list = []
                for product in sale.products:
                    product_name = product.get('name', '')
                    quantity = product.get('quantity', 0)
                    price = product.get('price', 0)
                    product_list.append(f"{product_name} (Qty: {quantity}, Price: {price})")
                products_str = "; ".join(product_list)
            
            excel_data.append({
                'Invoice Number': sale.invoice_number if sale.invoice_number else 'N/A',
                'Date': sale.date.strftime('%Y-%m-%d') if sale.date else '',
                'Time': sale.time.strftime('%H:%M:%S') if sale.time else '',
                'Salesman': sale.salesman.name if sale.salesman else '',
                'Customer': sale.customer.name if sale.customer else '',
                'Products': products_str,
                'Total Price': float(sale.total_price or 0),
                'Discount': float(sale.discount or 0),
                'Less': float(sale.less or 0),
                'Net Amount': float((sale.total_price or 0) - (sale.discount or 0) - (sale.less or 0)),
                'Payment Received': float(sale.payment_received or 0),
                'Due': float(sale.due or 0),
                'Commission': float(sale.comission or 0),
            })
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='All Sales')
        
        # Prepare response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
        # Generate filename with filters
        filename_parts = ['sales_export']
        if selected_salesman:
            try:
                salesman = Salesman.objects.get(id=selected_salesman)
                filename_parts.append(salesman.name.replace(' ', '_'))
            except:
                pass
        if selected_month and selected_year:
            filename_parts.append(f"{int(selected_year)}_{int(selected_month):02d}")
        filename_parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
        
        response['Content-Disposition'] = f'attachment; filename="{"_".join(filename_parts)}.xlsx"'
        
        return response
    except Exception as e:
        messages.error(request, f'Error exporting sales: {str(e)}')
        return redirect('all_sales')

def download_cash_memo(request, sale_id):
    try:
        # Get sale data from Django ORM
        sale = get_object_or_404(Sale, id=sale_id)
        customer = sale.customer
        salesman = sale.salesman
        

        # Use calculated due; previous_due = current calculated due minus this sale's due
        current_due, current_adv = get_customer_calculated_due_advance(customer)
        previous_due = current_due - (sale.due or 0)
        if previous_due < 0:
            previous_due = 0
        total_due = previous_due + (sale.due or 0)
        print("due bole dao:", total_due)

        # Net sale = same as get_sale_net_amount (total - discount - effective_less)
        net_bill = get_sale_net_amount(sale)
        mot_bill = sale.total_price
        total_less_per_unit = 0
        who_less = 0
        if sale.products:
            for item in sale.products:
                lp = float(item.get('lessPerUnit', 0) or 0)
                qty = float(item.get('quantity', 0) or 0)
                total_less_per_unit += lp * qty
                if lp > 0:
                    who_less += 1
        effective_less = (float(sale.less or 0) - total_less_per_unit) if who_less > 0 else float(sale.less or 0)

        products = sale.products if hasattr(sale, 'products') else []

        context = {
            'sale': sale,
            'mot_bill': mot_bill,
            'salesman': salesman,
            'customer': customer,
            'products': products,
            'net_bill': net_bill,
            'total_due': current_due,
            'previous_due': previous_due,
            'customer_advance': current_adv or 0,
            'less': effective_less,
        }

        html_string = render_to_string('Memo.html', context)
        return HttpResponse(html_string, content_type='text/html')

    except Exception as e:
        return HttpResponse(f"Error generating HTML memo: {str(e)}", status=500)
