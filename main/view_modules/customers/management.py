"""Customers views: management."""

from ..common import *

@csrf_exempt
def customer_list(request):
    if request.method == 'POST':
        # Adding a new customer (initial due/advance from form only)
        name = request.POST.get('name')
        code = request.POST.get('code')
        area = request.POST.get('area')
        phone = request.POST.get('phone')
        nid = request.POST.get('nid')
        initial_due = float(request.POST.get('due', 0) or 0)
        initial_advance = float(request.POST.get('Advance', 0) or 0)
        if name and code and area and phone and nid:
            Customer.objects.create(
                name=name,
                code=code,
                area=area,
                phone=phone,
                nid=nid,
                due=initial_due,
                Advance=initial_advance,
                Paid=0
            )
            return redirect('customer_list')

    # Fetching all customers
    customers = Customer.objects.all()
    sales_data = Sale.objects.all()
    current_month = datetime.now().month
    current_year = datetime.now().year

    # Total buy = sum of net sale per sale (same as download_cash_memo net_bill)
    customer_totals = {}
    for sale in sales_data:
        customer_obj = sale.customer
        sale_date = sale.date
        net_sale = get_sale_net_amount(sale)  # total - discount - effective_less (matches memo)
        if customer_obj:
            customer_name = customer_obj.name
            if customer_name not in customer_totals:
                customer_totals[customer_name] = {'total_buy': 0, 'current_month_buy': 0}
            customer_totals[customer_name]['total_buy'] += net_sale
            if sale_date and sale_date.year == current_year and sale_date.month == current_month:
                customer_totals[customer_name]['current_month_buy'] += net_sale

    customer_list_data = []
    for customer in customers:
        current_due, current_advance = get_customer_calculated_due_advance(customer)
        customer_name = customer.name
        customer_dict = {
            'id': customer.id,
            'name': customer.name,
            'code': customer.code,
            'area': customer.area,
            'phone': customer.phone,
            'nid': customer.nid,
            'due': current_due,
            'Advance': current_advance,
            'initial_due': customer.due,
            'initial_advance': customer.Advance,
            'Paid': customer.Paid,
            'total_buy': customer_totals.get(customer_name, {}).get('total_buy', 0),
            'current_month_buy': customer_totals.get(customer_name, {}).get('current_month_buy', 0),
        }
        customer_dict['json'] = json.dumps(customer_dict)
        customer_list_data.append(customer_dict)

    return render(request, 'Customer.html', {'customer': customer_list_data})

@csrf_exempt
def upload_customers(request):
    """Upload customers from Excel file"""
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            excel_file = request.FILES['excel_file']
            
            # Read Excel file
            df = pd.read_excel(excel_file)
            
            # List of exact column names from the Excel file
            excel_column_names = ['Name', 'Code', 'Area', 'Phone', 'NID', 'Due', 'Advance', 'Paid']
            
            # Check for missing columns in the DataFrame
            missing_excel_columns = [col for col in excel_column_names if col not in df.columns]
            if missing_excel_columns:
                messages.error(request, f'Missing required columns in Excel file: {", ".join(missing_excel_columns)}. Please ensure your Excel has these exact column headers.')
                return redirect('customer_list')
            
            success_count = 0
            error_count = 0
            error_details = []
            
            for index, row in df.iterrows():
                try:
                    # Convert values to appropriate types and handle NaN using Excel column names
                    name = str(row['Name']) if pd.notna(row['Name']) else ''
                    code = str(row['Code']) if pd.notna(row['Code']) else ''
                    area = str(row['Area']) if pd.notna(row['Area']) else ''
                    phone = str(row['Phone']) if pd.notna(row['Phone']) else ''
                    nid = str(row['NID']) if pd.notna(row['NID']) else ''
                    due = float(row['Due']) if pd.notna(row['Due']) else 0.0
                    advance = float(row['Advance']) if pd.notna(row['Advance']) else 0.0
                    paid = float(row['Paid']) if pd.notna(row['Paid']) else 0.0
                    
                    # Validate required fields
                    if not name or not code or not area or not phone or not nid:
                        raise ValueError("Name, Code, Area, Phone, and NID are required fields for each customer.")
                    
                    customer, created = Customer.objects.update_or_create(
                        code=code,
                        defaults={
                            'name': name,
                            'area': area,
                            'phone': phone,
                            'nid': nid,
                            'due': due,
                            'Advance': advance,
                            'Paid': paid
                        }
                    )
                    
                    success_count += 1
                    
                except Exception as e:
                    error_count += 1
                    error_msg = f"Row {index + 2}: {str(e)}"
                    error_details.append(error_msg)
                    print(f"Error processing row {index + 2}: {str(e)}")
            
            if success_count > 0:
                messages.success(request, f'Successfully uploaded {success_count} customers')
            if error_count > 0:
                messages.warning(request, f'Failed to upload {error_count} customers')
                for error in error_details[:5]:  # Show first 5 errors
                    messages.error(request, error)
                if len(error_details) > 5:
                    messages.error(request, f"... and {len(error_details) - 5} more errors")
            
            return redirect('customer_list')
            
        except Exception as e:
            error_msg = f'Error processing file: {str(e)}'
            print(error_msg)  # Print to console for debugging
            messages.error(request, error_msg)
            return redirect('customer_list')
    
    # If GET request, redirect to customer list (upload will be done via modal)
    return redirect('customer_list')

@csrf_exempt
def delete_customer(request, customer_id):
    if request.method == 'POST':
        try:
            customer = Customer.objects.get(id=customer_id)
            customer.delete()
        except Customer.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('customer_list')

@csrf_exempt
@require_POST
def update_customer(request, customer_id):
    import json
    from django.http import JsonResponse, HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'], 'This endpoint only accepts POST requests.')
    try:
        data = json.loads(request.body)
        customer = Customer.objects.get(id=customer_id)
        # Update all editable fields
        customer.name = data.get('name', customer.name)
        customer.code = data.get('code', customer.code)
        customer.area = data.get('area', customer.area)
        customer.phone = data.get('phone', customer.phone)
        customer.nid = data.get('nid', customer.nid)
        # Numeric fields
        try:
            customer.due = float(data.get('due', customer.due))
        except (TypeError, ValueError):
            pass
        try:
            customer.Advance = float(data.get('Advance', customer.Advance))
        except (TypeError, ValueError):
            pass
        try:
            customer.Paid = float(data.get('Paid', customer.Paid))
        except (TypeError, ValueError):
            pass
        customer.save()
        current_due, current_advance = get_customer_calculated_due_advance(customer)
        return JsonResponse({
            'status': 'success',
            'due': current_due,
            'Advance': current_advance,
            'Paid': customer.Paid,
        })
    except Customer.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Customer not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
