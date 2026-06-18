"""Admin user impersonation (switch user) helpers."""

from django.contrib.auth.models import User

IMPERSONATE_ORIGINAL_USER_ID = '_impersonate_original_user_id'
IMPERSONATE_TARGET_USER_ID = '_impersonate_target_user_id'


def get_teacher_from_user(user):
    from .models import Teacher

    try:
        return user.teacher
    except (Teacher.DoesNotExist, AttributeError):
        return None


def is_impersonating(request):
    return bool(request.session.get(IMPERSONATE_ORIGINAL_USER_ID))


def get_impersonator_user(request):
    original_id = request.session.get(IMPERSONATE_ORIGINAL_USER_ID)
    if not original_id:
        return None
    return User.objects.filter(pk=original_id).first()


def user_can_impersonate(actor):
    if not actor or not actor.is_authenticated:
        return False
    if get_teacher_from_user(actor) and not actor.is_superuser:
        return False
    return actor.is_superuser or actor.is_staff


def can_switch_to_user(actor, target):
    if not user_can_impersonate(actor):
        return False
    if not target or not target.is_active:
        return False
    if actor.pk == target.pk:
        return False
    if target.is_superuser and not actor.is_superuser:
        return False
    return True
