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
        // Callback after dropdown is shown
        onShow: function() {
            enhance_tags_dropdown_aria($(this));
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
            
            // Update ARIA attributes
            enhance_tags_dropdown_aria($(this));
            
            // Announce to screen readers (just the tag text, no prefix)
            if (!$('#tags-announcement').length) {
                $('body').append('<div id="tags-announcement" role="status" aria-live="polite" aria-atomic="true" style="position: absolute; left: -10000px; width: 1px; height: 1px; overflow: hidden;"></div>');
            }
            $('#tags-announcement').text(text);
        }
    });
    
    // Ensure dropdown has proper ARIA attributes
    $('.tags').each(function() {
        var $dropdown = $(this);
        $dropdown.attr('role', 'combobox');
        $dropdown.attr('aria-haspopup', 'listbox');
        if ($dropdown.attr('multiple')) {
            $dropdown.attr('aria-multiselectable', 'true');
        }
    });
    $('.tags .dropdown.icon').attr('aria-hidden', 'true');
    
    // Initial ARIA enhancement
    $('.tags').each(function() {
        enhance_tags_dropdown_aria($(this));
    });
    
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

// Enhance tags dropdown with proper ARIA attributes
function enhance_tags_dropdown_aria($dropdown) {
    // Find the menu element
    var $menu = $dropdown.children('.menu');
    if ($menu.length > 0) {
        // Check if menu is visible
        var isVisible = $menu.hasClass('visible') || $menu.hasClass('active');
        $dropdown.attr('aria-expanded', isVisible ? 'true' : 'false');
        
        // Ensure menu has proper ID
        if (!$menu.attr('id')) {
            var dropdownId = $dropdown.attr('id') || 'tags-dropdown-' + Math.random().toString(36).substr(2, 9);
            $dropdown.attr('id', dropdownId);
            $menu.attr('id', dropdownId + '-menu');
        }
        
        // Set role on menu
        $menu.attr('role', 'listbox');
        
        // Link dropdown to its menu
        $dropdown.attr('aria-controls', $menu.attr('id'));
        
        // Enhance menu items
        $menu.find('.item').each(function(index) {
            var $item = $(this);
            $item.attr('role', 'option');
            $item.attr('tabindex', '-1');
            
            // Mark selected items
            if ($item.hasClass('selected') || $item.hasClass('active')) {
                $item.attr('aria-selected', 'true');
            } else {
                $item.attr('aria-selected', 'false');
            }
        });
    }
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
            },
            // Callback after dropdown is initialized and shown
            onShow: function() {
                enhance_dropdown_aria($dropdown);
            },
            onChange: function(value, text, $selectedItem) {
                // Update ARIA attributes when selection changes
                enhance_dropdown_aria($dropdown);
                
                // Announce selection to screen readers (just the option text, no prefix)
                if (!$('#dropdown-announcement').length) {
                    $('body').append('<div id="dropdown-announcement" role="status" aria-live="polite" aria-atomic="true" style="position: absolute; left: -10000px; width: 1px; height: 1px; overflow: hidden;"></div>');
                }
                $('#dropdown-announcement').text(text);
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
        
        // Initial ARIA enhancement
        enhance_dropdown_aria($dropdown);
    });
}

// Enhance Semantic UI dropdown with proper ARIA attributes for screen readers
function enhance_dropdown_aria($dropdown) {
    // Ensure the dropdown element has proper ID
    if (!$dropdown.attr('id')) {
        var randomId = 'dropdown-' + Math.random().toString(36).substr(2, 9);
        $dropdown.attr('id', randomId);
    }
    
    // Set role and ARIA attributes on the main dropdown container
    $dropdown.attr('role', 'combobox');
    $dropdown.attr('aria-haspopup', 'listbox');
    
    // Find the menu element
    var $menu = $dropdown.children('.menu');
    if ($menu.length > 0) {
        // Check if menu is visible
        var isVisible = $menu.hasClass('visible') || $menu.hasClass('active');
        $dropdown.attr('aria-expanded', isVisible ? 'true' : 'false');
        
        // Ensure menu has proper ID
        if (!$menu.attr('id')) {
            $menu.attr('id', $dropdown.attr('id') + '-menu');
        }
        
        // Set role on menu
        $menu.attr('role', 'listbox');
        
        // Link dropdown to its menu
        $dropdown.attr('aria-controls', $menu.attr('id'));
        
        // Enhance menu items
        $menu.find('.item').each(function(index) {
            var $item = $(this);
            $item.attr('role', 'option');
            $item.attr('tabindex', '-1');
            
            // Mark selected items
            if ($item.hasClass('selected') || $item.hasClass('active')) {
                $item.attr('aria-selected', 'true');
            } else {
                $item.attr('aria-selected', 'false');
            }
        });
    }
    
    // Update aria-label to reflect current selection without repetition
    var currentText = $dropdown.find('.text').text().trim();
    var placeholder = $dropdown.data('placeholder') || '';
    
    // Only update if there's a valid selection (not placeholder text)
    if (currentText && currentText !== placeholder && currentText !== 'Select post type' && currentText !== '') {
        // Use a clean aria-label with just the current selection
        $dropdown.attr('aria-label', currentText);
    } else {
        // Reset to base label when no selection
        var baseLabel = $dropdown.attr('data-base-label');
        if (!baseLabel) {
            // Store the original aria-label on first run
            baseLabel = $dropdown.attr('aria-label') || 'Select option';
            $dropdown.attr('data-base-label', baseLabel);
        }
        $dropdown.attr('aria-label', baseLabel);
    }
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
