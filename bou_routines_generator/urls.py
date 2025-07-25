"""
URL configuration for bou_routines_generator project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from bou_routines_app.views import export_academic_calendar_pdf

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('bou_routines_app.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('export-academic-calendar/<int:semester_id>/', export_academic_calendar_pdf, name='export-academic-calendar-pdf'),
]
