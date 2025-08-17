% function [] = optimize_gmm_weights(starting_gmm, data_vector)

    starting_gmm = GMM;
    data_vector = orig_vector;
% Make sure the data vector size matches expected
if (size(data_vector, 2) ~= size(starting_gmm.mu, 2))
    error('Data vector size does not match GMM parameters');
end

n_batches = 4;

randomized_idx = randperm(size(data_vector,1));
bin_size = floor(1/n_batches * size(data_vector,1));

validation_idx = randomized_idx(1:bin_size);
test_idx = randomized_idx(bin_size+1:end);

n_epochs = 1;


n_cores = 16;
% try
%     EMC_parpool(n_cores);
% catch
%     delete(gcp('nocreate'));
%     pause(3)
%     EMC_parpool(n_cores);
% end

fprintf('Starting log likelihood: %f\n',starting_gmm.NegativeLogLikelihood);



optimizer = adamOptimizer(ones(starting_gmm.NumVariables,1));
current_gmm = starting_gmm;
for i_epoch = 1:n_epochs
    for i_batch = 1:n_batches
        if (i_batch < n_batches)
            batch_idx = test_idx((i_batch-1)*bin_size+1:i_batch*bin_size);
        else
            batch_idx = test_idx((i_batch-1)*bin_size+1:end);
        end


        
        weights = [0.9 .* optimizer.get_current_parameters()' ; ...
            1.1 .* optimizer.get_current_parameters()'];
        loss = cell(2,starting_gmm.NumVariables);


        starting_values = struct('mu',current_gmm.mu,'Sigma',current_gmm.Sigma,'ComponentProportion',current_gmm.PComponents);
        for i_weight = 1:starting_gmm.NumVariables
            for lowhigh = 1:2
                gm = gmdistribution(current_gmm.mu,current_gmm.Sigma, current_gmm.PComponents);
                fit_vector = data_vector(batch_idx,:);
                p1 = mahal(gm, fit_vector);
                fit_vector(:,i_weight) = fit_vector(:,i_weight) .* weights(lowhigh, i_weight);
                p2 =  mahal(gm, fit_vector);
                error('asdf')
                
                
                i_gmm = fitgmdist(fit_vector, ...
                    starting_gmm.NumComponents, ...
                    'Regularize', starting_gmm.RegularizationValue, ...
                    'Replicates', 1, ...
                    'CovarianceType', starting_gmm.CovarianceType, ... 
                    'SharedCovariance', starting_gmm.SharedCovariance, ... % covariance can vary between clusters
                    'Start', starting_values, ...
                    'Options', statset('UseParallel', 0, 'MaxIter', 1) ); % We just want to estimate the gradient, so only do one iteration 
                loss{lowhigh,i_weight} = i_gmm.NegativeLogLikelihood;
                fprintf('for i_weight %d and lowhisgh %d loss is %f\n', i_weight, lowhigh, i_gmm.NegativeLogLikelihood);
            end
        end

        loss_v = 0.* weights;
        for i_weight = 1:starting_gmm.NumVariables
            for lowhigh = 1:2
                loss_v(lowhigh, i_weight) = loss{lowhigh, i_weight};
            end
        end
        gradient = -diff(loss_v) ./ diff(weights);
        optimizer.update(gradient');

        optimizer.get_current_parameters'

            

    end % i_batch
    error('batch')
end
% Initialize an adam optimizer to fit the weights
% Loop over each epoch
    % Loop over each batch, probably also 20%
        % Calculate a finite difference gradient for each weight, timing could be problematic and will probably play into the batch size
        % Probably need something to handle removing values where weights are pushed to zero (or so far outsize the average weight)
        % Maybe this doesn't make a difference though if all 
            % Taking the existing mu/sigma and S = struct('mu',Mu,'Sigma',Sigma,'ComponentProportion',PComponents);

            % GMModel3 = fitgmdist(X,3,'Start',S);

            % Update the values with the adam optimizer

    % Calculate the score on the validation dataset


% end