from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Teacher, Semester, Course, CurrentRoutine, SemesterCourse

class RoutineForm(forms.ModelForm):
    class Meta:
        model = CurrentRoutine
        fields = ['semester', 'course', 'start_time', 'end_time', 'day']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'day': forms.Select(choices=[('', 'Select Day'), ('Friday', 'Friday'), ('Saturday', 'Saturday')]),
        }

class TeacherRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    
    # Teacher-specific fields
    teacher_name = forms.CharField(max_length=100, required=True, help_text="Full name as it appears in official records")
    short_name = forms.CharField(max_length=50, required=False, help_text="Short name for display in routines")
    address = forms.CharField(widget=forms.Textarea, required=False)
    phone = forms.CharField(max_length=15, required=False)
    designation = forms.CharField(max_length=100, required=False, help_text="e.g., Professor, Assistant Professor")
    department = forms.CharField(max_length=100, required=False, help_text="e.g., Computer Science & Engineering")
    join_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), required=False)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make username field more user-friendly
        self.fields['username'].help_text = 'Choose a unique username for login'
        self.fields['email'].help_text = 'Your institutional email address'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_staff = True  # Allow access to admin
        
        if commit:
            user.save()
            
            # Create teacher profile
            teacher = Teacher.objects.create(
                user=user,
                name=self.cleaned_data['teacher_name'],
                short_name=self.cleaned_data['short_name'],
                address=self.cleaned_data['address'],
                phone=self.cleaned_data['phone'],
                designation=self.cleaned_data['designation'],
                department=self.cleaned_data['department'],
                join_date=self.cleaned_data['join_date']
            )
            
            # Assign default attendance permission
            from django.contrib.auth.models import Permission
            attendance_permission = Permission.objects.get(
                codename='can_mark_attendance',
                content_type__app_label='bou_routines_app'
            )
            user.user_permissions.add(attendance_permission)
            
        return user