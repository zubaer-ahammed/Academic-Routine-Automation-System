from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, AdminPasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.http import HttpResponseRedirect, Http404
from django.contrib.auth import update_session_auth_hash, logout
from django.template.response import TemplateResponse
from .models import Teacher, Semester, Course, CurrentRoutine, NewRoutine, SemesterCourse, LoginLog, Student, Attendance, Curriculum, CAMark, FinalExamMark, Centre, ProgramCoordinator

@admin.register(CurrentRoutine)
class CurrentRoutineAdmin(admin.ModelAdmin):
    list_display = ('id', 'semester', 'course', 'get_teacher', 'start_time', 'end_time', 'day')
    list_filter = ('semester', 'day')
    search_fields = ('course__code', 'semester__name')
    ordering = ('semester', 'day', 'start_time')
    
    def get_teacher(self, obj):
        return obj.teacher.name
    get_teacher.short_description = 'Teacher'
    get_teacher.admin_order_field = 'course__teacher'

@admin.register(Centre)
class CentreAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('name',)

@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code', 'is_active', 'effective_from', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'code', 'description')
    ordering = ('-is_active', 'name')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'description', 'is_active')
        }),
        ('Timeline', {
            'fields': ('effective_from',)
        }),
        ('Theory CA Distribution', {
            'fields': ('theory_ca_attendance_weight', 'theory_ca_assignment_weight', 'theory_ca_quiz_weight', 'theory_ca_midterm_weight'),
            'description': 'Default CA mark distribution for Theory courses in this curriculum. Total should be 30% (for 70% final exam).'
        }),
        ('Lab CA Distribution', {
            'fields': ('lab_ca_attendance_weight', 'lab_ca_assignment_weight', 'lab_ca_practical_weight', 'lab_ca_quiz_weight'),
            'description': 'Default CA mark distribution for Lab courses in this curriculum. Total should be 40% (for 60% final exam).'
        }),
        ('Project Work Distribution', {
            'fields': ('project_supervisor_weight', 'project_evaluation_weight', 'project_presentation_weight'),
            'description': 'Mark distribution for Project Work courses. Total should be 100%.'
        }),
    )

class CourseAdminForm(forms.ModelForm):
    """Custom form for Course admin with radio buttons for course type"""
    
    COURSE_TYPE_CHOICES = [
        ('theory', 'Theory Course'),
        ('lab', 'Lab Course'),
        ('project', 'Project Work'),
    ]
    
    course_type_selection = forms.ChoiceField(
        choices=COURSE_TYPE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'course-type-radio', 'style': 'list-style: none; padding: 0;'}),
        label='Course Type',
        help_text='Select whether this is a Theory course, Lab course, or Project Work'
    )
    
    class Meta:
        model = Course
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial value for radio button based on existing is_lab/is_theory/course_type values
        if self.instance and self.instance.pk:
            if self.instance.course_type == 'PROJECT':
                self.fields['course_type_selection'].initial = 'project'
            elif self.instance.is_lab:
                self.fields['course_type_selection'].initial = 'lab'
            elif self.instance.is_theory:
                self.fields['course_type_selection'].initial = 'theory'
            else:
                # Default to theory if neither is set
                self.fields['course_type_selection'].initial = 'theory'
        else:
            # For new courses, default to theory
            self.fields['course_type_selection'].initial = 'theory'
        
        # Hide the original is_lab and is_theory fields
        self.fields['is_lab'].widget = forms.HiddenInput()
        self.fields['is_theory'].widget = forms.HiddenInput()
        
        # Hide CA distribution fields - now managed at Curriculum level
        # Only hide if they exist in the form (they might be excluded)
        ca_fields_to_hide = [
            'ca_attendance_weight', 'ca_assignment_weight', 'ca_quiz_weight', 'ca_midterm_weight',
            'lab_ca_attendance_weight', 'lab_ca_assignment_weight', 'lab_ca_practical_weight'
        ]
        for field_name in ca_fields_to_hide:
            if field_name in self.fields:
                self.fields[field_name].widget = forms.HiddenInput()
    
    def clean(self):
        cleaned_data = super().clean()
        course_type = cleaned_data.get('course_type_selection')
        
        # Set is_lab, is_theory, and course_type based on radio button selection
        if course_type == 'lab':
            cleaned_data['is_lab'] = True
            cleaned_data['is_theory'] = False
            # If course_type is PROJECT, change it to CORE (project work should use project type)
            if cleaned_data.get('course_type') == 'PROJECT':
                cleaned_data['course_type'] = 'CORE'
        elif course_type == 'theory':
            cleaned_data['is_lab'] = False
            cleaned_data['is_theory'] = True
            # If course_type is PROJECT, change it to CORE (project work should use project type)
            if cleaned_data.get('course_type') == 'PROJECT':
                cleaned_data['course_type'] = 'CORE'
        elif course_type == 'project':
            cleaned_data['is_lab'] = False
            cleaned_data['is_theory'] = False
            cleaned_data['course_type'] = 'PROJECT'  # Set the course_type field to PROJECT
        
        return cleaned_data

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    list_display = ('id', 'code', 'name', 'curriculum', 'credits', 'course_type', 'is_theory', 'is_lab')
    list_filter = ('curriculum', 'course_type', 'is_theory', 'is_lab')
    search_fields = ('code', 'name', 'curriculum__name')
    ordering = ('curriculum', 'code',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'curriculum', 'course_type')
        }),
        ('Course Details', {
            'fields': ('credits', 'course_type_selection', 'is_theory', 'is_lab', 'prerequisite_courses'),
            'description': 'Select whether this is a Theory course, Lab course, or Project Work. Note: "Course type" field (Core/Elective/General/Project) in Basic Information is separate from the course type selection above.'
        }),
        # CA Distribution fields removed - now managed at Curriculum level
    )
    
    class Media:
        css = {
            'all': ('admin/css/course_type_radio.css',)
        }

