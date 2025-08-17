function  EMC_assert_string_value(input_value, valid_string_cell, is_case_sensitive)

    value_is_valid = false;
    if ~isa(valid_string_cell, 'cell')
        error('EMC_assert_string_value: input_string_cell is not a cell array');
    end

    for i = 1:length(valid_string_cell)
        if ~ischar(valid_string_cell{i})
            error('EMC_assert_string_value: valid_string_cell{%d} is not a string', i);
        end
        if (is_case_sensitive)
            if (strcmp(input_value, valid_string_cell{i}))
                value_is_valid = true;
                break;
            end
        else
            if (strcmpi(input_value, valid_string_cell{i}))
                value_is_valid = true;
                break;
            end
        end

    end
    if ~value_is_valid
        error('EMC_assert_string_value: (%s) input_value is not a valid string', input_value);
    end

end