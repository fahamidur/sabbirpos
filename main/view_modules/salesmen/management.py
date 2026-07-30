"""Salesmen views: management."""

from ..common import *

@csrf_exempt
def salesman_list(request):
    if request.method == 'POST':
        # Adding a new salesmanm
        name = request.POST.get('name')
        code = request.POST.get('code')
        area = request.POST.get('area')
        phone = request.POST.get('phone')
        nid = request.POST.get('nid')
        comission = float(request.POST.get('comission', 0) or 0)
        basic_salary = float(request.POST.get('basic_salary', 0) or 0)
        if name and code and area and phone and nid:
            Salesman.objects.create(
                name=name,
                code=code,
                area=area,
                phone=phone,
                nid=nid,
                comission=comission,
                basic_salary=basic_salary
            )
            return redirect('salesman_list')

    # Period filter: all_time (default), last_month, custom (month + year)
    today = datetime.now().date()
    period = (request.GET.get('period') or 'all_time').strip().lower()
    filter_year = None
    filter_month = None
    if period == 'last_month':
        if today.month == 1:
            filter_year = today.year - 1
            filter_month = 12
        else:
            filter_year = today.year
            filter_month = today.month - 1
    elif period == 'custom':
        try:
            filter_year = int(request.GET.get('year') or 0)
            filter_month = int(request.GET.get('month') or 0)
            if not (1 <= filter_month <= 12 and filter_year >= 2000):
                period = 'all_time'
                filter_year = filter_month = None
        except (ValueError, TypeError):
            period = 'all_time'
            filter_year = filter_month = None

    # Base querysets for Sale and Adai (optionally filtered by date)
    sale_qs = Sale.objects.all()
    adai_qs = Adai.objects.all()
    if filter_year and filter_month:
        sale_qs = sale_qs.filter(date__year=filter_year, date__month=filter_month)
        adai_qs = adai_qs.filter(date__year=filter_year, date__month=filter_month)

    # Fetching all salesmen
    salesmen_list = Salesman.objects.all()
    # Commission from all sales (filtered by period)
    commission_from_sales = dict(
        sale_qs.values('salesman').annotate(total=Sum('comission')).values_list('salesman', 'total')
    )
    # Commission from Adai (filtered by period)
    commission_from_adai = dict(
        adai_qs.filter(salesman__isnull=False).values('salesman').annotate(total=Sum('sales_comission')).values_list('salesman', 'total')
    )
    # Total paid sales per salesman (filtered by period)
    paid_sales_by_salesman = dict(
        sale_qs.values('salesman').annotate(total=Sum('payment_received')).values_list('salesman', 'total')
    )
    # Total collection (due + advance) per salesman from Adai (filtered by period)
    salesmen_with_adai = []
    for salesman in salesmen_list:
        adai_records = adai_qs.filter(salesman=salesman)
        total_due = sum(a.due or 0 for a in adai_records)
        total_advance = sum(a.advance or 0 for a in adai_records)
        total_collection = total_due + total_advance
        total_paid_sales = paid_sales_by_salesman.get(salesman.id, 0) or 0
        total_sales = total_collection + total_paid_sales
        total_commission = (commission_from_sales.get(salesman.id, 0) or 0) + (commission_from_adai.get(salesman.id, 0) or 0)
        s = {
            'id': salesman.id,
            'name': salesman.name,
            'code': salesman.code,
            'area': salesman.area,
            'phone': salesman.phone,
            'comission': salesman.comission,
            'basic_salary': getattr(salesman, 'basic_salary', 0),
            'salescomission': total_commission,
            'adai': total_collection,
            'total_collection': total_collection,
            'total_paid_sales': total_paid_sales,
            'total_sales': total_sales,
        }
        s['json'] = json.dumps(s)
        salesmen_with_adai.append(s)

    # Build list of months for custom dropdown (1-12)
    months = [{'value': i, 'label': calendar.month_name[i]} for i in range(1, 13)]
    current_year = today.year
    years = list(range(current_year, current_year - 11, -1))  # current year and 10 past years
    context = {
        'salesmen': salesmen_with_adai,
        'period': period,
        'filter_month': filter_month or today.month,
        'filter_year': filter_year or current_year,
        'months': months,
        'years': years,
    }
    return render(request, 'Salesman.html', context)

@csrf_exempt
def delete_salesman(request, salesman_id):
    if request.method == 'POST':
        try:
            salesman = Salesman.objects.get(id=salesman_id)
            salesman.delete()
        except Salesman.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('salesman_list')

@csrf_exempt
@require_POST
def update_salesman(request, salesman_id):
    import json
    from django.http import JsonResponse
    from main.models import Salesman
    try:
        data = json.loads(request.body)
        salesman = Salesman.objects.get(id=salesman_id)
        salesman.name = data.get('name', salesman.name)
        salesman.code = data.get('code', salesman.code)
        salesman.area = data.get('area', salesman.area)
        salesman.phone = data.get('phone', salesman.phone)
        try:
            salesman.comission = float(data.get('comission', salesman.comission))
        except (TypeError, ValueError):
            pass
        try:
            salesman.salescomission = float(data.get('salescomission', salesman.salescomission))
        except (TypeError, ValueError):
            pass
        try:
            salesman.basic_salary = float(data.get('basic_salary', getattr(salesman, 'basic_salary', 0)))
        except (TypeError, ValueError):
            pass
        salesman.save()
        return JsonResponse({'status': 'success'})
    except Salesman.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Salesman not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
