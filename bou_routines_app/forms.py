from django import forms
from .models import CurrentRoutine

class RoutineForm(forms.ModelForm):
    class Meta:
        model = CurrentRoutine
        fields = ['semester', 'course', 'start_time', 'end_time', 'day']