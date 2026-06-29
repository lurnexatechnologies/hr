from django import template
print("DEBUG: LOADING EMPLOYEE FILTERS")

import datetime

register = template.Library()

@register.filter
def calculate_tenure(joined_date_str):
    if not joined_date_str:
        return "N/A"
    try:
        joined_date = datetime.date.fromisoformat(joined_date_str)
        today = datetime.date.today()
        
        years = today.year - joined_date.year
        months = today.month - joined_date.month
        days = today.day - joined_date.day

        if days < 0:
            months -= 1
            # Simple approximation for days in previous month
            days += 30
        if months < 0:
            years -= 1
            months += 12

        parts = []
        if years > 0:
            parts.append(f"{years} yr{'s' if years > 1 else ''}")
        if months > 0:
            parts.append(f"{months} mo{'s' if months > 1 else ''}")
        if (days > 0 and years == 0) or not parts:
            parts.append(f"{days} d{'s' if days != 1 else ''}")
            
        return ", ".join(parts)
    except Exception as e:
        return "N/A"

@register.filter
def get_item(dictionary, key):
    if not dictionary:
        return None
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None

@register.filter
def format_iso(value):
    if not value or 'T' not in value:
        return value
    date_part, time_part = value.split('T')
    return f"{date_part} {time_part[:5]}"

@register.filter
def split(value, arg):
    return value.split(arg)

@register.filter
def strip(value):
    return value.strip()
