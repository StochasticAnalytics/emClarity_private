classdef adamOptimizer < handle

    properties (Access = private)
        alpha = 0.001; % Default scalar learning rate
        beta1 = 0.9;   % Exponential decay rate for the first moment estimates
        beta2 = 0.999; % Exponential decay rate for the second moment estimates
        epsilon = 1e-8; % Small value to prevent division by zero
        m; % First moment vector
        v; % Second moment vector
        t = 0; % Time step
        initial_parameters = [];
        current_parameters = [];
        learning_rates = [];   % Per-parameter learning rate vector
        lower_bounds = [];     % Parameter lower bounds
        upper_bounds = [];     % Parameter upper bounds
        score_history = [];    % Track objective values per iteration
    end

    methods

        function obj = adamOptimizer(initial_parameters)
            if nargin < 1 || isempty(initial_parameters) || ~isvector(initial_parameters)
                error('Initial parameters must be a non-empty vector.');
            end
            if length(initial_parameters) < 1
                error('Initial parameters must have at least one element.');
            end
            obj.m = zeros(length(initial_parameters), 1);
            obj.v = zeros(length(initial_parameters), 1);
            obj.initial_parameters = initial_parameters(:);
            obj.current_parameters = obj.initial_parameters;
        end

        function update(obj, gradient)
            gradient = gradient(:); % Ensure column vector

            obj.t = obj.t + 1;

            % Update biased first moment estimate
            obj.m = obj.beta1 * obj.m + (1 - obj.beta1) .* gradient;

            % Update biased second raw moment estimate
            obj.v = obj.beta2 * obj.v + (1 - obj.beta2) .* (gradient .^ 2);

            % Compute bias-corrected first moment estimate
            m_hat = obj.m / (1 - obj.beta1 ^ obj.t);

            % Compute bias-corrected second raw moment estimate
            v_hat = obj.v / (1 - obj.beta2 ^ obj.t);

            % Use per-parameter learning rates if set, otherwise scalar alpha
            if ~isempty(obj.learning_rates)
                lr = obj.learning_rates;
            else
                lr = obj.alpha;
            end

            % Update parameters
            obj.current_parameters = obj.current_parameters - lr .* m_hat ./ (sqrt(v_hat) + obj.epsilon);

            % Clamp to bounds if set
            if ~isempty(obj.lower_bounds)
                obj.current_parameters = max(obj.current_parameters, obj.lower_bounds);
            end
            if ~isempty(obj.upper_bounds)
                obj.current_parameters = min(obj.current_parameters, obj.upper_bounds);
            end
        end

        function params = get_current_parameters(obj)
            params = obj.current_parameters;
        end

        function set_learning_rates(obj, lr)
            % Set per-parameter learning rates.
            % lr must be a vector with the same length as the parameter vector.
            lr = lr(:);
            if length(lr) ~= length(obj.current_parameters)
                error('Learning rate vector must have the same length as parameter vector (%d)', ...
                    length(obj.current_parameters));
            end
            obj.learning_rates = lr;
        end

        function set_bounds(obj, lb, ub)
            % Set parameter bounds. Use -inf/inf for unconstrained dimensions.
            lb = lb(:);
            ub = ub(:);
            n = length(obj.current_parameters);
            if length(lb) ~= n || length(ub) ~= n
                error('Bound vectors must have the same length as parameter vector (%d)', n);
            end
            obj.lower_bounds = lb;
            obj.upper_bounds = ub;
            % Clamp current parameters to bounds immediately
            obj.current_parameters = max(obj.current_parameters, obj.lower_bounds);
            obj.current_parameters = min(obj.current_parameters, obj.upper_bounds);
        end

        function add_score(obj, score)
            % Append a score value to the score history.
            obj.score_history(end+1) = score;
        end

        function converged = has_converged(obj, n_lookback, threshold)
            % Check convergence: true if the relative improvement over the
            % last n_lookback scores is below threshold.
            % Default: n_lookback=3, threshold=0.001 (0.1%)
            if nargin < 2 || isempty(n_lookback)
                n_lookback = 3;
            end
            if nargin < 3 || isempty(threshold)
                threshold = 0.001;
            end
            converged = false;
            if length(obj.score_history) < n_lookback + 1
                return;
            end
            recent = obj.score_history(end - n_lookback + 1:end);
            baseline = obj.score_history(end - n_lookback);
            if baseline == 0
                return;
            end
            max_change = max(abs(recent - baseline)) / abs(baseline);
            converged = max_change < threshold;
        end

        function history = get_score_history(obj)
            history = obj.score_history;
        end

        function step = get_timestep(obj)
            step = obj.t;
        end

        function freeze_parameters(obj, indices)
            % Freeze specific parameters by setting their learning rates to 0.
            % Requires learning_rates to be set first.
            if isempty(obj.learning_rates)
                obj.learning_rates = obj.alpha * ones(length(obj.current_parameters), 1);
            end
            obj.learning_rates(indices) = 0;
        end

        function unfreeze_parameters(obj, indices, lr_values)
            % Unfreeze specific parameters by restoring their learning rates.
            if isempty(obj.learning_rates)
                obj.learning_rates = obj.alpha * ones(length(obj.current_parameters), 1);
            end
            obj.learning_rates(indices) = lr_values(:);
        end

    end

end
