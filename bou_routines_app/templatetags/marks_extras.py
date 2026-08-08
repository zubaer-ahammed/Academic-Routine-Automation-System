from decimal import Decimal
import math

from django import template


register = template.Library()


@register.simple_tag
def final_exam_q_value(final_mark, teacher_role, q_index):
    """Display value for a theory final-exam question input (blank if unset)."""
    if not final_mark:
        return ''
    role = str(teacher_role or 'teacher1')
    if role == 'teacher2':
        prefix = 'teacher2'
    elif role == 'teacher3':
        prefix = 'teacher3'
    else:
        prefix = 'teacher1'
    vals = [getattr(final_mark, f'{prefix}_q{i}', None) for i in range(1, 8)]
    # Legacy/default fill wrote 0 in every Q for unused examiner columns — show blank.
    # Intentional marks never set all seven to 0 (group rules allow at most five entered).
    if vals and all(v is not None and float(v) == 0 for v in vals):
        return ''
    val = vals[int(q_index) - 1] if 1 <= int(q_index) <= 7 else None
    if val is None:
        return ''
    return str(int(float(val)))


@register.simple_tag
def final_exam_lab_field_value(final_mark, teacher_role, field_name):
    """Display value for lab final/viva inputs (blank if unset)."""
    if not final_mark:
        return ''
    role = str(teacher_role or 'teacher1')
    prefix = 'teacher2' if role == 'teacher2' else 'teacher1'
    val = getattr(final_mark, f'{prefix}_{field_name}', None)
    if val is None:
        return ''
    return f'{float(val):.2f}'


@register.filter
def mark_input_value(value, decimals='2'):
    """
    Format a mark for use in <input value="...">: blank when unset (None), otherwise numeric.
    Second argument is decimal places (0 for integer question-set marks).
    """
    if value is None:
        return ''
    try:
        places = int(decimals)
    except (ValueError, TypeError):
        places = 2
    num = float(value)
    if places <= 0:
        return str(int(num))
    return f'{num:.{places}f}'


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

