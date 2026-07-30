"""Finance views: banking."""

from ..common import *

@csrf_exempt
def transaction_list(request):
    if request.method == 'POST':
        # Check if this is a new bank account creation
        if 'bank_name' in request.POST:
            # Creating a new bank account
            bank_name = request.POST.get('bank_name')
            branch_name = request.POST.get('branch_name')
            account_number = request.POST.get('account_number')
            opening_balance = float(request.POST.get('opening_balance', 0))
            
            if bank_name and branch_name and account_number:
                # Create new bank account
                bank_account = BankAccount.objects.create(
                    bank_name=bank_name,
                    branch_name=branch_name,
                    account_number=account_number,
                    opening_balance=opening_balance,
                    current_balance=opening_balance
                )
                messages.success(request, 'Bank account created successfully!')
        else:
            # Adding a new transaction
            bank_account_id = request.POST.get('bank_account')
            date = request.POST.get('transactionDate')
            narration = request.POST.get('narration')
            transaction_type = request.POST.get('transaction_type')
            amount = float(request.POST.get('amount', 0))
            
            if bank_account_id and date and narration and transaction_type and amount:
                try:
                    bank_account = BankAccount.objects.get(id=bank_account_id)
                    Transaction.objects.create(
                        bank_account=bank_account,
                        date=date,
                        narration=narration,
                        transaction_type=transaction_type,
                        amount=amount
                    )
                    messages.success(request, 'Transaction added successfully!')
                except BankAccount.DoesNotExist:
                    messages.error(request, 'Bank account not found!')
            
        return redirect('transaction_list')
    
    # Get filter parameters
    selected_bank = request.GET.get('ledger_bank')
    selected_month = request.GET.get('ledger_month')
    selected_year = request.GET.get('ledger_year')

    # Filter transactions for ledger
    ledger_transactions = None
    if selected_bank and selected_month and selected_year:
        ledger_transactions = Transaction.objects.filter(
            bank_account_id=selected_bank,
            date__year=selected_year,
            date__month=selected_month
        ).order_by('date')
    
    # Fetch all bank accounts and their transactions
    bank_accounts = BankAccount.objects.all()
    transactions = Transaction.objects.all().order_by('-date')
    
    # Generate month and year options
    months = [
        {'number': 1, 'name': 'January'},
        {'number': 2, 'name': 'February'},
        {'number': 3, 'name': 'March'},
        {'number': 4, 'name': 'April'},
        {'number': 5, 'name': 'May'},
        {'number': 6, 'name': 'June'},
        {'number': 7, 'name': 'July'},
        {'number': 8, 'name': 'August'},
        {'number': 9, 'name': 'September'},
        {'number': 10, 'name': 'October'},
        {'number': 11, 'name': 'November'},
        {'number': 12, 'name': 'December'}
    ]
    years = range(2020, datetime.now().year + 1)
    
    context = {
        'bank_accounts': bank_accounts,
        'transactions': transactions,
        'ledger_transactions': ledger_transactions,
        'selected_bank': selected_bank,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months': months,
        'years': years
    }
    return render(request, 'bankinfo.html', context)

@csrf_exempt
def delete_transaction(request, transaction_id):
    if request.method == 'POST':
        try:
            transaction = Transaction.objects.get(id=transaction_id)
            # Reverse the transaction's effect on the bank account balance
            bank_account = transaction.bank_account
            if transaction.transaction_type == 'debit':
                bank_account.current_balance = float(bank_account.current_balance) + float(transaction.amount)
            else:  # credit
                bank_account.current_balance = float(bank_account.current_balance) - float(transaction.amount)
            bank_account.save()
            
            # Delete the transaction
            transaction.delete()
            messages.success(request, 'Transaction deleted successfully!')
        except Transaction.DoesNotExist:
            messages.error(request, 'Transaction not found!')
    return redirect('transaction_list')

@csrf_exempt
def update_transaction(request, transaction_id):
    if request.method == 'POST':
        try:
            from main.models import Transaction, BankAccount
            transaction = Transaction.objects.get(id=transaction_id)
            bank_account_id = request.POST.get('bank_account')
            date = request.POST.get('transactionDate')
            narration = request.POST.get('narration')
            transaction_type = request.POST.get('transaction_type')
            amount = float(request.POST.get('amount', 0) or 0)
            if bank_account_id:
                try:
                    bank_account = BankAccount.objects.get(id=bank_account_id)
                    transaction.bank_account = bank_account
                except BankAccount.DoesNotExist:
                    pass
            if date:
                transaction.date = date
            if narration is not None:
                transaction.narration = narration
            if transaction_type:
                transaction.transaction_type = transaction_type
            transaction.amount = amount
            transaction.save()
        except Transaction.DoesNotExist:
            pass
        return redirect('transaction_list')
    return redirect('transaction_list')
