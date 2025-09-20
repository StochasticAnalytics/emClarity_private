function [] = BH_plotMultiCycleFSC(SUBTOMO_META_NAME, CYCLE_LIST, REFERENCE_LIST)
%BH_plotMultiCycleFSC Plot FSC curves from multiple cycles on the same graph
%
%   BH_plotMultiCycleFSC(SUBTOMO_META_NAME, CYCLE_LIST, REFERENCE_LIST)
%
%   Plots Fourier Shell Correlation curves from multiple cycles for comparison,
%   with resolution metrics calculated for the most recent cycle.
%
%   Inputs:
%       SUBTOMO_META_NAME - Name of the subTomoMeta file (without .mat extension)
%       CYCLE_LIST - String with cycle numbers in emClarity format:
%                    - Single number: '16'
%                    - Array: '[10,12,14,16]' or '10,12,14,16'
%       REFERENCE_LIST - String with reference numbers in emClarity format:
%                       - Single number: '1'
%                       - Array: '[1,2]' or '1,2'
%                       Optional, defaults to '1'
%
%   Example:
%       BH_plotMultiCycleFSC('project1', '[10,12,14,16]', '1')
%       BH_plotMultiCycleFSC('project1', '10,12,14,16', '1')
%       BH_plotMultiCycleFSC('project1', '16', '[1,2]')
%
%   Output:
%       Saves PDF plot to FSC/multiCycle_cycles[X]_refs[Y]_[metaName].pdf

if nargin < 2
    error('Usage: BH_plotMultiCycleFSC(SUBTOMO_META_NAME, CYCLE_LIST, [REFERENCE_LIST])');
end

if nargin < 3
    REFERENCE_LIST = '1';
end

% Parse cycle list using standard EMC conversion
cycles = EMC_str2double(CYCLE_LIST);
if isscalar(cycles)
    cycles = [cycles]; % Ensure it's always an array for consistency
end

% Parse reference list using standard EMC conversion
references = EMC_str2double(REFERENCE_LIST);
if isscalar(references)
    references = [references]; % Ensure it's always an array for consistency
end

% Sort cycles to ensure highest is last
cycles = sort(cycles);
highestCycle = cycles(end);

% Load subTomoMeta
try
    load(sprintf('%s.mat', SUBTOMO_META_NAME), 'subTomoMeta');
catch
    error('Could not load %s.mat', SUBTOMO_META_NAME);
end

% Create output directory if needed
if ~exist('FSC', 'dir')
    mkdir('FSC');
end

% Set up figure (wider to accommodate legend)
fig = figure('Visible', 'off'); % 'Position', [100, 100, 1100*length(references), 600]);

% Color scheme: dark to light blue, purple, green progression
nCycles = length(cycles);
colors = zeros(nCycles, 3);

% Define color progression: blue → purple → green
for i = 1:nCycles
    progress = (i-1) / max(nCycles-1, 1);

    if progress <= 0.33
        % Dark to light blue
        local_progress = progress / 0.33;
        colors(i,:) = [0.1, 0.2 + 0.4*local_progress, 0.4 + 0.4*local_progress];
    elseif progress <= 0.67
        % Dark to light purple
        local_progress = (progress - 0.33) / 0.34;
        colors(i,:) = [0.3 + 0.4*local_progress, 0.1, 0.4 + 0.4*local_progress];
    else
        % Dark to light green
        local_progress = (progress - 0.67) / 0.33;
        colors(i,:) = [0.1, 0.3 + 0.4*local_progress, 0.2 + 0.3*local_progress];
    end
end

