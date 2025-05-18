// Add this script to your page after including all the original scripts

$(document).ready(function() {
    // Reset and reinitialize all the timepickers
    $('.mdtimepicker').each(function() {
        // First properly destroy the timepicker if it exists
        if ($(this).data('mdtimepicker')) {
            $(this).mdtimepicker('destroy');
        }
        
        // Then initialize it properly
        $(this).mdtimepicker({
            format: 'hh:mm',
            theme: 'blue',
            hourPadding: true
        });
    });
    
    // Special handling for the lunch break time pickers
    $('#lunchBreakStart, #lunchBreakEnd').each(function() {
        // Make sure they are properly initialized
        if ($(this).data('mdtimepicker')) {
            $(this).mdtimepicker('destroy');
        }
        
        $(this).mdtimepicker({
            format: 'hh:mm',
            theme: 'blue',
            hourPadding: true
        });
    });
    
    // Re-attach event listeners to ensure they work
    $(document).on('mdtimepicker:close', '.mdtimepicker', function() {
        // If this is a course time input, check for overlaps
        if ($(this).hasClass('time-input')) {
            const row = $(this).closest('.course-row');
            if (typeof checkTimeOverlap === 'function') {
                checkTimeOverlap(row);
            }
        }
        
        // If this is a lunch break input, update the lunch break info
        if ($(this).attr('id') === 'lunchBreakStart' || $(this).attr('id') === 'lunchBreakEnd') {
            const startTime = $('#lunchBreakStart').val();
            const endTime = $('#lunchBreakEnd').val();
            
            if (startTime && endTime) {
                $('#lunchBreakInfo').text(`Lunch Break: ${startTime} - ${endTime}`).show();
                
                // Update the data attribute with new values
                $('#semester').data('lunch-break', {
                    start: startTime,
                    end: endTime
                });
                
                // Re-check all rows for overlaps if the function exists
                if (typeof checkTimeOverlap === 'function') {
                    $('.course-row').each(function() {
                        checkTimeOverlap($(this));
                    });
                }
            }
        }
    });
});