@admin.register(SemesterCourse)
class SemesterCourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'semester', 'course', 'centre', 'teacher', 'effective_teacher', 'number_of_classes')
    list_filter = ('semester', 'centre', 'teacher', 'course__curriculum')
    search_fields = ('semester__name', 'course__code', 'course__name', 'teacher__name', 'centre__name')
    ordering = ('semester', 'course__code', 'centre')
    fields = ('semester', 'course', 'centre', 'teacher', 'number_of_classes')
    autocomplete_fields = ('teacher',)

class BaseTeacherUserAdminForm:
    """Base class with common fields for both add and change forms"""
    USER_TYPE_CHOICES = [
        ('', 'Select Type'),
        ('administrator', 'Administrator'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]
    
    user_type = forms.ChoiceField(
        choices=USER_TYPE_CHOICES,
        required=False,
        help_text="Select the type of user. This determines which profile can be linked."
    )
    
    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.all().order_by('name'),
        required=False,
        empty_label="Select a Teacher (optional)",
        help_text="Select an existing teacher to link to this user. Only shown when Type is 'Teacher'."
    )
    
    student = forms.ModelChoiceField(
        queryset=Student.objects.all().order_by('name'),
        required=False,
        empty_label="Select a Student (optional)",
        help_text="Select an existing student to link to this user. Only shown when Type is 'Student'."
    )

