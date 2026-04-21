from decimal import Decimal
import math

from django import template


register = template.Library()


@register.filter
def ceil_int(value):
    """
    Ceiling to next integer for numeric values.
    Returns empty string for None/blank; otherwise an int.
    """
    if value is None or value == '':
        return ''
    try:
        if isinstance(value, Decimal):
            return int(value.to_integral_value(rounding='ROUND_CEILING'))
        return int(math.ceil(float(value)))
    except (ValueError, TypeError):
        return value

