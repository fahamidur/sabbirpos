"""Finance views: salesman payments."""

from ..common import *

@csrf_exempt
def salesmanpayment(request):
    if request.method == 'POST':
        # Adding a new salesman
        name = request.POST.get('name')
        code = request.POST.get('code')
        area = request.POST.get('area')
        phone = request.POST.get('phone')
        nid = request.POST.get('nid')
        comission = float(request.POST.get('comission')) if request.POST.get('comission') else 0.0
        totalcomission = float(request.POST.get('totalcomission')) if request.POST.get('totalcomission') else 0.0
        
        if name and code and area and phone and nid:
            Salesman.objects.create(
                name=name,
                code=code,
                area=area,
                phone=phone,
                nid=nid,
                comission=comission,
                salescomission=totalcomission
            )
            return redirect('salesman_list')

    # Fetching all salesmen
    salesmen_list = Salesman.objects.all()
    return render(request, 'Salesman.html', {'salesmen': salesmen_list})

@csrf_exempt
def delete_salesmanpayment(request, salesman_id):
    if request.method == 'POST':
        try:
            salesman = Salesman.objects.get(id=salesman_id)
            salesman.delete()
        except Salesman.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('salesman_list')

def salespayjust(request):
    salesmen = Salesman.objects.all()
    now = datetime.now()
    sales_data = []
    for salesman in salesmen:
        # Sum salary payments for current month
        month_salary_paid = SalesmanSalaryPayment.objects.filter(
            salesman=salesman,
            date__year=now.year,
            date__month=now.month
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        sales_data.append({
            'id': salesman.id,
            'name': salesman.name,
            'code': salesman.code,
            'area': salesman.area,
            'phone': salesman.phone,
            'nid': salesman.nid,
            'comission': salesman.comission,
            'salescomission': salesman.salescomission,
            'Due': salesman.Due,
            'Paid': salesman.Paid,
            'basic_salary': getattr(salesman, 'basic_salary', 0),
            'month_salary_paid': month_salary_paid,
        })
    context = {
        'salesman': sales_data,
    }
   
    return render(request, 'salesmanpayment.html', context)

@csrf_exempt
def salesman_pay(request):
    """Handle commission or salary payment for a salesman (JSON version)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            salesman_id = data.get('product_id')
            quantity = float(data.get('quantity', 0))
            payment_type = data.get('payment_type', 'commission')
            date_str = data.get('date')
            from datetime import datetime
            payment_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now().date()

            # Validate inputs
            if not salesman_id or not quantity:
                return JsonResponse({'status': 'error', 'error': 'Missing required fields'})
            if quantity <= 0:
                return JsonResponse({'status': 'error', 'error': 'Quantity must be positive'})

            # Update salesman's commission or salary
            try:
                salesman = Salesman.objects.get(id=salesman_id)
                if payment_type == 'salary':
                    # Save salary payment
                    SalesmanSalaryPayment.objects.create(
                        salesman=salesman,
                        amount=quantity,
                        date=payment_date
                    )
                    return JsonResponse({'status': 'success'})
                else:
                    # Commission payment (existing logic)
                    if salesman.salescomission >= quantity:
                        salesman.salescomission -= quantity
                        salesman.Paid += quantity
                        salesman.save()
                        return JsonResponse({'status': 'success'})
                    else:
                        return JsonResponse({'status': 'error', 'error': 'Insufficient commission to pay.'})
            except Salesman.DoesNotExist:
                return JsonResponse({'status': 'error', 'error': 'Salesman not found'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})
