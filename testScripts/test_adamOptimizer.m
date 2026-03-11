% test_adamOptimizer.m - Unit tests for the adamOptimizer class
%
% Tests cover:
% 1. Basic ADAM convergence on a quadratic objective
% 2. Per-parameter learning rates
% 3. Parameter bounds clamping
% 4. Score history and convergence detection
% 5. Parameter freezing/unfreezing

function test_adamOptimizer()
    fprintf('\n=== adamOptimizer Unit Tests ===\n\n');

    test_basic_quadratic_convergence();
    test_linear_regression();
    test_per_parameter_learning_rates();
    test_parameter_bounds();
    test_score_history_and_convergence();
    test_parameter_freezing();
    test_gradient_column_row_handling();

    fprintf('\n=== All tests passed ===\n');
end

function test_basic_quadratic_convergence()
    % Minimize f(x) = (x-3)^2 + (y+2)^2, minimum at [3, -2]
    fprintf('Test: basic quadratic convergence... ');

    opt = adamOptimizer([0; 0]);

    for i = 1:5000
        params = opt.get_current_parameters();
        grad = [2*(params(1) - 3); 2*(params(2) + 2)];
        opt.update(grad);
    end

    final = opt.get_current_parameters();
    assert(abs(final(1) - 3) < 0.01, 'x should converge to 3, got %f', final(1));
    assert(abs(final(2) + 2) < 0.01, 'y should converge to -2, got %f', final(2));
    fprintf('PASSED\n');
end

function test_linear_regression()
    % Fit y = 2x + 3 from noisy data
    fprintf('Test: linear regression convergence... ');

    rng(42); % Reproducible
    x = linspace(0, 10, 100)';
    y = 2*x + 3 + 0.5*randn(size(x));

    opt = adamOptimizer([0; 0]);

    for i = 1:10000
        params = opt.get_current_parameters();
        y_pred = params(1)*x + params(2);
        err = y_pred - y;
        grad = [(2/length(x))*sum(err.*x); (2/length(x))*sum(err)];
        opt.update(grad);
    end

    final = opt.get_current_parameters();
    assert(abs(final(1) - 2) < 0.1, 'Slope should be ~2, got %f', final(1));
    assert(abs(final(2) - 3) < 0.5, 'Intercept should be ~3, got %f', final(2));
    fprintf('PASSED\n');
end

function test_per_parameter_learning_rates()
    % Different learning rates for different parameters
    fprintf('Test: per-parameter learning rates... ');

    opt = adamOptimizer([0; 0]);
    % Parameter 1 gets 10x the learning rate
    opt.set_learning_rates([0.01; 0.001]);

    for i = 1:2000
        params = opt.get_current_parameters();
        grad = [2*(params(1) - 5); 2*(params(2) - 5)];
        opt.update(grad);
    end

    final = opt.get_current_parameters();
    % Both should converge but param 1 should converge faster
    assert(abs(final(1) - 5) < 0.1, 'x should converge to 5, got %f', final(1));
    assert(abs(final(2) - 5) < 0.1, 'y should converge to 5, got %f', final(2));

    % Verify error on mismatched sizes
    try
        opt.set_learning_rates([0.01; 0.001; 0.0001]);
        error('Should have thrown an error for mismatched sizes');
    catch ME
        assert(contains(ME.message, 'same length'), 'Wrong error message: %s', ME.message);
    end
    fprintf('PASSED\n');
end

function test_parameter_bounds()
    % Minimize f(x) = (x-10)^2 + (y+10)^2 with bounds [-5, 5]
    fprintf('Test: parameter bounds... ');

    opt = adamOptimizer([0; 0]);
    opt.set_bounds([-5; -5], [5; 5]);

    for i = 1:5000
        params = opt.get_current_parameters();
        grad = [2*(params(1) - 10); 2*(params(2) + 10)];
        opt.update(grad);
    end

    final = opt.get_current_parameters();
    % Should be clamped at bounds
    assert(abs(final(1) - 5) < 0.01, 'x should be clamped at 5, got %f', final(1));
    assert(abs(final(2) + 5) < 0.01, 'y should be clamped at -5, got %f', final(2));

    % Verify bounds set clamps immediately
    opt2 = adamOptimizer([100; -100]);
    opt2.set_bounds([-1; -1], [1; 1]);
    p = opt2.get_current_parameters();
    assert(p(1) == 1, 'Initial x should be clamped to 1');
    assert(p(2) == -1, 'Initial y should be clamped to -1');
    fprintf('PASSED\n');
end

function test_score_history_and_convergence()
    fprintf('Test: score history and convergence detection... ');

    opt = adamOptimizer([0]);

    % Not enough history - should not be converged
    opt.add_score(1.0);
    opt.add_score(1.1);
    assert(~opt.has_converged(3, 0.001), 'Should not be converged with only 2 scores');

    % Add converging scores
    opt.add_score(1.1001);
    opt.add_score(1.1002);
    assert(opt.has_converged(3, 0.001), 'Should be converged with plateau scores');

    % Verify history retrieval
    h = opt.get_score_history();
    assert(length(h) == 4, 'Should have 4 scores in history');
    assert(h(1) == 1.0, 'First score should be 1.0');
    fprintf('PASSED\n');
end

function test_parameter_freezing()
    % Freeze one parameter, verify it doesn't change
    fprintf('Test: parameter freezing/unfreezing... ');

    opt = adamOptimizer([0; 0]);
    opt.freeze_parameters(2); % Freeze second parameter

    for i = 1:1000
        params = opt.get_current_parameters();
        grad = [2*(params(1) - 5); 2*(params(2) - 5)];
        opt.update(grad);
    end

    final = opt.get_current_parameters();
    assert(abs(final(2)) < 1e-10, 'Frozen parameter should remain at 0, got %f', final(2));
    assert(abs(final(1) - 5) < 1.0, 'Unfrozen parameter should move toward 5, got %f', final(1));

    % Unfreeze and verify it can now move
    opt.unfreeze_parameters(2, 0.001);
    for i = 1:5000
        params = opt.get_current_parameters();
        grad = [2*(params(1) - 5); 2*(params(2) - 5)];
        opt.update(grad);
    end

    final2 = opt.get_current_parameters();
    assert(abs(final2(2) - 5) < 1.0, 'Unfrozen parameter should move toward 5, got %f', final2(2));
    fprintf('PASSED\n');
end

function test_gradient_column_row_handling()
    % Verify that row gradients are handled correctly
    fprintf('Test: gradient column/row vector handling... ');

    opt = adamOptimizer([0; 0; 0]);

    % Pass gradient as row vector - should work
    opt.update([1, 2, 3]);
    p1 = opt.get_current_parameters();

    opt2 = adamOptimizer([0; 0; 0]);
    opt2.update([1; 2; 3]);
    p2 = opt2.get_current_parameters();

    assert(max(abs(p1 - p2)) < 1e-15, 'Row and column gradients should give same result');
    fprintf('PASSED\n');
end
