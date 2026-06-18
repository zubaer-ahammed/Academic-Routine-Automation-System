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
def is_office_staff(user):
    from bou_routines_app.views import user_is_office_staff
    return user_is_office_staff(user)


@register.filter
def can_assign_course_teacher(user):
    from bou_routines_app.views import user_can_assign_course_teacher
    return user_can_assign_course_teacher(user)


@register.filter
def can_assign_examiners(user):
    from bou_routines_app.views import user_can_assign_examiners
    return user_can_assign_examiners(user)


@register.filter
def can_assign_chairman(user):
    from bou_routines_app.views import user_can_assign_chairman
    return user_can_assign_chairman(user)


@register.filter
def can_use_assign_menu(user):
    from bou_routines_app.views import user_has_any_assign_permission
    return user_has_any_assign_permission(user)

@register.filter
def is_date_allowed(check_date, allowed_range):
    """
    Check if a date is within the allowed range.
    allowed_range should be a tuple/list: (allowed_start_date, allowed_end_date)
    Returns True if date is within range, False otherwise.
    If allowed_range is None, returns False (restrict all dates - for safety).
    Note: Admins should have allowed_range set to a wide range in the view.
    """
    try:
        # If no allowed_range is provided (None), restrict all dates by default
        # This is safer - admins should have their restrictions handled differently
        if not allowed_range:
            print(f"DEBUG is_date_allowed: allowed_range is None/empty, returning False for date {check_date}")
            return False
        
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
        
        # Convert to date objects if they're strings or other types
        from datetime import datetime, date
        from django.utils import dateparse
        
        # Handle check_date - could be date object, string, or datetime
        if isinstance(check_date, str):
            try:
                check_date = datetime.strptime(check_date, "%Y-%m-%d").date()
            except:
                try:
                    check_date = dateparse.parse_date(check_date)
                    if not check_date:
                        return False
                except:
                    return False
        elif hasattr(check_date, 'date'):
            # If it's a datetime object, convert to date
            check_date = check_date.date()
        elif not isinstance(check_date, date):
            return False
        
        # Handle allowed_start_date
        if isinstance(allowed_start_date, str):
            try:
                allowed_start_date = datetime.strptime(allowed_start_date, "%Y-%m-%d").date()
            except:
                try:
                    allowed_start_date = dateparse.parse_date(allowed_start_date)
                    if not allowed_start_date:
                        return False
                except:
                    return False
        elif hasattr(allowed_start_date, 'date'):
            allowed_start_date = allowed_start_date.date()
        elif not isinstance(allowed_start_date, date):
            return False
        
        # Handle allowed_end_date
        if isinstance(allowed_end_date, str):
            try:
                allowed_end_date = datetime.strptime(allowed_end_date, "%Y-%m-%d").date()
            except:
                try:
                    allowed_end_date = dateparse.parse_date(allowed_end_date)
                    if not allowed_end_date:
                        return False
                except:
                    return False
        elif hasattr(allowed_end_date, 'date'):
            allowed_end_date = allowed_end_date.date()
        elif not isinstance(allowed_end_date, date):
            return False
        
        # Now compare dates
        result = allowed_start_date <= check_date <= allowed_end_date
        if not result:
            print(f"DEBUG is_date_allowed: Date {check_date} is OUTSIDE range {allowed_start_date} to {allowed_end_date}")
        return result
    except Exception as e:
        # Log the error for debugging
        print(f"Error in is_date_allowed filter: {e}")
        return False
