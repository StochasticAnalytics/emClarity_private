classdef adamOptimizer < handle

    properties (Access = private)
        alpha = 0.001; % Default scalar learning rate
        beta1 = 0.9;   % Exponential decay rate for the first moment estimates
        beta2 = 0.999; % Exponential decay rate for the second moment estimates
        epsilon = 1e-8; % Small value to prevent division by zero
        use_amsgrad = false; % AMSGrad: use max of past v_hat to ensure convergence (Reddi et al., 2018)
        lr_decay_power = 0; % Learning rate decay: lr_t = lr / t^decay_power. 0 = no decay.
        v_hat_max; % Running maximum of bias-corrected second moment (AMSGrad)
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
            obj.v_hat_max = zeros(length(initial_parameters), 1);
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

            % AMSGrad: use running max of v_hat to ensure non-increasing
            % effective learning rate, which guarantees convergence on
            % convex problems (Reddi et al., 2018)
            if obj.use_amsgrad
                obj.v_hat_max = max(obj.v_hat_max, v_hat);
                v_hat = obj.v_hat_max;
            end

            % Use per-parameter learning rates if set, otherwise scalar alpha
            if ~isempty(obj.learning_rates)
                lr = obj.learning_rates;
            else
                lr = obj.alpha;
            end

            % Apply learning rate decay: lr_t = lr / t^decay_power
            % At t=1 (first iteration) this has no effect; decays from t=2 onward.
            if obj.lr_decay_power > 0
                lr = lr / obj.t^obj.lr_decay_power;
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

        function lr = get_learning_rates(obj)
            % Get current per-parameter learning rates.
            % Returns the per-parameter vector if set, otherwise alpha * ones.
            if ~isempty(obj.learning_rates)
                lr = obj.learning_rates;
            else
                lr = obj.alpha * ones(length(obj.current_parameters), 1);
            end
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

        function scale_learning_rates(obj, factor)
            % Multiply all learning rates by a scalar factor.
            obj.learning_rates = obj.learning_rates * factor;
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

        function set_alpha(obj, alpha)
            % Set base learning rate (default: 0.001).
            % ADAM normalizes each step to ~alpha regardless of gradient
            % magnitude, so alpha should be tuned to the expected parameter
            % scale, not the gradient scale.
            obj.alpha = alpha;
        end

        function auto_scale_learning_rate(obj, expected_range, n_iterations, safety_factor)
            % Automatically set learning rate(s) based on expected parameter range.
            %
            % ADAM normalizes each step to approximately alpha, independent of
            % gradient magnitude. With lr_decay_power p, the total distance
            % ADAM can travel in N steps is:
            %
            %   total_travel = alpha * sum_{t=1}^{N} 1/t^p
            %
            % For p=0 (no decay): total = alpha * N
            % For p=0.5:          total ≈ alpha * 2*sqrt(N)
            % For general p<1:    total ≈ alpha * N^(1-p) / (1-p)
            %
            % This method computes alpha so that total_travel = safety_factor * expected_range,
            % ensuring the optimizer has sufficient step budget to reach the target.
            %
            % If expected_range is a vector, per-parameter learning rates are set
            % proportional to each dimension's range.
            %
            % Inputs:
            %   expected_range  - scalar or vector: max distance each parameter
            %                     might travel (e.g., upper_bound - lower_bound,
            %                     or a conservative estimate of |target - initial|)
            %   n_iterations    - planned number of update steps
            %   safety_factor   - multiplier on range (default: 5). Higher values
            %                     give more step budget (faster approach, slower
            %                     fine-tuning). 3-10 is typical.

            if nargin < 4 || isempty(safety_factor)
                safety_factor = 5;
            end

            expected_range = expected_range(:);
            n = length(obj.current_parameters);

            % Compute total step budget multiplier for the current decay schedule
            p = obj.lr_decay_power;
            if p == 0
                step_sum = n_iterations;
            elseif p < 1
                % Integral approximation: sum ≈ N^(1-p) / (1-p)
                step_sum = n_iterations^(1 - p) / (1 - p);
            else
                % p >= 1: harmonic series or slower, sum ≈ ln(N) for p=1
                step_sum = log(n_iterations) + 0.5772; % Euler-Mascheroni
            end

            if isscalar(expected_range)
                % Uniform range: set scalar alpha
                obj.alpha = safety_factor * expected_range / step_sum;
            else
                % Per-parameter ranges: set per-parameter learning rates
                if length(expected_range) ~= n
                    error('expected_range vector must have %d elements (one per parameter)', n);
                end
                obj.learning_rates = safety_factor * expected_range / step_sum;
            end
        end

        function set_amsgrad(obj, enabled)
            % Enable/disable AMSGrad (default: disabled).
            % AMSGrad uses max of past bias-corrected second moments to
            % ensure convergence on convex problems (Reddi et al., 2018).
            obj.use_amsgrad = enabled;
        end

        function set_lr_decay_power(obj, power)
            % Set learning rate decay power: lr_t = lr / t^decay_power.
            % power=0 means no decay (default). power=0.5 gives 1/sqrt(t) decay.
            % Decay breaks ADAM's limit cycles on convex problems by ensuring
            % the step size vanishes, guaranteeing convergence.
            obj.lr_decay_power = power;
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
