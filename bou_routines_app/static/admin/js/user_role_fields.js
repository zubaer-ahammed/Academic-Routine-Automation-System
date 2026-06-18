(function($) {
    $(document).ready(function() {
        function toggleProfileFields() {
            var userType = $('#id_user_type').val();
            $('.user-role-teacher-row').toggle(userType === 'teacher');
            $('.user-role-student-row').toggle(userType === 'student');
        }

        var $userType = $('#id_user_type');
        if ($userType.length) {
            toggleProfileFields();
            $userType.on('change', toggleProfileFields);
        }
    });
})(django.jQuery || jQuery);
