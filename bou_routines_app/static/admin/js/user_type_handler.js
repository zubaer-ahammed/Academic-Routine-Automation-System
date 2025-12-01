(function($) {
    $(document).ready(function() {
        function toggleProfileFields() {
            var userType = $('#id_user_type').val();
            var $teacherField = $('#id_teacher').closest('.form-row, .field-teacher, div').first();
            var $studentField = $('#id_student').closest('.form-row, .field-student, div').first();
            
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
        
        // Run on page load
        toggleProfileFields();
        
        // Run when type changes
        $('#id_user_type').on('change', toggleProfileFields);
    });
})(django.jQuery || jQuery);