class TeacherUserAdminAddForm(UserCreationForm, BaseTeacherUserAdminForm):
    """Custom form for adding users that includes Type and conditional Teacher/Student selection"""
    
    class Meta(UserCreationForm.Meta):
        model = User
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure custom fields are added (they might be filtered out)
        # Add fields from BaseTeacherUserAdminForm if they don't exist
        if 'user_type' not in self.fields:
            self.fields['user_type'] = forms.ChoiceField(
                choices=BaseTeacherUserAdminForm.USER_TYPE_CHOICES,
                required=False,
                help_text="Select the type of user. This determines which profile can be linked."
            )
        if 'teacher' not in self.fields:
            self.fields['teacher'] = forms.ModelChoiceField(
                queryset=Teacher.objects.all().order_by('name'),
                required=False,
                empty_label="Select a Teacher (optional)",
                help_text="Select an existing teacher to link to this user. Only shown when Type is 'Teacher'."
            )
        if 'student' not in self.fields:
            self.fields['student'] = forms.ModelChoiceField(
                queryset=Student.objects.all().order_by('name'),
                required=False,
                empty_label="Select a Student (optional)",
                help_text="Select an existing student to link to this user. Only shown when Type is 'Student'."
            )
    
    def clean(self):
        """Validate that user can only be one type at a time"""
        cleaned_data = super().clean()
        user_type = cleaned_data.get('user_type')
        teacher_id = cleaned_data.get('teacher')
        student_id = cleaned_data.get('student')
        
        # Validate that only one profile type is selected
        if user_type == 'teacher' and student_id:
            raise forms.ValidationError({
                'student': 'Cannot select a student when user type is Teacher.'
            })
        
        if user_type == 'student' and teacher_id:
            raise forms.ValidationError({
                'teacher': 'Cannot select a teacher when user type is Student.'
            })
        
        if user_type == 'administrator' and (teacher_id or student_id):
            raise forms.ValidationError(
                'Administrators should not have teacher or student profiles.'
            )
        
        # Validate that required profile is selected
        if user_type == 'teacher' and not teacher_id:
            raise forms.ValidationError({
                'teacher': 'Please select a teacher when user type is Teacher.'
            })
        
        if user_type == 'student' and not student_id:
            raise forms.ValidationError({
                'student': 'Please select a student when user type is Student.'
            })
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=commit)
        
        if commit:
            user_type = self.cleaned_data.get('user_type')
            teacher_id = self.cleaned_data.get('teacher')
            student_id = self.cleaned_data.get('student')
            
            # Now link based on type
            if user_type == 'teacher' and teacher_id:
                # Unlink the selected teacher from its current user (if any)
                try:
                    existing_teacher = Teacher.objects.get(id=teacher_id)
                    if existing_teacher.user and existing_teacher.user != user:
                        existing_teacher.user = None
                        existing_teacher.save()
                except Teacher.DoesNotExist:
                    pass
                
                # Link the selected teacher to this user
                try:
                    teacher = Teacher.objects.get(id=teacher_id)
                    teacher.user = user
                    teacher.save()
                except Teacher.DoesNotExist:
                    pass
                    
            elif user_type == 'student' and student_id:
                # Unlink the selected student from its current user (if any)
                try:
                    existing_student = Student.objects.get(id=student_id)
                    if existing_student.user and existing_student.user != user:
                        existing_student.user = None
                        existing_student.save()
                except Student.DoesNotExist:
                    pass
                
                # Link the selected student to this user
                try:
                    student = Student.objects.get(id=student_id)
                    student.user = user
                    student.save()
                except Student.DoesNotExist:
                    pass
        
        return user

