"""Finance views: expenses."""

from ..common import *

@csrf_exempt
def expence_list(request):
    if request.method == 'POST':
        # Create a new supplier with initial due or advance
        date = request.POST.get('transactionDate')
        suplier = request.POST.get('suplier')
        debit = float(request.POST.get('debit') or 0)  # Due
        credit = float(request.POST.get('credit') or 0) # Advance
        # Only create if supplier does not exist
        if suplier and not Expence.objects.filter(suplier=suplier).exists():
            from datetime import datetime
            Expence.objects.create(
                date=date if date else datetime.now().date(),
                narration="Initial Balance",
                due=debit,
                advance=credit,
                total_pay=0,
                suplier=suplier
            )
        return redirect('expence_list')

    # Fetch all unique suppliers and calculate their running balances
    suppliers = Expence.objects.values_list('suplier', flat=True).distinct()
    expence_list_data = []
    
    for supplier in suppliers:
        if not supplier:
            continue
            
        # Get all expenses for this supplier
        expenses = Expence.objects.filter(suplier=supplier)
        
        # Calculate sum of all advance and due
        total_advance = sum(e.advance for e in expenses)
        total_due = sum(e.due for e in expenses)
        
        # Net balance = Advance - Due
        net_balance = total_advance - total_due
        
        if net_balance > 0:
            current_advance = net_balance
            current_due = 0
        else:
            current_advance = 0
            current_due = abs(net_balance)
            
        expence_list_data.append({
            'suplier': supplier,
            'advance': current_advance,
            'due': current_due,
        })
        
    return render(request, 'expence_list.html', {'expence_list': expence_list_data})

@csrf_exempt
def delete_expence(request, transaction_id):
    if request.method == 'POST':
        try:
            expence = Expence.objects.get(id=transaction_id)
            expence.delete()
        except Expence.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('expence_list')

@csrf_exempt
def add_expence(request):
    """
    - GET: Show form with unique supplier list.
    - POST (JSON): Add due/advance for selected supplier (must exist).
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            suplier = data.get('suplier')
            date = data.get('date')
            narration = data.get('narration', '')
            amount = float(data.get('amount', 0))
            money_type = int(data.get('money_type', 0))

            if not suplier or not date or not amount or not money_type:
                return JsonResponse({'status': 'error', 'error': 'Missing required fields'})

            # Only allow if supplier exists
            if not Expence.objects.filter(suplier=suplier).exists():
                return JsonResponse({'status': 'error', 'error': 'Supplier does not exist. Please create in Expense List.'})

            due = amount if money_type == 1 else 0
            advance = amount if money_type == 2 else 0

            Expence.objects.create(
                suplier=suplier,
                date=date,
                narration=narration,
                due=due,
                advance=advance,
                total_pay=0
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    # GET: Show unique supplier list for dropdown
    suplier_list = Expence.objects.values_list('suplier', flat=True).distinct()
    expence_list = Expence.objects.all().order_by('-date')
    return render(request, 'add_expence.html', {
        'expence_list': expence_list,
        'suplier_list': suplier_list,
    })

@csrf_exempt
def update_expence(request, expence_id):
    """
    Update an expense record by ID (for editing from modal).
    Accepts JSON with any of: suplier, narration, due, advance, total_pay, date.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            expence = Expence.objects.get(id=expence_id)
            # Update only provided fields
            if 'due' in data and data['due'] is not None:
                expence.due = float(data['due'])
            if 'advance' in data and data['advance'] is not None:
                expence.advance = float(data['advance'])
            if 'total_pay' in data and data['total_pay'] is not None:
                expence.total_pay = float(data['total_pay'])
            if 'narration' in data and data['narration'] is not None:
                expence.narration = data['narration']
            if 'suplier' in data and data['suplier'] is not None:
                expence.suplier = data['suplier']
            if 'date' in data and data['date'] is not None:
                expence.date = data['date']
            expence.save()
            return JsonResponse({'status': 'success', 'message': 'Expense updated successfully.'})
        except Expence.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Expense record not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})
