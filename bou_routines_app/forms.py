from django import forms
from .models import CurrentRoutine

class RoutineForm(forms.ModelForm):
    class Meta:
        model = CurrentRoutine
        fields = '__all__'