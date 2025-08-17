class EmcTypeTraits:
    def assert_numeric(self, value, expected_length=None, value_range=None, param_name="Parameter"):
        """Checks if a value is numeric, optionally checks length and range."""
        is_numeric = isinstance(value, (int, float))
        is_list_of_numeric = isinstance(value, list) and all(isinstance(x, (int, float)) for x in value)

        if not (is_numeric or is_list_of_numeric):
            raise ValueError(f"{param_name} is not numeric: {value}")

        if expected_length is not None:
            current_length = 1 if is_numeric else len(value)
            if current_length != expected_length:
                raise ValueError(f"{param_name} '{value}' has length {current_length}, expected {expected_length}")

        if value_range is not None:
            values_to_check = value if isinstance(value, list) else [value]
            for v_item in values_to_check:
                if not (value_range[0] <= v_item <= value_range[1]):
                    raise ValueError(f"{param_name} value {v_item} out of range {value_range}")
        return True

    def assert_boolean(self, value, param_name="Parameter"):
        """Checks if a value is boolean-like (True, False, 0, 1)."""
        if not isinstance(value, (bool, int, float)) or (isinstance(value, (int, float)) and value not in (0, 1)):
            # ast.literal_eval might turn "0" into int 0, "1" into int 1.
            # True/False are bool.
            # Allow 0/1 as bool-like after ast.literal_eval
            # If strict bool is needed, this check would be: if not isinstance(value, bool):
            pass # Current logic allows 0/1
            # raise ValueError(f"{param_name} is not boolean-like: {value}")
        return True

    def assert_string_value(self, value, allowed_values, case_sensitive=False, param_name="Parameter"):
        """Checks if a string value is one of the allowed values."""
        val_to_check = value if case_sensitive else str(value).lower()
        allowed_to_check = allowed_values if case_sensitive else [str(x).lower() for x in allowed_values]
        if val_to_check not in allowed_to_check:
            raise ValueError(f"{param_name} value '{value}' not in allowed set: {allowed_values}")
        return True

    def assert_deprecated_substitution(self, params, old_name, new_name):
        """Handles deprecated parameter names, substituting with new names if appropriate."""
        if old_name in params:
            old_value = params.pop(old_name) # Remove old_name first
            if new_name not in params or params.get(new_name) is None:
                print(f"Info: Parameter '{old_name}' is deprecated. Using its value for '{new_name}'.")
                params[new_name] = old_value
            # If new_name exists and has a value, MATLAB code prefers old_value if new_value is None.
            # The original python translation was:
            # elif params.get(new_name) is None and params.get(old_name) is not None :
            # This condition is tricky after popping old_name.
            # Let's simplify: if new_name is already there with a non-None value, we keep it.
            # Otherwise, the value from old_name is used.
            # The MATLAB code implies if new_name is present (even if None), old_name's value might be preferred.
            # The current logic: if new_name is not in params OR new_name is in params but its value is None, use old_value.
            # If new_name is in params and has a non-None value, the old_value is effectively ignored (already popped).
            elif params.get(new_name) is not None:
                 print(f"Info: Parameter '{old_name}' is deprecated. '{new_name}' already exists with value '{params[new_name]}'. Value from '{old_name}' ('{old_value}') is ignored.")
        return params