class TeacherUserAdminChangeForm(UserChangeForm, BaseTeacherUserAdminForm):
    """Custom form for changing users that includes Type and conditional Teacher/Student selection"""
    
    class Meta(UserChangeForm.Meta):
        model = User
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure custom fields are added (they might be filtered out by UserChangeForm)
        # Add fields from BaseTeacherUserAdminForm if they don't exist
        if 'user_type' not in self.fields:
            self.fields['user_type'] = forms.ChoiceField(
                choices=BaseTeacherUserAdminForm.USER_TYPE_CHOICES,
                required=False,
                help_text="Select the type of user. This determines which profile can be linked."
            )
        if 'teacher' not in self.fields:
            self.fields['teacher'] = forms.ModelChoiceField(
                queryset=Teacher.objects.all().order_by('name'),
                required=False,
                empty_label="Select a Teacher (optional)",
                help_text="Select an existing teacher to link to this user. Only shown when Type is 'Teacher'."
            )
        if 'student' not in self.fields:
            self.fields['student'] = forms.ModelChoiceField(
                queryset=Student.objects.all().order_by('name'),
                required=False,
                empty_label="Select a Student (optional)",
                help_text="Select an existing student to link to this user. Only shown when Type is 'Student'."
            )
        
        # Set initial values if user has a teacher or student
        if self.instance and self.instance.pk:
            try:
                teacher = self.instance.teacher
                self.fields['user_type'].initial = 'teacher'
                self.fields['teacher'].initial = teacher.id
            except Teacher.DoesNotExist:
                try:
                    student = self.instance.student
                    self.fields['user_type'].initial = 'student'
                    self.fields['student'].initial = student.id
                except Student.DoesNotExist:
                    # Check if user is staff/superuser to determine if administrator
                    if self.instance.is_staff or self.instance.is_superuser:
                        self.fields['user_type'].initial = 'administrator'
    
    def clean(self):
        """Validate that user can only be one type at a time"""
        cleaned_data = super().clean()
        user_type = cleaned_data.get('user_type')
        teacher_id = cleaned_data.get('teacher')
        student_id = cleaned_data.get('student')
        
        # Validate that only one profile type is selected
        if user_type == 'teacher' and student_id:
            raise forms.ValidationError({
                'student': 'Cannot select a student when user type is Teacher.'
            })
        
        if user_type == 'student' and teacher_id:
            raise forms.ValidationError({
                'teacher': 'Cannot select a teacher when user type is Student.'
            })
        
        if user_type == 'administrator' and (teacher_id or student_id):
            raise forms.ValidationError(
                'Administrators should not have teacher or student profiles.'
            )
        
        # Validate that required profile is selected
        if user_type == 'teacher' and not teacher_id:
            raise forms.ValidationError({
                'teacher': 'Please select a teacher when user type is Teacher.'
            })
        
        if user_type == 'student' and not student_id:
            raise forms.ValidationError({
                'student': 'Please select a student when user type is Student.'
            })
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=commit)
        
        if commit:
            user_type = self.cleaned_data.get('user_type')
            teacher_id = self.cleaned_data.get('teacher')
            student_id = self.cleaned_data.get('student')
            
            # First, unlink any existing relationships
            try:
                current_teacher = user.teacher
                current_teacher.user = None
                current_teacher.save()
            except Teacher.DoesNotExist:
                pass
            
            try:
                current_student = user.student
                current_student.user = None
                current_student.save()
            except Student.DoesNotExist:
                pass
            
            # Now link based on type
            if user_type == 'teacher' and teacher_id:
                # Unlink the selected teacher from its current user (if any)
                try:
                    existing_teacher = Teacher.objects.get(id=teacher_id)
                    if existing_teacher.user and existing_teacher.user != user:
                        existing_teacher.user = None
                        existing_teacher.save()
                except Teacher.DoesNotExist:
                    pass
                
                # Link the selected teacher to this user
                try:
                    teacher = Teacher.objects.get(id=teacher_id)
                    teacher.user = user
                    teacher.save()
                except Teacher.DoesNotExist:
                    pass
                    
            elif user_type == 'student' and student_id:
                # Unlink the selected student from its current user (if any)
                try:
                    existing_student = Student.objects.get(id=student_id)
                    if existing_student.user and existing_student.user != user:
                        existing_student.user = None
                        existing_student.save()
                except Student.DoesNotExist:
                    pass
                
                # Link the selected student to this user
                try:
                    student = Student.objects.get(id=student_id)
                    student.user = user
                    student.save()
                except Student.DoesNotExist:
                    pass
        
        return user

