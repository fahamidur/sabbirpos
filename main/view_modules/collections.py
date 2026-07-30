"""Collections views."""

from .common import *
from .customers import customer_list

@csrf_exempt
def export_adai_excel(request):
    """Export all Adai records to Excel file"""
    try:
        # Get all Adai records
        adai_records = Adai.objects.all().order_by('-date')
        
        # Prepare data for Excel
        excel_data = []
        for adai in adai_records:
            excel_data.append({
                'Invoice Number': adai.invoice_number if adai.invoice_number else 'N/A',
                'Date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
                'Salesman': adai.salesman.name if adai.salesman else '',
                'Customer': adai.customer.name if adai.customer else '',
                'Due': float(adai.due or 0),
                'Advance': float(adai.advance or 0),
                'Sales Commission': float(adai.sales_comission or 0),
            })
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Adai Records')
        
        # Prepare response
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="adai_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
        
        return response
    except Exception as e:
        messages.error(request, f'Error exporting Adai records: {str(e)}')
        return redirect('salesaddjust')


@csrf_exempt
def delete_adai(request, adai_id):
    if request.method == 'POST':
        try:
            # Fetch the Adai record to get advance, due, customer, and salesman details
            adai = Adai.objects.get(id=adai_id)
            advance_amount = float(adai.advance or 0)
            due_amount = float(adai.due or 0)
            customer = adai.customer
            salesman = adai.salesman

            # Customer.due/Advance are calculated from sales+adai; do not update them here.
            if salesman:
                salesman.salescomission -= float(adai.sales_comission or 0)
                if salesman.salescomission < 0:
                    salesman.salescomission = 0
                salesman.save()

            adai.delete()
            return redirect('salesaddjust')
        except Adai.DoesNotExist:
            # Always redirect after POST, even if record not found
            return redirect('salesaddjust')
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@csrf_exempt
def update_adai(request, adai_id):
    if request.method == 'POST':
        try:
            # Parse the updated data from the request
            data = json.loads(request.body)
            new_due = data.get('due')  # Keep as None if not provided
            new_advance = data.get('advance')  # Keep as None if not provided

            # Ensure `due` and `advance` are numbers
            new_due = float(new_due) if new_due is not None else None
            new_advance = float(new_advance) if new_advance is not None else None

            # Fetch the existing adai record
            adai = Adai.objects.get(id=adai_id)
            old_due = float(adai.due or 0)
            old_advance = float(adai.advance or 0)
            customer = adai.customer
            salesman = adai.salesman

            if not customer or not salesman:
                return JsonResponse({'status': 'error', 'message': 'Customer or Salesman not found.'})

            due_difference = (new_due - old_due) if new_due is not None else 0
            advance_difference = (new_advance - old_advance) if new_advance is not None else 0

            if due_difference > 0:
                current_due, _ = get_customer_calculated_due_advance(customer)
                if current_due < due_difference:
                    return JsonResponse({'status': 'error', 'message': 'Customer due cannot be negative.'})

            # Customer.due/Advance are initial-only; do not update here.

            commission_rate = float(salesman.comission or 0)
            commission_difference_due = (commission_rate / 100) * due_difference
            commission_difference_advance = (commission_rate / 100) * advance_difference
            total_commission_difference = commission_difference_due + commission_difference_advance
            if total_commission_difference != 0:
                salesman.salescomission += total_commission_difference
                salesman.save()

            # Update the adai record with the new values (only update provided fields)
            if new_due is not None:
                adai.due = new_due
            if new_advance is not None:
                adai.advance = new_advance

            # Update the sales_comission in the adai record
            adai.sales_comission = float(adai.sales_comission or 0) + total_commission_difference
            adai.save()

            return JsonResponse({'status': 'success', 'message': 'Adai, customer, and salesman data updated successfully.'})
        except Adai.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Adai record not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@csrf_exempt
def update_adai(request, adai_id):
    if request.method == 'POST':
        try:
            # Parse the updated data from the request
            data = json.loads(request.body)
            new_due = data.get('due')  # Keep as None if not provided
            new_advance = data.get('advance')  # Keep as None if not provided

            # Ensure `due` and `advance` are numbers
            new_due = float(new_due) if new_due is not None else None
            new_advance = float(new_advance) if new_advance is not None else None

            # Fetch the existing adai record
            adai = Adai.objects.get(id=adai_id)
            old_due = float(adai.due or 0)
            old_advance = float(adai.advance or 0)
            customer = adai.customer
            salesman = adai.salesman

            if not customer or not salesman:
                return JsonResponse({'status': 'error', 'message': 'Customer or Salesman not found.'})

            due_difference = (new_due - old_due) if new_due is not None else 0
            advance_difference = (new_advance - old_advance) if new_advance is not None else 0

            if due_difference > 0:
                current_due, _ = get_customer_calculated_due_advance(customer)
                if current_due < due_difference:
                    return JsonResponse({'status': 'error', 'message': 'Customer due cannot be negative.'})

            # Customer.due/Advance are initial-only; do not update here.

            commission_rate = float(salesman.comission or 0)
            commission_difference_due = (commission_rate / 100) * due_difference
            commission_difference_advance = (commission_rate / 100) * advance_difference
            total_commission_difference = commission_difference_due + commission_difference_advance
            if total_commission_difference != 0:
                salesman.salescomission += total_commission_difference
                salesman.save()

            # Update the adai record with the new values (only update provided fields)
            if new_due is not None:
                adai.due = new_due
            if new_advance is not None:
                adai.advance = new_advance

            # Update the sales_comission in the adai record
            adai.sales_comission = float(adai.sales_comission or 0) + total_commission_difference
            adai.save()

            return JsonResponse({'status': 'success', 'message': 'Adai, customer, and salesman data updated successfully.'})
        except Adai.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Adai record not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@csrf_exempt
def filter_adai(request):
    if request.method == 'POST':
        # Get the selected customer, month, and year from the form
        customer_id = request.POST.get('customer')
        selected_month = int(request.POST.get('month'))
        selected_year = int(request.POST.get('year'))

        # Fetch the customer details
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Customer not found.'})

        # Fetch adai records for the selected customer and date
        adai_records = Adai.objects.filter(
            customer=customer,
            date__year=selected_year,
            date__month=selected_month
        )
        filtered_adai = [
            {
                'date': adai.date.strftime('%Y-%m-%d') if adai.date else '',
                'salesman': adai.salesman.name if adai.salesman else '',
                'due': adai.due,
                'advance': adai.advance,
                'sales_comission': adai.sales_comission,
            }
            for adai in adai_records
        ]

        return render(request, 'adai_filter.html', {
            'customer_name': customer.name,
            'filtered_adai': filtered_adai,
            'selected_month': selected_month,
            'selected_year': selected_year,
            'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
            'years': range(2020, 2031),
        })

    # Default view (GET request)
    customers = Customer.objects.all()
    customer_list = [{'id': c.id, 'name': c.name} for c in customers]
    return render(request, 'adai_filter.html', {
        'customers': customer_list,
        'months': [{'number': i, 'name': calendar.month_name[i]} for i in range(1, 13)],
        'years': range(2020, 2031),
    })


