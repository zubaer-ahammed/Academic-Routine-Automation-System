(function($) {
    $(document).ready(function() {
        // Move custom fields to the correct position (after password2 for add form, after password for change form)
        function moveCustomFields() {
            var $userTypeField = $('#id_user_type').closest('.form-row, .field-user_type, .form-group, div').first();
            var $teacherField = $('#id_teacher').closest('.form-row, .field-teacher, .form-group, div').first();
            var $studentField = $('#id_student').closest('.form-row, .field-student, .form-group, div').first();
            
            // Find the password field to insert after
            var $passwordField = $('#id_password2').closest('.form-row, .field-password2, .form-group, div').first();
            if ($passwordField.length === 0) {
                // For change form, look for password field
                $passwordField = $('#id_password').closest('.form-row, .field-password, .form-group, div').first();
            }
            
            if ($passwordField.length > 0 && $userTypeField.length > 0) {
                // Move fields after password field
                $userTypeField.insertAfter($passwordField);
                $teacherField.insertAfter($userTypeField);
                $studentField.insertAfter($teacherField);
            }
        }
        
        function toggleProfileFields() {
            var userType = $('#id_user_type').val();
            var $teacherField = $('#id_teacher').closest('.form-row, .field-teacher, .form-group, div').first();
            var $studentField = $('#id_student').closest('.form-row, .field-student, .form-group, div').first();
            
            // Hide both fields initially
            $teacherField.hide();
            $studentField.hide();
            
            // Show appropriate field based on type
            if (userType === 'teacher') {
                $teacherField.show();
            } else if (userType === 'student') {
                $studentField.show();
            }
        }
        
        // Move fields first, then toggle visibility
        moveCustomFields();
        toggleProfileFields();
        
        // Run when type changes
        $('#id_user_type').on('change', toggleProfileFields);
    });
})(django.jQuery || jQuery);

