% in this script fit a linear polynomial to a set of data points using the adamOptimizer class
% First, we will create some sample data points
% Sample data points
x = linspace(0, 10, 100)'; % 100 data points from 0 to 10
y_true = 2 * x + 3; % True linear relationship (y = 2x + 3)
noise = randn(size(x)); % Add some noise to the data
y = y_true + 1.5 * noise; % Noisy observations

% plot the data points
figure;
scatter(x, y, 'b.');
%show the figure
title('Sample Data Points');
xlabel('x');
ylabel('y');
grid on;

% Initialize parameters for the linear model (y = mx + b)
initial_parameters = [0; 0]; % Start with m=0, b=0 (slope and intercept)
% Create an instance of the adamOptimizer
optimizer = adamOptimizer(initial_parameters);

% Define the number of iterations for optimization
num_iterations = 10000;
loss = zeros(num_iterations, 1); % Preallocate loss array for optional debugging
num_complete_iterations = 0; % Initialize the number of complete iterations
% Perform the optimization
for i = 1:num_iterations
    % Compute the gradient of the loss
    [ gradient, loss_i ] = compute_gradient(x, y, optimizer.get_current_parameters);
    loss(i) = loss_i; % Store the loss for debugging purposes (optional)
    num_complete_iterations = num_complete_iterations + 1; % Increment the count of complete iterations
    % If iteration > 5 compare current loss to previous loss to check for convergence
    if i > 5 && abs(loss(i) - loss(i-1)) < 1e-6
        fprintf('Converged after %d iterations.\n', i);
        break; % Stop early if the loss has converged
    end
    % Update the optimizer with the computed gradient
    optimizer.update(gradient);
end 
% After optimization, retrieve the optimized parameters
optimized_parameters = optimizer.get_current_parameters;
% Display the optimized parameters
fprintf('Optimized parameters:\n');
fprintf('Slope (m): %.4f\n', optimized_parameters(1));
fprintf('Intercept (b): %.4f\n', optimized_parameters(2));
% Plot the results
figure;
scatter(x, y, 'b.', 'DisplayName', 'Data Points'); % Original data points
hold on;
% Plot the fitted line using the optimized parameters
y_pred = optimized_parameters(1) * x + optimized_parameters(2); % Compute the predicted y values
plot(x, y_pred, 'r-', 'LineWidth', 2, 'DisplayName', 'Fitted Line'); % Fitted line
title('Fitted Linear Model using Adam Optimizer');
xlabel('x');
ylabel('y');
legend('show');
% Show the figure
hold off;

% Trim the loss to the number of iterations completed (in case of early stopping)
% plot the loss over iterations (optional)
figure;
plot(1:num_complete_iterations, loss(1:num_complete_iterations), 'b-', 'LineWidth', 2);
title('Loss over Iterations');
xlabel('Iteration');
ylabel('Mean Squared Error (Loss)');
grid on;
% This script fits a linear model to the noisy data using the Adam optimizer
% and plots the fitted line along with the original data points. The loss is also plotted to show the convergence.


% Define a function to compute the gradient of the loss (mean squared error)
function [gradient, loss] = compute_gradient(x, y, parameters)
    % Extract parameters
    m = parameters(1);
    b = parameters(2);
    
    % Compute predictions
    y_pred = m * x + b;
    
    % Compute the error
    error = y_pred - y;

    % Compute the loss (mean squared error) if needed
    loss = mean(error .^ 2); % Mean Squared Error (optional, can be used for debugging)
    
    % Compute the gradient of the loss with respect to m and b
    grad_m = (2 / length(x)) * sum(error .* x);
    grad_b = (2 / length(x)) * sum(error);
    
    % Combine gradients into a single vector
    gradient = [grad_m; grad_b];
end


