function [class_idx, class_probability] = EMC_get_class_idx(val)

        EMC_assert_numeric(val, 1)
        if (val == -9999)
            class_idx = -9999;
            class_probability = 0.0;
        else
            class_idx = floor(val);
            class_probability = max(0, min(1, 1-(val - floor(val))));
        end

end