class WeakPasswordAdminPasswordChangeForm(AdminPasswordChangeForm):
    """Custom password change form that allows weak passwords with confirmation"""
    
    allow_weak_password = forms.BooleanField(
        required=False,
        initial=False,
        label='Allow weak password anyway',
        help_text='Check this box to set a weak password despite validation warnings.'
    )
    
    class Media:
        js = ('admin/js/weak_password_handler.js',)
    
    def __init__(self, user, *args, **kwargs):
        # Extract request if provided
        self.request = kwargs.pop('request', None)
        super().__init__(user, *args, **kwargs)
        # Disable password validators if we're allowing weak passwords
        # We'll handle this in clean() instead
    
    def clean(self):
        # Check if user wants to allow weak password BEFORE calling super().clean()
        allow_weak = (
            self.data.get('allow_weak_password') == 'on' or
            self.data.get('allow_weak_password') == True
        )
        
        # Get password values from form data before validation
        password1_raw = self.data.get('password1', '')
        password2_raw = self.data.get('password2', '')
        
        # Call parent clean() which will run validation
        cleaned_data = super().clean()
        
        # If user explicitly allows weak password, clear validation errors
        if allow_weak and password1_raw and password2_raw and password1_raw == password2_raw:
            # Clear all password-related validation errors
            for field_name in ['password1', 'password2', 'new_password1', 'new_password2']:
                if field_name in self._errors:
                    del self._errors[field_name]
            
            # Clear non-field errors that might be password-related
            if self._errors.get('__all__'):
                self._errors['__all__'] = [e for e in self._errors['__all__'] 
                                         if 'password' not in str(e).lower() and 
                                            'similar' not in str(e).lower() and
                                            'too' not in str(e).lower()]
            
            # Ensure passwords are in cleaned_data
            cleaned_data['password1'] = password1_raw
            cleaned_data['password2'] = password2_raw
            cleaned_data['allow_weak_password'] = True
        
        return cleaned_data
    
    def save(self, commit=True):
        user = self.user
        # Get password from cleaned_data - try both field name variations
        password = self.cleaned_data.get("password1") or self.cleaned_data.get("new_password1")
        if password:
            user.set_password(password)
            if commit:
                user.save()
                # Updating the password logs out all other sessions for the user
                # except the current one if update_session_auth_hash is used
                if self.request:
                    update_session_auth_hash(self.request, user)
        return user

class TeacherUserAdmin(UserAdmin):
    form = TeacherUserAdminChangeForm
    add_form = TeacherUserAdminAddForm
    change_password_form = WeakPasswordAdminPasswordChangeForm
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_user_type', 'get_profile_name')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    
    # Override add_fieldsets to exclude custom fields (they're form fields, not model fields)
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
    )
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<id>/password/',
                self.admin_site.admin_view(self.user_change_password),
                name='auth_user_password_change',
            ),
        ]
        return custom_urls + urls
    
    def user_change_password(self, request, id, form_url=''):
        user = self.get_object(request, id)
        if user is None:
            raise Http404('User object not found.')
        if request.method == 'POST':
            form = self.change_password_form(user, request.POST, request=request)
            if form.is_valid():
                form.save()
                change_message = self.construct_change_message(request, form, None)
                self.log_change(request, user, change_message)
                msg = 'Password changed successfully.'
                messages.success(request, msg)
                return HttpResponseRedirect(
                    reverse(
                        '%s:%s_%s_change' % (
                            self.admin_site.name,
                            user._meta.app_label,
                            user._meta.model_name,
                        ),
                        args=(user.pk,),
                    )
                )
        else:
            form = self.change_password_form(user, request=request)
        
        # Include the allow_weak_password field in fieldsets
        # Get all fields from the form
        form_fields = list(form.base_fields.keys())
        # Ensure allow_weak_password is included
        if 'allow_weak_password' not in form_fields:
            form_fields.append('allow_weak_password')
        # Create fieldsets - put allow_weak_password after password fields
        password_fields = [f for f in form_fields if f.startswith('password')]
        other_fields = [f for f in form_fields if f not in password_fields and f != 'allow_weak_password']
        ordered_fields = password_fields + ['allow_weak_password'] + other_fields
        fieldsets = [(None, {'fields': ordered_fields})]
        adminForm = admin.helpers.AdminForm(form, fieldsets, {})
        
        # IS_POPUP_VAR is just the string '_popup' in Django
        IS_POPUP_VAR = '_popup'
        context = {
            'title': 'Change password: %s' % user.get_username(),
            'adminForm': adminForm,
            'form_url': form_url,
            'form': form,
            'is_popup': (IS_POPUP_VAR in request.POST or
                        IS_POPUP_VAR in request.GET),
            'is_popup_var': IS_POPUP_VAR,
            'add': False,
            'change': True,
            'has_add_permission': False,
            'has_delete_permission': False,
            'has_change_permission': True,
            'has_view_permission': True,
            'has_absolute_url': False,
            'opts': self.model._meta,
            'original': user,
            'save_as': False,
            'show_save': True,
            'show_save_and_add_another': False,
            'show_save_and_continue': False,
            'show_delete_link': False,
            'inline_admin_formsets': [],
            'inline_admin_formset_extra': 0,
            **self.admin_site.each_context(request),
        }
        
        # Add form media to context to ensure JavaScript loads
        context['media'] = form.media
        # Also ensure the media includes our script
        if 'admin/js/weak_password_handler.js' not in str(context['media']):
            from django.forms import Media
            context['media'] = form.media + Media(js=['admin/js/weak_password_handler.js'])
        
        request.current_app = self.admin_site.name
        
        # Use custom template if it exists, otherwise use default
        template_name = 'admin/auth/user/change_password.html'
        return TemplateResponse(
            request,
            template_name,
            context,
        )
    
    def get_fieldsets(self, request, obj=None):
        """Override to get fieldsets without custom fields"""
        # Custom fields will be rendered by the form automatically
        # and positioned via JavaScript
        if obj is None:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)
    
    def get_user_type(self, obj):
        try:
            obj.teacher
            return "Teacher"
        except Teacher.DoesNotExist:
            try:
                obj.student
                return "Student"
            except Student.DoesNotExist:
                if obj.is_staff or obj.is_superuser:
                    return "Administrator"
                return "None"
    get_user_type.short_description = 'Type'
    
    def get_profile_name(self, obj):
        try:
            return obj.teacher.name
        except Teacher.DoesNotExist:
            try:
                return obj.student.name
            except Student.DoesNotExist:
                return "No Profile"
    get_profile_name.short_description = 'Profile Name'
    
    def get_fieldsets(self, request, obj=None):
        """Override to add custom form fields (not model fields) to fieldsets"""
        # Don't add custom fields to fieldsets - Django validates them against the model
        # Instead, we'll let the form handle them and they'll appear automatically
        # We can add them to fieldsets after form creation if needed
        if obj is None:
            return super().add_fieldsets
        return super().get_fieldsets(request, obj)
    
    class Media:
        js = ('admin/js/user_type_handler.js', 'admin/js/weak_password_handler.js',)

