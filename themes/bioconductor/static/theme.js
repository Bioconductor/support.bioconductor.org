// Enhanced tags dropdown with accessibility support
function tags_dropdown() {
    $('.tags').dropdown({
        allowAdditions: true,
        forceSelection: false,
        // Make keyboard navigation work better
        keys: {
            delimiter: false,
            deleteKey: 8,
            leftArrow: 37,
            upArrow: 38,
            rightArrow: 39,
            downArrow: 40,
            enter: 13,
            escape: 27,
            tab: 9
        },
        // Get form field to add to
        onChange: function (value, text, $selectedItem) {
            // Get form field to add to
            var field = $(this).find("select").data("value");
            var tag_field = $('#{0}'.f(field));
            // Add selected tag to field
            // Set text instead of value
            value = $('<div/>').text(value).html();
            tag_field.val(value);
            
            // Announce to screen readers
            if (!$('#tags-announcement').length) {
                $('body').append('<div id="tags-announcement" role="status" aria-live="polite" aria-atomic="true" style="position: absolute; left: -10000px; width: 1px; height: 1px; overflow: hidden;"></div>');
            }
            $('#tags-announcement').text('Selected: ' + text);
        }
    });
    
    // Ensure dropdown has proper ARIA attributes
    $('.tags').attr('role', 'listbox');
    $('.tags[multiple]').attr('aria-multiselectable', 'true');
    $('.tags .dropdown.icon').attr('aria-hidden', 'true');
    
    $('.tags > input.search').keydown(function (event) {
        // Prevent submitting form when adding tag by pressing ENTER.
        var ek = event.keyCode || event.which;
        var value = $(this).val().trim();

        // Get a list of delimiters
        //var delimiters = $('#field-tags').data('delimiters').split(',');
        // console.log(ek===13);
        if (ek===13) {
            // Escape the text before settings value.
            value = $('<div/>').text(value).html();
            event.preventDefault();
            $(this).closest('.tags').dropdown('set selected', value);
            $(this).val('');
            return value
        }
    })
}

// Initialize all dropdowns with accessibility features
function init_accessible_dropdowns() {
    // Initialize all Semantic UI dropdowns with accessibility enhancements
    $('.ui.dropdown:not(.tags):not(.accessible-dropdown)').each(function() {
        var $dropdown = $(this);
        
        $dropdown.dropdown({
            // Preserve accessibility
            forceSelection: false,
            keys: {
                delimiter: false,
                deleteKey: 8,
                leftArrow: 37,
                upArrow: 38,
                rightArrow: 39,
                downArrow: 40,
                enter: 13,
                escape: 27,
                tab: 9
            }
        });
        
        // Ensure proper ARIA attributes
        if (!$dropdown.attr('aria-label')) {
            var label = $dropdown.closest('.field').find('label').text();
            if (label) {
                $dropdown.attr('aria-label', label);
            }
        }
        
        // Make dropdown icons decorative
        $dropdown.find('.dropdown.icon').attr('aria-hidden', 'true');
    });
}

$(document).ready(function () {
    // Initialize tags dropdown
    tags_dropdown();
    
    // Initialize all other dropdowns with accessibility
    init_accessible_dropdowns();
    
    function cancel_answers() {
        $('.answer-text').hide();
        $('.answer-text textarea').val('')
    }

    $('.show-answer').click(function () {
        $(".answer-text").show();
    });

    remove_trigger();

    $('body').keyup(function (event) {
        if (event.keyCode === 27) {
            // Cancel answer text area.
            cancel_answers()
        }
    });

    $('.answer-text .cancel').click(function () {
        cancel_answers()
    });

});
