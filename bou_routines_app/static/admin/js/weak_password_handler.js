(function($) {
    'use strict';
    
    console.log('Weak password handler script loaded');
    
    // Function to check for password errors
    function hasPasswordErrors() {
        var password1Field = $('#id_password1');
        var password2Field = $('#id_password2');
        
        // Check for error messages near password fields
        var password1Row = password1Field.closest('.form-row, .form-group, tr, .field-password1');
        var password2Row = password2Field.closest('.form-row, .form-group, tr, .field-password2');
        
        // Look for errorlist elements
        var password1Errors = password1Row.find('.errorlist li, .errorlist');
        var password2Errors = password2Row.find('.errorlist li, .errorlist');
        
        // Also check for general error messages
        var generalErrors = $('.errornote, .errorlist li');
        
        // Check for password-related error messages anywhere on the page
        var hasPasswordError = false;
        
        // Check password field errors
        if (password1Errors.length > 0 || password2Errors.length > 0) {
            hasPasswordError = true;
        }
        
        // Check general errors for password-related text
        if (!hasPasswordError && generalErrors.length > 0) {
            generalErrors.each(function() {
                var errorText = $(this).text().toLowerCase();
                if (errorText.indexOf('password') !== -1 || 
                    errorText.indexOf('too similar') !== -1 ||
                    errorText.indexOf('similar to') !== -1 ||
                    errorText.indexOf('too short') !== -1 ||
                    errorText.indexOf('at least') !== -1 ||
                    errorText.indexOf('common') !== -1 ||
                    errorText.indexOf('commonly used') !== -1 ||
                    errorText.indexOf('numeric') !== -1 ||
                    errorText.indexOf('entirely numeric') !== -1 ||
                    errorText.indexOf('first name') !== -1 ||
                    errorText.indexOf('last name') !== -1 ||
                    errorText.indexOf('username') !== -1) {
                    hasPasswordError = true;
                    return false;
                }
            });
        }
        
        // Also check if password field has error class
        if (!hasPasswordError) {
            if (password1Field.hasClass('error') || password2Field.hasClass('error')) {
                hasPasswordError = true;
            }
        }
        
        return hasPasswordError;
    }
    
    function initPasswordHandler() {
        // Handle password validation errors and show confirmation popup
        var passwordForm = $('form#user_form, form[action*="password"], form');
        
        console.log('Password form found:', passwordForm.length);
        
        if (passwordForm.length === 0) {
            console.log('No password form found');
            return;
        }
        
        var password1Field = $('#id_password1');
        var password2Field = $('#id_password2');
        var allowWeakCheckbox = $('#id_allow_weak_password');
        
        // If checkbox doesn't exist, add it dynamically
        if (allowWeakCheckbox.length === 0 && password1Field.length) {
            var checkboxHtml = '<div class="form-row">' +
                '<div>' +
                '<label for="id_allow_weak_password">' +
                '<input type="checkbox" name="allow_weak_password" id="id_allow_weak_password"> ' +
                'Allow weak password anyway' +
                '</label>' +
                '<p class="help">Check this box to set a weak password despite validation warnings.</p>' +
                '</div>' +
                '</div>';
            
            // Try multiple insertion points
            var insertPoint = password2Field.closest('.form-row, .form-group, tr, .field-password2');
            if (insertPoint.length === 0) {
                insertPoint = password1Field.closest('.form-row, .form-group, tr, .field-password1');
            }
            if (insertPoint.length > 0) {
                insertPoint.after(checkboxHtml);
            } else {
                // Fallback: insert after password2 field directly
                password2Field.after(checkboxHtml);
            }
            allowWeakCheckbox = $('#id_allow_weak_password');
        }
        
        // Show popup immediately if errors exist on page load
        var hasErrors = hasPasswordErrors();
        console.log('Has password errors:', hasErrors);
        console.log('Checkbox exists:', allowWeakCheckbox.length > 0);
        console.log('Checkbox checked:', allowWeakCheckbox.length > 0 ? allowWeakCheckbox.is(':checked') : 'N/A');
        
        if (hasErrors) {
            // Get the first error message
            var errorText = '';
            var firstError = $('.errorlist li, .errornote').first();
            if (firstError.length > 0) {
                errorText = firstError.text();
            }
            
            var confirmMessage = 'The password does not meet the security requirements.\n\n';
            if (errorText) {
                confirmMessage += 'Error: ' + errorText + '\n\n';
            }
            confirmMessage += 'Do you want to set this weak password anyway?\n\n' +
                'This is not recommended for security reasons.';
            
            console.log('Showing password confirmation popup');
            if (confirm(confirmMessage)) {
                // User confirmed
                // Ensure checkbox exists and is checked
                if (allowWeakCheckbox.length === 0) {
                    // Create checkbox if it doesn't exist
                    var checkboxHtml = '<input type="hidden" name="allow_weak_password" id="id_allow_weak_password" value="on">';
                    passwordForm.append(checkboxHtml);
                    allowWeakCheckbox = $('#id_allow_weak_password');
                }
                allowWeakCheckbox.prop('checked', true);
                if (allowWeakCheckbox.is('input[type="hidden"]')) {
                    allowWeakCheckbox.val('on');
                }
                console.log('Checkbox checked, submitting form');
                // Auto-submit the form
                passwordForm.submit();
                return;
            }
        }
        
        // When form is submitted, check if user wants to proceed
        passwordForm.on('submit', function(e) {
            // Only intercept if checkbox is not checked and there are errors
            if (!allowWeakCheckbox.is(':checked') && hasPasswordErrors()) {
                e.preventDefault();
                
                // Get the first error message
                var errorText = '';
                var firstError = $('.errorlist li, .errornote').first();
                if (firstError.length > 0) {
                    errorText = firstError.text();
                }
                
                var confirmMessage = 'The password does not meet the security requirements.\n\n';
                if (errorText) {
                    confirmMessage += 'Error: ' + errorText + '\n\n';
                }
                confirmMessage += 'Do you want to set this weak password anyway?\n\n' +
                    'This is not recommended for security reasons.';
                
                if (confirm(confirmMessage)) {
                    // User confirmed, check the checkbox and resubmit
                    allowWeakCheckbox.prop('checked', true);
                    passwordForm.off('submit').submit();
                }
                // If user cancels, form submission is prevented
                return false;
            }
        });
    }
    
    // Run on document ready
    $(document).ready(function() {
        initPasswordHandler();
    });
    
    // Also run after a short delay to catch dynamically loaded content
    setTimeout(function() {
        initPasswordHandler();
    }, 500);
})(django.jQuery);
