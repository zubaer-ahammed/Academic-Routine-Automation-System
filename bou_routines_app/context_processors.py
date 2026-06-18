from .impersonation import get_impersonator_user, is_impersonating


def impersonation(request):
    if not is_impersonating(request) or not request.user.is_authenticated:
        return {'impersonation_active': False}

    return {
        'impersonation_active': True,
        'impersonation_original_user': get_impersonator_user(request),
    }
