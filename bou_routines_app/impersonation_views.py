from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .impersonation import (
    IMPERSONATE_ORIGINAL_USER_ID,
    IMPERSONATE_TARGET_USER_ID,
    can_switch_to_user,
    is_impersonating,
    user_can_impersonate,
)
from .views import user_is_office_staff


def _auth_backend(request):
    return getattr(request.user, 'backend', None) or settings.AUTHENTICATION_BACKENDS[0]


def _redirect_for_user(user):
    if user_is_office_staff(user):
        return redirect('assign-home')
    return redirect('home')


@login_required
@require_POST
def switch_user(request, user_id):
    if is_impersonating(request):
        messages.error(request, 'Exit the current switched session before switching to another user.')
        return redirect('home')

    target = get_object_or_404(User, pk=user_id, is_active=True)
    if not can_switch_to_user(request.user, target):
        messages.error(request, 'You do not have permission to switch to this user.')
        return redirect('admin:auth_user_change', target.pk)

    original_pk = request.user.pk
    target_pk = target.pk
    login(request, target, backend=_auth_backend(request))
    request.session[IMPERSONATE_ORIGINAL_USER_ID] = original_pk
    request.session[IMPERSONATE_TARGET_USER_ID] = target_pk
    messages.success(
        request,
        f'You are now logged in as {target.username}. Use Exit to return to your account.',
    )
    return _redirect_for_user(target)


@login_required
@require_POST
def exit_impersonation(request):
    if not is_impersonating(request):
        messages.info(request, 'You are not using a switched-user session.')
        return redirect('home')

    target_id = request.session.get(IMPERSONATE_TARGET_USER_ID)
    original_id = request.session.get(IMPERSONATE_ORIGINAL_USER_ID)
    original = User.objects.filter(pk=original_id).first() if original_id else None

    if not original:
        request.session.pop(IMPERSONATE_ORIGINAL_USER_ID, None)
        request.session.pop(IMPERSONATE_TARGET_USER_ID, None)
        messages.info(request, 'You are not using a switched-user session.')
        return redirect('home')

    if not user_can_impersonate(original):
        messages.error(request, 'Your original account can no longer use user switching.')
        return redirect('login')

    login(request, original, backend=settings.AUTHENTICATION_BACKENDS[0])
    request.session.pop(IMPERSONATE_ORIGINAL_USER_ID, None)
    request.session.pop(IMPERSONATE_TARGET_USER_ID, None)
    messages.success(request, f'Returned to your account ({original.username}).')

    if target_id:
        return redirect('admin:auth_user_change', target_id)
    return redirect('admin:auth_user_changelist')
