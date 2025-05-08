from django.urls import path
from . import views

urlpatterns = [
    path('', views.routine_entry, name='routine-entry'),
    path('generate/', views.generate_routine, name='generate-routine'),
    path('create-semester/', views.create_semester, name='create-semester'),
]
