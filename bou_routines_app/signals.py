from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from .models import LoginLog

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    ip = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    LoginLog.objects.create(user=user, ip_address=ip, user_agent=user_agent)
    # Keep only the last 100 records
    logs = LoginLog.objects.order_by('-login_time')
    if logs.count() > 100:
        for log in logs[100:]:
            log.delete() 