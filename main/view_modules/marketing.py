"""Marketing views."""

from .common import *

@csrf_exempt
def marketing_cost(request):
    from django.contrib import messages
    from main.models import Customer
    # Filter customers by selected salesman (like pos_dashboard)
    selected_salesman_id = request.GET.get('salesman') or request.POST.get('salesman')
    if selected_salesman_id:
        try:
            selected_salesman = Salesman.objects.get(id=selected_salesman_id)
            code_range = selected_salesman.code
            if '-' in code_range:
                start_code, end_code = code_range.split('-')
                try:
                    start_code = int(start_code)
                    end_code = int(end_code)
                    filtered_customers = [
                        c for c in Customer.objects.all()
                        if c.code.isdigit() and start_code <= int(c.code) <= end_code
                    ]
                except ValueError:
                    filtered_customers = Customer.objects.none()
            else:
                filtered_customers = Customer.objects.none()
        except Salesman.DoesNotExist:
            filtered_customers = Customer.objects.none()
    else:
        filtered_customers = Customer.objects.all()

    if request.method == 'POST':
        date = request.POST.get('date')
        salesman_id = request.POST.get('salesman')
        customer_id =0
        invoice_number =0
        expense_type = request.POST.get('expense_type')
        amount = request.POST.get('amount')
        try:
            salesman = Salesman.objects.get(id=salesman_id)
            # customer = Customer.objects.get(id=customer_id)
            MarketingCost.objects.create(
                date=date,
                salesman=salesman,
                customer_name='null',
                invoice_number=invoice_number,
                expense_type=expense_type,
                amount=amount
            )
            messages.success(request, 'Marketing cost entry added successfully!')
            return redirect('marketing_cost')
        except Salesman.DoesNotExist:
            messages.error(request, 'Salesman not found!')
        except Customer.DoesNotExist:
            messages.error(request, 'Customer not found!')
        except Exception as e:
            messages.error(request, f'Error: {e}')
    salesmen = Salesman.objects.all()
    invoices = Sale.objects.filter(invoice_number__isnull=False).exclude(invoice_number='').order_by('-date')
    return render(request, 'marketing_cost.html', {'salesmen': salesmen, 'customers': filtered_customers, 'invoices': invoices})


@csrf_exempt
def marketing_cost_list(request):
    from main.models import MarketingCost, Salesman
    from django.contrib import messages
    salesmen = Salesman.objects.all()
    selected_salesman = request.GET.get('salesman', '')
    selected_month = request.GET.get('month', '')
    marketing_costs = MarketingCost.objects.all().order_by('-date')
    if selected_salesman:
        marketing_costs = marketing_costs.filter(salesman_id=selected_salesman)
    if selected_month:
        try:
            year, month = selected_month.split('-')
            marketing_costs = marketing_costs.filter(
                date__year=int(year),
                date__month=int(month)
            )
        except (ValueError, TypeError):
            messages.error(request, 'Invalid month filter format.')
    context = {
        'salesmen': salesmen,
        'selected_salesman': selected_salesman,
        'selected_month': selected_month,
        'marketing_costs': marketing_costs,
    }
    return render(request, 'marketing_cost_list.html', context)


@csrf_exempt
def delete_marketing_cost(request, cost_id):
    from main.models import MarketingCost
    from django.contrib import messages
    if request.method == 'POST':
        try:
            cost = MarketingCost.objects.get(id=cost_id)
            cost.delete()
            messages.success(request, 'Marketing cost entry deleted successfully!')
        except MarketingCost.DoesNotExist:
            messages.error(request, 'Marketing cost entry not found!')
    return redirect(reverse('marketing_cost_list'))