# Custom logout view that redirects to home
def admin_logout_view(request):
    logout(request)
    return redirect('home')

# Override admin logout URL
admin.site.logout = admin_logout_view

# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, TeacherUserAdmin)

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('name', 'username', 'email', 'short_name', 'centre')
    search_fields = ('name', 'short_name', 'user__username', 'user__email', 'designation', 'centre__name')
    list_filter = ('centre', 'department', 'designation')
    ordering = ('name',)
    
    fields = ('user', 'name', 'short_name', 'centre', 'address', 'phone', 'designation', 'department', 'join_date')
    
    def save_model(self, request, obj, form, change):
        """Override save to handle user linking/unlinking for OneToOne relationship"""
        if change:
            # Get the original teacher from database to compare
            try:
                original_teacher = Teacher.objects.get(pk=obj.pk)
                old_user = original_teacher.user
                new_user = obj.user
                
                # If user is being changed
                if old_user != new_user:
                    # If there was an old user, we don't need to do anything - 
                    # Django will handle unlinking when we set obj.user
                    
                    # If a new user is being set, unlink that user from any existing teacher
                    if new_user:
                        try:
                            existing_teacher = new_user.teacher
                            if existing_teacher and existing_teacher != obj:
                                existing_teacher.user = None
                                existing_teacher.save()
                        except Teacher.DoesNotExist:
                            pass
            except Teacher.DoesNotExist:
                # New teacher being created
                if obj.user:
                    # Unlink the new user from any existing teacher
                    try:
                        existing_teacher = obj.user.teacher
                        if existing_teacher:
                            existing_teacher.user = None
                            existing_teacher.save()
                    except Teacher.DoesNotExist:
                        pass
        
        super().save_model(request, obj, form, change)
    
    def username(self, obj):
        return obj.user.username if obj.user else ""
    username.short_description = 'Username'
    
    def email(self, obj):
        return obj.user.email if obj.user else ""
    email.short_description = 'Email'