% Process each reference
for refIdx = 1:length(references)
    iRef = references(refIdx);

    if length(references) > 1
        subplot(1, length(references), refIdx);
    end

    hold on;
    legendEntries = {};

    % Variables to store data from highest cycle for metrics
    highestCycleFSC = [];
    highestCycleOsX = [];
    pixelSize = [];
    nParticles = 0;

    % Plot FSC curves for each cycle
    for cycIdx = 1:nCycles
        iCycle = cycles(cycIdx);
        cycleNumber = sprintf('cycle%0.3d', iCycle);

        % Check if cycle exists
        if ~isfield(subTomoMeta, cycleNumber)
            warning('Cycle %s not found in subTomoMeta, skipping', cycleNumber);
            continue;
        end

        % Check if FSC data exists for this cycle
        if ~isfield(subTomoMeta.(cycleNumber), 'fitFSC')
            warning('No FSC data found for %s, skipping', cycleNumber);
            continue;
        end

        % Construct the field name for this reference (matching BH_fscGold_class naming)
        refField = sprintf('Ref%d', iRef);

        % Check if this reference exists
        if ~isfield(subTomoMeta.(cycleNumber).fitFSC, refField)
            % Try alternative naming conventions
            refField = sprintf('STD%d', iRef);
            if ~isfield(subTomoMeta.(cycleNumber).fitFSC, refField)
                refField = sprintf('Cls%d', iRef);
                if ~isfield(subTomoMeta.(cycleNumber).fitFSC, refField)
                    warning('No FSC data found for reference %d in %s, skipping', iRef, cycleNumber);
                    continue;
                end
            end
        end

        % Extract FSC data
        fscData = subTomoMeta.(cycleNumber).fitFSC.(refField);

        % fscData format: {shellsFreq, shellsFSC, {cRef,cRefAli,mtf}, osX, ...}
        shellsFreq = fscData{1};
        shellsFSC = fscData{2};
        osX = fscData{4};

        % Get sampling rate if available (for pixel size conversion)
        if length(fscData) >= 10
            samplingRate = fscData{10};
        else
            samplingRate = 1; % Default if not stored
        end

        % Fit spline to FSC data (using first column if multiple)
        if size(shellsFreq, 2) > 1
            shellsFreq = shellsFreq(:,1);
            shellsFSC = shellsFSC(:,1);
        end

        fitFSC = csape(shellsFreq, shellsFSC, 'variational');
        fscCurve = fnval(fitFSC, osX);

        % Plot FSC curve
        plot(osX, fscCurve, 'LineWidth', 1.5, 'Color', colors(cycIdx,:));
        legendEntries{end+1} = sprintf('Cycle %d', iCycle);

        % Store data from highest cycle for metrics
        if iCycle == highestCycle
            highestCycleFSC = fitFSC;
            highestCycleOsX = osX;

            % Try to get pixel size from metadata
            if isfield(subTomoMeta, 'pixelSize')
                pixelSize = subTomoMeta.pixelSize * samplingRate;
            elseif length(fscData) >= 10
                % Estimate from osX range and sampling
                pixelSize = 1.0; % Default to 1.0 if not found
            else
                pixelSize = 1.0;
            end

            % Try to get particle count for one-bit/half-bit calculation
            if isfield(subTomoMeta.(cycleNumber), 'nParticles')
                nParticles = subTomoMeta.(cycleNumber).nParticles;
            else
                % Estimate from geometry if available
                nParticles = 1000; % Default estimate
            end
        end
    end

    % Add threshold lines (only if we have data)
    if ~isempty(highestCycleOsX)
        plot(highestCycleOsX, 0.*highestCycleOsX, 'k-', 'LineWidth', 0.5);
        plot(highestCycleOsX, 0.*highestCycleOsX + 0.143, 'k--', 'LineWidth', 0.5);
        plot(highestCycleOsX, 0.*highestCycleOsX + 0.5, 'k--', 'LineWidth', 0.5);
    end

    % Calculate and plot one-bit and half-bit criteria for highest cycle
    if ~isempty(highestCycleFSC)
        % Calculate effective number of particles
        nEffective = sqrt(2 * nParticles);

        % One-bit criterion
        oneBIT = (0.5 + 2.4142./sqrt(nEffective)) ./ ...
                 (1 + 2.4142./sqrt(nEffective));

        % Half-bit criterion
        halfBIT = (0.207 + 1.9102./sqrt(nEffective)) ./ ...
                  (1 + 1.9102./sqrt(nEffective));

        % Plot criteria curves
        plot(highestCycleOsX, oneBIT, 'c-', 'LineWidth', 1);
        plot(highestCycleOsX, halfBIT, 'b-', 'LineWidth', 1);

        legendEntries{end+1} = 'One-bit';
        legendEntries{end+1} = 'Half-bit';

        % Find resolution values
        fscVals = fnval(highestCycleFSC, highestCycleOsX);

        % Find 0.5 crossing
        idx05 = find(fscVals < 0.5 & highestCycleOsX > 1/100, 1, 'first');
        if ~isempty(idx05)
            f05 = highestCycleOsX(idx05);
            res05 = 1./f05;  % Simple conversion like BH_fscGold_class
        else
            res05 = NaN;
        end

        % Find 0.143 crossing
        idx0143 = find(fscVals < 0.143 & highestCycleOsX > 1/100, 1, 'first');
        if ~isempty(idx0143)
            f0143 = highestCycleOsX(idx0143);
            res0143 = 1./f0143;
        else
            res0143 = NaN;
        end

        % Find one-bit crossing
        idxOneBit = find(fscVals - oneBIT < 0 & highestCycleOsX > 1/100, 1, 'first');
        if ~isempty(idxOneBit)
            fOneBit = highestCycleOsX(idxOneBit);
            resOneBit = 1./fOneBit;
        else
            resOneBit = NaN;
        end

        % Find half-bit crossing
        idxHalfBit = find(fscVals - halfBIT < 0 & highestCycleOsX > 1/100, 1, 'first');
        if ~isempty(idxHalfBit)
            fHalfBit = highestCycleOsX(idxHalfBit);
            resHalfBit = 1./fHalfBit;
        else
            resHalfBit = NaN;
        end

        % Add title with resolution metrics
        title(sprintf('FSC - Reference %d, Cycle %d\n0.5=%3.2fÅ\n0.143=%3.2fÅ\nOne-bit=%3.2fÅ\nHalf-bit=%3.2fÅ', ...
                      iRef, highestCycle, res05, res0143, resOneBit, resHalfBit));
    else
        title(sprintf('FSC - Reference %d', iRef));
    end

    % Format axes
    ylabel('FSC');
    ylim([-.05 1.025]);

    % Convert x-axis to resolution using same logic as title (1./frequency)
    if ~isempty(highestCycleOsX)
        % Use full data range in frequency
        minFreq = min(highestCycleOsX(highestCycleOsX > 0));  % Lowest frequency in data
        maxFreq = max(highestCycleOsX);  % Nyquist frequency
        xlim([minFreq, maxFreq]);

        % Get current tick locations in frequency
        currentTicks = get(gca, 'XTick');
        currentTicks = currentTicks(currentTicks > 0); % Remove zero to avoid infinity

        % Add Nyquist frequency to ticks if not already there
        if abs(currentTicks(end) - maxFreq) > 0.01 * maxFreq
            currentTicks(end+1) = maxFreq;
        end

        % Convert ticks to resolution (1./frequency)
        resolutionTicks = 1 ./ currentTicks;

        % Create labels - skip labels > 100Å, mark Nyquist
        nyquistRes = 1 / maxFreq;
        tickLabels = cell(size(resolutionTicks));
        for i = 1:length(resolutionTicks)
            if resolutionTicks(i) > 100
                tickLabels{i} = '';  % Skip labels beyond 100Å
            elseif abs(resolutionTicks(i) - nyquistRes) < 0.1
                tickLabels{i} = sprintf('%.1f (Nyquist)', resolutionTicks(i));
            else
                tickLabels{i} = sprintf('%.1f', resolutionTicks(i));
            end
        end

        % Set resolution labels
        set(gca, 'XTick', currentTicks);
        set(gca, 'XTickLabel', tickLabels);
        xlabel('Resolution (Å)');
    else
        xlabel('Spatial Freq');
    end

    grid on;

    % Add legend (outside plot area to avoid cutoff)
    legend(legendEntries, 'Location', 'northeast','Orientation','vertical');

    hold off;
end

% Save figure
cycleStr = sprintf('%d_', cycles);
cycleStr = cycleStr(1:end-1);
refStr = sprintf('%d_', references);
refStr = refStr(1:end-1);

outputFile = sprintf('FSC/multiCycle_cycles%s_refs%s_%s.pdf', cycleStr, refStr, SUBTOMO_META_NAME);

% Adjust layout to prevent legend cutoff
if exist('fig', 'var')
    % Use tight layout if available (newer MATLAB versions)
    try
        fig.Units = 'inches';
        fig.Position(3) = fig.Position(3) * 1.2; % Make 20% wider
    catch
        % Fallback for older MATLAB
    end
end

saveas(gcf, outputFile, 'pdf');
fprintf('Saved multi-cycle FSC plot to %s\n', outputFile);

% Close figure
close(gcf);

end