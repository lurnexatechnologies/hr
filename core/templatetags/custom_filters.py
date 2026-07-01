from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if not dictionary:
        return None
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None

@register.filter
def replace(value, arg):
    if not isinstance(value, str):
        return value
    if ',' in arg:
        old, new = arg.split(',', 1)
        return value.replace(old, new)
    return value.replace(arg, '')

@register.filter
def format_currency(value):
    if value is None or value == '':
        return '0.00'
    try:
        val_float = float(value)
        return f"{val_float:,.2f}"
    except (ValueError, TypeError):
        return value
