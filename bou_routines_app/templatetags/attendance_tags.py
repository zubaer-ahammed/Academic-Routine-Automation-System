from django import template
from bou_routines_app.models import Teacher

register = template.Library()

@register.filter
def dict_key(dictionary, key):
    """Get value from dictionary by key"""
    if dictionary and key in dictionary:
        return dictionary[key]
    return None

@register.filter
def has_teacher_profile(user):
    """Check if user has a teacher profile"""
    if not user or not user.is_authenticated:
        return False
    try:
        # Try to access the teacher relationship
        # This will raise Teacher.DoesNotExist if no teacher profile exists
        teacher = user.teacher
        return teacher is not None
    except (Teacher.DoesNotExist, AttributeError):
        return False

@register.filter
def is_teacher_only(user):
    """Check if user is a teacher (has teacher profile) - restrict access unless superuser"""
    if not user or not user.is_authenticated:
        return False
    # Must have teacher profile
    if not has_teacher_profile(user):
        return False
    # Superusers can access everything, but regular teachers (even with staff status) should be restricted
    return not user.is_superuser

@register.filter
def is_date_allowed(check_date, allowed_range):
    """
    Check if a date is within the allowed range.
    allowed_range should be a tuple/list: (allowed_start_date, allowed_end_date)
    Returns True if date is within range, False otherwise.
    If allowed_range is None, returns True (no restrictions - for admins).
    """
    try:
        # If no allowed_range is provided (None), all dates are allowed (admin access)
        if not allowed_range:
            return True
        
        # Handle tuple/list
        if hasattr(allowed_range, '__iter__') and not isinstance(allowed_range, str):
            allowed_range = list(allowed_range)
            if len(allowed_range) != 2:
                return False
            allowed_start_date, allowed_end_date = allowed_range
        else:
            return False
        
        if not allowed_start_date or not allowed_end_date:
            return False
        
        # Convert to date objects if they're strings
        from datetime import datetime
        if isinstance(check_date, str):
            try:
                check_date = datetime.strptime(check_date, "%Y-%m-%d").date()
            except:
                return False
        
        if isinstance(allowed_start_date, str):
            try:
                allowed_start_date = datetime.strptime(allowed_start_date, "%Y-%m-%d").date()
            except:
                return False
        
        if isinstance(allowed_end_date, str):
            try:
                allowed_end_date = datetime.strptime(allowed_end_date, "%Y-%m-%d").date()
            except:
                return False
        
        return allowed_start_date <= check_date <= allowed_end_date
    except Exception as e:
        # Log the error for debugging
        print(f"Error in is_date_allowed filter: {e}")
        return False
