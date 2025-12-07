(function($) {
    $(document).ready(function() {
        var isLabCheckbox = $('#id_is_lab');
        var isTheoryCheckbox = $('#id_is_theory');
        
        // Function to handle mutual exclusivity
        function handleMutualExclusivity(checkedCheckbox, otherCheckbox) {
            if (checkedCheckbox.is(':checked')) {
                otherCheckbox.prop('checked', false);
            }
        }
        
        // When is_lab is checked, uncheck is_theory
        isLabCheckbox.on('change', function() {
            if ($(this).is(':checked')) {
                isTheoryCheckbox.prop('checked', false);
            }
        });
        
        // When is_theory is checked, uncheck is_lab
        isTheoryCheckbox.on('change', function() {
            if ($(this).is(':checked')) {
                isLabCheckbox.prop('checked', false);
            }
        });
    });
})(django.jQuery);