@admin.register(ProgramCoordinator)
class ProgramCoordinatorAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'centre', 'designation', 'phone', 'email', 'is_active', 'updated_at')
    list_filter = ('centre', 'is_active', 'updated_at')
    search_fields = ('teacher__name', 'designation', 'secondary_designation', 'phone', 'email', 'centre__name')
    ordering = ('centre', 'teacher__name')
    fieldsets = (
        ('Basic Information', {
            'fields': ('teacher', 'centre', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('designation', 'secondary_designation', 'phone', 'email')
        }),
    )

@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'semester_full_name', 'curriculum', 'theory_class_duration_minutes', 'lab_class_duration_minutes', 'start_date')
    list_filter = ('curriculum',)
    search_fields = ('name', 'curriculum__name')
    ordering = ('name',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'order', 'semester_full_name', 'term', 'session', 'curriculum')
        }),
        ('Program Coordinator', {
            'fields': ('program_coordinator',)
        }),
        ('Class Durations', {
            'fields': ('theory_class_duration_minutes', 'lab_class_duration_minutes'),
            'description': 'Duration in minutes for theory and lab classes. Used for calculating class counts during routine generation.'
        }),
        ('Schedule Settings', {
            'fields': ('lunch_break_start', 'lunch_break_end', 'start_date', 'end_date')
        }),
        ('Dates', {
            'fields': ('holidays', 'makeup_dates'),
            'description': 'Comma-separated dates in YYYY-MM-DD format'
        }),
    )

@admin.register(NewRoutine)
class NewRoutineAdmin(admin.ModelAdmin):
    list_display = ('id', 'semester', 'course', 'class_date', 'day', 'start_time', 'end_time', 'get_teacher')
    list_filter = ('semester', 'day', 'class_date')
    search_fields = ('course__code', 'course__name', 'semester__name', 'day', 'class_date')
    ordering = ('semester', 'class_date', 'start_time')
    date_hierarchy = 'class_date'
    
    def get_teacher(self, obj):
        teacher = obj.teacher
        return teacher.name if teacher else 'N/A'
    get_teacher.short_description = 'Teacher'

@admin.register(LoginLog)
class LoginLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'login_time', 'ip_address', 'user_agent')
    search_fields = ('user__username', 'ip_address', 'user_agent')
    list_filter = ('user',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'get_centre', 'get_semesters', 'session', 'email')
    list_filter = ('semesters', 'session', 'centre', 'gender')
    search_fields = ('id', 'name', 'roll_number', 'email', 'user__username', 'user__email', 'father_name', 'mother_name')
    ordering = ('id',)
    filter_horizontal = ('semesters',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'id', 'name', 'centre', 'semesters', 'session', 'roll_number')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone')
        }),
        ('Personal Information', {
            'fields': ('gender', 'date_of_birth', 'father_name', 'mother_name')
        }),
    )
    readonly_fields = ('user',)
    
    def get_semesters(self, obj):
        return ", ".join([semester.name for semester in obj.semesters.all()])
    get_semesters.short_description = 'Semesters'
    
    def get_centre(self, obj):
        return obj.centre.name if obj.centre else "-"
    get_centre.short_description = 'Study Center'
    get_centre.admin_order_field = 'centre__name'


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'semester', 'attendance_date', 'is_present', 'marked_by', 'marked_at')
    list_filter = ('semester', 'course', 'attendance_date', 'is_present', 'marked_by')
    search_fields = ('student__id', 'student__name', 'course__code', 'course__name')
    ordering = ('-attendance_date', 'student__id')
    date_hierarchy = 'attendance_date'
    
    readonly_fields = ('marked_at',)
    
    fieldsets = (
        ('Attendance Information', {
            'fields': ('student', 'course', 'semester', 'attendance_date', 'is_present')
        }),
        ('Record Details', {
            'fields': ('marked_by', 'marked_at', 'notes'),
            'classes': ('collapse',)
        }),
    )

