"""Finance views: suppliers."""

from ..common import *

@csrf_exempt
def delete_supplier(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            supplier_name = data.get('name')
            if not supplier_name:
                return JsonResponse({'status': 'error', 'error': 'Supplier name is required'})
            # Delete all expenses associated with this supplier name
            Expence.objects.filter(suplier=supplier_name).delete()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})

@csrf_exempt
def update_supplier(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            supplier_name = data.get('original_name')  # name from request body, not URL (avoids slash/encoding issues)
            new_name = data.get('name')
            new_due = float(data.get('due', 0))
            new_advance = float(data.get('advance', 0))

            if not supplier_name:
                return JsonResponse({'status': 'error', 'error': 'Original supplier name is required'})
            if not new_name:
                return JsonResponse({'status': 'error', 'error': 'Supplier name is required'})

            # If name changed, update all existing records
            if new_name != supplier_name:
                Expence.objects.filter(suplier=supplier_name).update(suplier=new_name)
                # Use the new name for the rest of the operations
                supplier_name = new_name

            # Calculate current aggregate due and advance
            expenses = Expence.objects.filter(suplier=supplier_name)
            total_advance_current = sum(e.advance for e in expenses)
            total_due_current = sum(e.due for e in expenses)
            
            # Net balance logic: 
            # If net > 0, it means we have overall advance.
            # If net < 0, it means we have overall due.
            net_balance_current = total_advance_current - total_due_current
            net_balance_new = new_advance - new_due

            difference = net_balance_new - net_balance_current
            
            if difference != 0:
                # Add an adjustment expense to reconcile the sum
                adjustment_advance = difference if difference > 0 else 0
                adjustment_due = abs(difference) if difference < 0 else 0
                
                from datetime import datetime
                Expence.objects.create(
                    suplier=supplier_name,
                    date=datetime.now().date(),
                    narration="Balance Adjustment from Edit",
                    advance=adjustment_advance,
                    due=adjustment_due,
                    total_pay=0
                )

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})

@csrf_exempt
def supplier_ledger(request):
    # Get unique supplier list from Expence
    suppliers = Expence.objects.values_list('suplier', flat=True).distinct()
    years = range(2020, 2031)
    ledger_rows = []
    supplier_name = ""
    selected_year = None
    opening_balance = 0

    if request.method == "POST":
        supplier = request.POST.get("supplier")
        year = request.POST.get("year")

        if supplier and year:
            selected_year = int(year)
            supplier_name = supplier

            # Get all expenses for this supplier in the selected year
            expenses = Expence.objects.filter(suplier=supplier, date__year=selected_year)

            # Get all previous expenses for opening balance
            prev_expenses = Expence.objects.filter(suplier=supplier, date__year__lt=selected_year)

            # Calculate opening balance (Advance - Due up to previous year)
            opening_advance = sum(e.advance for e in prev_expenses)
            opening_due = sum(e.due for e in prev_expenses)
            opening_balance = opening_advance - opening_due

            # Gather all transactions for the year
            transactions = []
            for exp in expenses:
                # Debit: Due (you owe supplier), Credit: Advance (you paid in advance)
                transactions.append({
                    "date": exp.date,
                    "particulars": exp.narration or "Expense",
                    "debit": exp.due,
                    "credit": exp.advance,
                })

            # Sort all transactions by date
            transactions.sort(key=lambda x: x["date"] or "")

            # Build ledger rows with running balance
            balance = opening_balance
            for t in transactions:
                balance = balance + (t["credit"] or 0) - (t["debit"] or 0)
                ledger_rows.append({
                    "date": t["date"].strftime("%d/%m/%y") if t["date"] else "",
                    "particulars": t["particulars"],
                    "debit": t["debit"] if t["debit"] else "",
                    "credit": t["credit"] if t["credit"] else "",
                    "balance": balance,
                })

    context = {
        "suppliers": suppliers,
        "years": years,
        "ledger_rows": ledger_rows,
        "supplier_name": supplier_name,
        "selected_year": selected_year,
        "opening_balance": opening_balance,
    }
    return render(request, "ledger_supplier.html", context)
