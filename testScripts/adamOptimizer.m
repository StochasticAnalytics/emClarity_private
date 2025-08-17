classdef adamOptimizer < handle

    properties (Access = private)
        alpha = 0.001; % Learning rate
        beta1 = 0.9;   % Exponential decay rate for the first moment estimates
        beta2 = 0.999; % Exponential decay rate for the second moment estimates
        epsilon = 1e-8; % Small value to prevent division by zero
        m; % First moment vector
        v; % Second moment vector
        t = 0; % Time step
        initial_parameters = [];
        current_parameters = []; % This can be used to store the current parameters if needed
    end

    methods

        function obj = adamOptimizer(initial_parameters)
            % Check that the initial parameters are >= 1 and one dimensional
            if nargin < 1 || isempty(initial_parameters) || ~isvector(initial_parameters)
                error('Initial parameters must be a non-empty vector.');
            end
            if length(initial_parameters) < 1
                error('Initial parameters must have at least one element.');
            end
            % Constructor to initialize the first and second moment vectors
            obj.m = zeros(length(initial_parameters), 1); % Initialize first moment vector
            obj.v = zeros(length(initial_parameters), 1); % Initialize second moment vector

            % Store the initial parameters
            obj.initial_parameters = initial_parameters(:); % Ensure it's a column vector
            obj.current_parameters = obj.initial_parameters; % Initialize current parameters
        end

        function update(obj, gradient)
            % Increment time step
            obj.t = obj.t + 1;

            % Update biased first moment estimate
            obj.m = obj.beta1 * obj.m + (1 - obj.beta1) .* gradient;

            % Update biased second raw moment estimate
            obj.v = obj.beta2 * obj.v + (1 - obj.beta2) .* (gradient .^ 2);

            % Compute bias-corrected first moment estimate
            m_hat = obj.m / (1 - obj.beta1 .^ obj.t);

            % Compute bias-corrected second raw moment estimate
            v_hat = obj.v / (1 - obj.beta2 .^ obj.t);

            % Update parameters using the Adam update rule
            obj.current_parameters = obj.current_parameters - obj.alpha .* m_hat ./ (sqrt(v_hat) + obj.epsilon);
            
            % Apply the parameter update (this would be applied to the model parameters in practice)
        end

        function params = get_current_parameters(obj)
            % Getter method to retrieve the current parameters
            params = obj.current_parameters; 
        end

        
    end

end