@admin.register(CAMark)
class CAMarkAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'semester', 'total_ca_mark', 'marked_by', 'updated_at')
    list_filter = ('semester', 'course', 'marked_by', 'updated_at')
    search_fields = ('student__id', 'student__name', 'course__code', 'course__name')
    ordering = ('semester', 'course', 'student__id')
    readonly_fields = ('attendance_mark', 'assignment_mark', 'lab_assignment_mark', 'class_test_mark', 'total_ca_mark', 'marked_at', 'updated_at')
    
    fieldsets = (
        ('Student & Course', {
            'fields': ('student', 'course', 'semester')
        }),
        ('Theory Course Marks', {
            'fields': ('attendance_mark', 'first_assignment_mark', 'second_assignment_mark', 'third_assignment_mark', 'assignment_mark', 'first_class_test_mark', 'second_class_test_mark', 'class_test_mark', 'midterm_mark'),
            'description': 'Marks for theory courses. Assignment mark (average) is auto-calculated from the three individual assignments. Class test mark (best of first and second) is auto-calculated. Use class tests for old curriculum, midterm for new curriculum.'
        }),
        ('Lab Course Marks', {
            'fields': ('first_lab_assignment_mark', 'second_lab_assignment_mark', 'third_lab_assignment_mark', 'lab_assignment_mark', 'lab_practical_mark'),
            'description': 'Marks for lab courses. Lab assignment mark (average) is auto-calculated from the three individual lab assignments.'
        }),
        ('Total', {
            'fields': ('total_ca_mark',)
        }),
        ('Record Details', {
            'fields': ('marked_by', 'marked_at', 'updated_at', 'notes'),
            'classes': ('collapse',)
        }),
    )

@admin.register(FinalExamMark)
class FinalExamMarkAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'semester', 'final_exam_total', 'requires_third_teacher', 'marked_by', 'updated_at')
    list_filter = ('semester', 'course', 'requires_third_teacher', 'marked_by', 'updated_at')
    search_fields = ('student__id', 'student__name', 'course__code', 'course__name')
    ordering = ('semester', 'course', 'student__id')
    readonly_fields = ('teacher1_total', 'teacher2_total', 'teacher3_total', 'final_exam_total', 'requires_third_teacher', 'marked_at', 'updated_at')
    
    fieldsets = (
        ('Student & Course', {
            'fields': ('student', 'course', 'semester')
        }),
        ('Theory Course - Teacher 1 Evaluation', {
            'fields': ('teacher1_q1', 'teacher1_q2', 'teacher1_q3', 'teacher1_q4', 'teacher1_q5', 'teacher1_q6', 'teacher1_q7', 'teacher1_total', 'teacher1_evaluator'),
            'description': 'First evaluator marks (max 14 per set, max 5 sets)'
        }),
        ('Theory Course - Teacher 2 Evaluation', {
            'fields': ('teacher2_q1', 'teacher2_q2', 'teacher2_q3', 'teacher2_q4', 'teacher2_q5', 'teacher2_q6', 'teacher2_q7', 'teacher2_total', 'teacher2_evaluator'),
            'description': 'Second evaluator marks (max 14 per set, max 5 sets)'
        }),
        ('Theory Course - Teacher 3 Evaluation', {
            'fields': ('teacher3_q1', 'teacher3_q2', 'teacher3_q3', 'teacher3_q4', 'teacher3_q5', 'teacher3_q6', 'teacher3_q7', 'teacher3_total', 'teacher3_evaluator'),
            'description': 'Third evaluator marks (required if difference > 20% or > 14 marks)'
        }),
        ('Lab Course Final Exam', {
            'fields': ('lab_final_exam_mark',),
            'description': 'Lab course final exam mark (max 60)'
        }),
        ('Totals & Status', {
            'fields': ('final_exam_total', 'requires_third_teacher')
        }),
        ('Record Details', {
            'fields': ('marked_by', 'marked_at', 'updated_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
