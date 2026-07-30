from django import template
import calendar

register = template.Library()

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''

@register.filter
def get_month_name(month_number):
    try:
        return calendar.month_name[int(month_number)]
    except (ValueError, TypeError):
        return str(month_number) 