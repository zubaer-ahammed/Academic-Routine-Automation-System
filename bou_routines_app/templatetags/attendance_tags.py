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
