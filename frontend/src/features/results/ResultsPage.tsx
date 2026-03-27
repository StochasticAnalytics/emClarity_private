/**
 * Results viewer page — six-tab panel organized by tutorial output types.
 *
 * Tabs:
 *   1. Alignment Quality  — tutorial 5.2.3: fixedStacks/<prefix>_3dfind.ali
 *   2. CTF Diagnostics    — tutorial 6.4: _psRadial_1.pdf, _ccFIT.pdf
 *   3. Particle Picks     — tutorial 8.4: convmap/*.mrc + .mod overlays
 *   4. FSC Curves         — tutorial 11.4: FSC/*_fsc_GLD.pdf, per-cycle resolution
 *   5. Averages           — tutorial 11.4: _REF_ODD.mrc, _REF_EVE.mrc half-maps
 *   6. Particle Stats     — tutorial 14.4.2: CCC scores, class populations
 *
 * Layout pattern (cisTEM Results_panel.md):
 *   [Tab Bar]
 *   [Left Panel — item list] | [Right Panel — visualization]
 *   [Bottom — Prev / Next navigation]
 *
 * API calls:
 *   GET /api/v1/results/fsc        — FSC curve data (returns 404 if not available)
 *   GET /api/v1/results/particles  — Particle statistics (returns 404 if not available)
 */

import { useState } from 'react'
import { useTabParam } from '@/hooks/useTabParam'
import { useApiQuery } from '@/hooks/useApi.ts'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'
import { ApiError } from '@/api/client.ts'

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

interface FscPoint {
  /** Spatial frequency in 1/Å */
  spatial_frequency: number
  /** FSC value between 0.0 and 1.0 */
  fsc: number
}

interface FscData {
  half1_half2: FscPoint[]
  resolution_angstroms: number | null
}

interface ClassCount {
  class_label: string
  count: number
}

interface CccBin {
  bin_center: number
  count: number
}

interface ParticleStats {
  total_count: number
  class_distribution: ClassCount[]
  ccc_histogram: CccBin[]
  mean_ccc: number | null
}

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

const RESULT_TAB_IDS = [
  'alignment', 'ctf', 'particles', 'fsc', 'averages', 'stats',
] as const

type TabId = (typeof RESULT_TAB_IDS)[number]

interface TabDef {
  id: TabId
  label: string
}

const TABS: TabDef[] = [
  { id: 'alignment', label: 'Alignment Quality' },
  { id: 'ctf', label: 'CTF Diagnostics' },
  { id: 'particles', label: 'Particle Picks' },
  { id: 'fsc', label: 'FSC Curves' },
  { id: 'averages', label: 'Averages' },
  { id: 'stats', label: 'Particle Stats' },
]

// ---------------------------------------------------------------------------
// Three-panel layout shell
// ---------------------------------------------------------------------------

interface ThreePanelLayoutProps {
  listItems: string[]
  selectedIndex: number
  onSelect: (index: number) => void
  listLabel: string
  /** Selected indices for multi-select (optional) */
  selectedIndices?: Set<number>
  onToggleIndex?: (index: number) => void
  children: React.ReactNode
}

function ThreePanelLayout({
  listItems,
  selectedIndex,
  onSelect,
  listLabel,
  selectedIndices,
  onToggleIndex,
  children,
}: ThreePanelLayoutProps) {
  const total = listItems.length
  const canGoPrev = selectedIndex > 0
  const canGoNext = selectedIndex < total - 1

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Main area: left list + right visualization */}
      <div className="flex flex-1 min-h-0 overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm">
        {/* Left panel — item list */}
        <div className="w-56 shrink-0 border-r border-gray-200 dark:border-gray-700 flex flex-col">
          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {listLabel}
            </p>
          </div>
          <ul role="listbox" aria-label={listLabel} className="flex-1 overflow-y-auto py-1">
            {listItems.length === 0 ? (
              <li className="px-3 py-3 text-xs text-gray-400 dark:text-gray-500 italic">
                No items available
              </li>
            ) : (
              listItems.map((item, i) => {
                const isSelected = i === selectedIndex
                const isChecked = selectedIndices ? selectedIndices.has(i) : false
                return (
                  <li key={item} className="flex items-center">
                    {onToggleIndex && (
                      <label className="flex items-center pl-3 pr-1 py-2 shrink-0 cursor-pointer">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                          checked={isChecked}
                          onChange={() => onToggleIndex(i)}
                          aria-label={`Include ${item} in comparison`}
                        />
                      </label>
                    )}
                    <button
                      role="option"
                      aria-selected={isSelected}
                      type="button"
                      className={
                        'flex-1 flex items-center text-left px-2 py-2 text-sm transition-colors ' +
                        (isSelected
                          ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium'
                          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800')
                      }
                      onClick={() => onSelect(i)}
                    >
                      <span className="truncate font-mono text-xs">{item}</span>
                    </button>
                  </li>
                )
              })
            )}
          </ul>
        </div>

        {/* Right panel — visualization */}
        <div className="flex-1 min-w-0 overflow-y-auto p-5">{children}</div>
      </div>

      {/* Bottom navigation */}
      <div className="flex items-center justify-between px-4 py-2.5 mt-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm">
        <button
          type="button"
          disabled={!canGoPrev}
          onClick={() => onSelect(selectedIndex - 1)}
          className={
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border ' +
            'transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ' +
            (canGoPrev
              ? 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700'
              : 'border-gray-200 dark:border-gray-700 text-gray-300 dark:text-gray-600 bg-white dark:bg-gray-900 cursor-not-allowed')
          }
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z"
              clipRule="evenodd"
            />
          </svg>
          Previous
        </button>

        <span className="text-xs text-gray-400 dark:text-gray-500">
          {total === 0 ? 'No items' : `${selectedIndex + 1} / ${total}`}
        </span>

        <button
          type="button"
          disabled={!canGoNext}
          onClick={() => onSelect(selectedIndex + 1)}
          className={
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border ' +
            'transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ' +
            (canGoNext
              ? 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700'
              : 'border-gray-200 dark:border-gray-700 text-gray-300 dark:text-gray-600 bg-white dark:bg-gray-900 cursor-not-allowed')
          }
        >
          Next
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared placeholder for empty tabs
// ---------------------------------------------------------------------------

interface PlaceholderContentProps {
  icon?: React.ReactNode
  title: string
  description: string
  outputFiles?: string[]
  tutorialRef?: string
}

function PlaceholderContent({
  icon,
  title,
  description,
  outputFiles,
  tutorialRef,
}: PlaceholderContentProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[240px] text-center px-4">
      {icon ?? (
        <svg
          className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"
          />
        </svg>
      )}
      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">{title}</h4>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm">{description}</p>
      {outputFiles && outputFiles.length > 0 && (
        <div className="mt-4 text-left">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Output files to check:
          </p>
          <ul className="space-y-0.5">
            {outputFiles.map((f) => (
              <li key={f}>
                <code className="text-xs font-mono text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 px-1.5 py-0.5 rounded">
                  {f}
                </code>
              </li>
            ))}
          </ul>
        </div>
      )}
      {tutorialRef && (
        <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
          Tutorial reference: §{tutorialRef}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Alignment Quality (tutorial 5.2.3)
// ---------------------------------------------------------------------------

const ALIGNMENT_TILT_SERIES = [
  'TS_001', 'TS_002', 'TS_003', 'TS_004', 'TS_005',
]

function AlignmentQualityTab() {
  const [selectedIndex, setSelectedIndex] = useState(0)

  return (
    <ThreePanelLayout
      listItems={ALIGNMENT_TILT_SERIES}
      selectedIndex={selectedIndex}
      onSelect={setSelectedIndex}
      listLabel="Tilt Series"
    >
      <PlaceholderContent
        title="Alignment Quality — No data available"
        description={
          `After running Align Tilt-Series (autoAlign), alignment diagnostics for ` +
          `${ALIGNMENT_TILT_SERIES[selectedIndex]} will be displayed here. ` +
          `Check that fiducial tracks are correctly identified and residuals are low.`
        }
        outputFiles={[
          `fixedStacks/<prefix>_3dfind.ali`,
          `fixedStacks/<prefix>_3dfind.xf`,
          `fixedStacks/<prefix>_3dfind.tlt`,
        ]}
        tutorialRef="5.2.3"
      />
    </ThreePanelLayout>
  )
}

// ---------------------------------------------------------------------------
// Tab: CTF Diagnostics (tutorial 6.4)
// ---------------------------------------------------------------------------

const CTF_TILT_SERIES = [
  'TS_001', 'TS_002', 'TS_003', 'TS_004', 'TS_005',
]

function CTFDiagnosticsTab() {
  const [selectedIndex, setSelectedIndex] = useState(0)

  return (
    <ThreePanelLayout
      listItems={CTF_TILT_SERIES}
      selectedIndex={selectedIndex}
      onSelect={setSelectedIndex}
      listLabel="Tilt Series"
    >
      <PlaceholderContent
        icon={
          <svg
            className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"
            />
          </svg>
        }
        title="CTF Diagnostics — No data available"
        description={
          `After running Estimate CTF (ctf estimate), power spectrum and defocus fit ` +
          `diagnostics for ${CTF_TILT_SERIES[selectedIndex]} will appear here. ` +
          `Verify the CTF rings match the fitted model across all tilts.`
        }
        outputFiles={[
          `fixedStacks/<prefix>_psRadial_1.pdf`,
          `fixedStacks/<prefix>_ccFIT.pdf`,
          `fixedStacks/<prefix>_ctf.tlt`,
        ]}
        tutorialRef="6.4"
      />
    </ThreePanelLayout>
  )
}

// ---------------------------------------------------------------------------
// Tab: Particle Picks (tutorial 8.4)
// ---------------------------------------------------------------------------

const PARTICLE_PICK_ITEMS = [
  'TS_001 sub-region 1',
  'TS_001 sub-region 2',
  'TS_002 sub-region 1',
  'TS_002 sub-region 2',
  'TS_003 sub-region 1',
]

function ParticlePicksTab() {
  const [selectedIndex, setSelectedIndex] = useState(0)

  return (
    <ThreePanelLayout
      listItems={PARTICLE_PICK_ITEMS}
      selectedIndex={selectedIndex}
      onSelect={setSelectedIndex}
      listLabel="Sub-regions"
    >
      <PlaceholderContent
        icon={
          <svg
            className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25"
            />
          </svg>
        }
        title="Particle Picks — No data available"
        description={
          `After running Pick Particles (templateSearch), convolution maps and ` +
          `particle picks for ${PARTICLE_PICK_ITEMS[selectedIndex]} will be displayed here ` +
          `with .mod overlay showing pick locations.`
        }
        outputFiles={[
          `convmap/<prefix>_convmap.mrc`,
          `convmap/<prefix>.mod`,
          `convmap/<prefix>_convmap_peak.txt`,
        ]}
        tutorialRef="8.4"
      />
    </ThreePanelLayout>
  )
}

// ---------------------------------------------------------------------------
// Tab: FSC Curves (tutorial 11.4) — recharts LineChart with 0.143 threshold
// ---------------------------------------------------------------------------

const FSC_THRESHOLD = 0.143
const FSC_THRESHOLD_LABEL = '0.143 criterion'

/** Placeholder cycle list — real data would come from the backend */
const PLACEHOLDER_CYCLES = ['cycle000', 'cycle001', 'cycle002', 'cycle003']

interface FscChartProps {
  curves: Array<{ cycleLabel: string; data: FscPoint[]; resolution: number | null }>
}

const CYCLE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

function FscMultiChart({ curves }: FscChartProps) {
  const formatFrequency = (value: number): string => {
    if (value === 0) return '∞'
    return `${(1 / value).toFixed(1)} Å`
  }

  const formatFsc = (value: number): string => value.toFixed(3)

  // Merge all curves onto a common x-axis by spatial frequency key
  const mergedData = (() => {
    const map = new Map<number, Record<string, number>>()
    curves.forEach(({ cycleLabel, data }) => {
      data.forEach(({ spatial_frequency, fsc }) => {
        if (!map.has(spatial_frequency)) map.set(spatial_frequency, { spatial_frequency })
        const row = map.get(spatial_frequency)!
        row[cycleLabel] = fsc
      })
    })
    return Array.from(map.values()).sort((a, b) => a.spatial_frequency - b.spatial_frequency)
  })()

  return (
    <div className="space-y-3">
      {/* Resolution badges */}
      {curves.some((c) => c.resolution !== null) && (
        <div className="flex flex-wrap gap-2">
          {curves.map(({ cycleLabel, resolution }, i) =>
            resolution !== null ? (
              <span
                key={cycleLabel}
                className="inline-flex items-center gap-1.5 text-xs rounded-full px-2.5 py-0.5 font-medium"
                style={{ backgroundColor: `${CYCLE_COLORS[i % CYCLE_COLORS.length]}22`, color: CYCLE_COLORS[i % CYCLE_COLORS.length] }}
              >
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ backgroundColor: CYCLE_COLORS[i % CYCLE_COLORS.length] }}
                />
                {cycleLabel}: {resolution.toFixed(2)} Å
              </span>
            ) : null
          )}
        </div>
      )}

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={mergedData} margin={{ top: 8, right: 80, bottom: 28, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis
            dataKey="spatial_frequency"
            tickFormatter={formatFrequency}
            label={{
              value: 'Resolution (Å)',
              position: 'insideBottom',
              offset: -16,
              style: { fontSize: 12, fill: 'currentColor' },
            }}
            tick={{ fontSize: 11 }}
          />
          <YAxis
            domain={[0, 1]}
            tickFormatter={formatFsc}
            label={{
              value: 'FSC',
              angle: -90,
              position: 'insideLeft',
              style: { fontSize: 12, fill: 'currentColor' },
            }}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            formatter={(value, name) => [
              typeof value === 'number' ? formatFsc(value) : '',
              String(name),
            ]}
            labelFormatter={(label) =>
              typeof label === 'number' ? `Resolution: ${formatFrequency(label)}` : String(label)
            }
            contentStyle={{ fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
          {/* Gold-standard 0.143 threshold line */}
          <ReferenceLine
            y={FSC_THRESHOLD}
            stroke="#f59e0b"
            strokeDasharray="6 3"
            strokeWidth={2}
            label={{
              value: FSC_THRESHOLD_LABEL,
              position: 'right',
              style: { fontSize: 11, fill: '#f59e0b' },
            }}
          />
          {curves.map(({ cycleLabel }, i) => (
            <Line
              key={cycleLabel}
              type="monotone"
              dataKey={cycleLabel}
              name={cycleLabel}
              stroke={CYCLE_COLORS[i % CYCLE_COLORS.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function FscCurvesTab() {
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [checkedIndices, setCheckedIndices] = useState<Set<number>>(new Set([0]))

  const {
    data: fscData,
    error: fscError,
    isLoading: fscLoading,
    isFetching: fscFetching,
    refetch: fscRefetch,
  } = useApiQuery<FscData>(['results', 'fsc'], '/api/v1/results/fsc')

  const handleToggle = (index: number) => {
    setCheckedIndices((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        // Always keep at least one selected
        if (next.size > 1) next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  // Build the curves array for multi-cycle comparison
  const curves: FscChartProps['curves'] = Array.from(checkedIndices)
    .sort((a, b) => a - b)
    .map((i) => {
      const label = PLACEHOLDER_CYCLES[i] ?? `cycle${String(i).padStart(3, '0')}`
      // Only cycle000 (index 0) has real data from the API (when available)
      if (i === 0 && fscData) {
        return {
          cycleLabel: label,
          data: fscData.half1_half2,
          resolution: fscData.resolution_angstroms,
        }
      }
      return { cycleLabel: label, data: [], resolution: null }
    })

  return (
    <ThreePanelLayout
      listItems={PLACEHOLDER_CYCLES}
      selectedIndex={selectedIndex}
      onSelect={(i) => {
        setSelectedIndex(i)
        // Auto-select the clicked cycle for viewing
        setCheckedIndices((prev) => {
          if (prev.has(i)) return prev
          return new Set([...prev, i])
        })
      }}
      listLabel="Cycles"
      selectedIndices={checkedIndices}
      onToggleIndex={handleToggle}
    >
      <div className="space-y-4">
        {/* Header with refresh */}
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Fourier Shell Correlation
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              FSC between independent half-datasets — check cycles using checkboxes for comparison
            </p>
          </div>
          <button
            type="button"
            disabled={fscFetching}
            aria-label="Refresh FSC data"
            className={
              'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium ' +
              'border border-gray-300 dark:border-gray-600 ' +
              'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 ' +
              'hover:bg-gray-50 dark:hover:bg-gray-700 ' +
              'focus:outline-none focus:ring-2 focus:ring-blue-500 ' +
              'transition-colors disabled:opacity-50'
            }
            onClick={() => void fscRefetch()}
          >
            <svg
              className={`w-3.5 h-3.5 ${fscFetching ? 'animate-spin' : ''}`}
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
                clipRule="evenodd"
              />
            </svg>
            Refresh
          </button>
        </div>

        {/* Chart area */}
        {fscLoading && (
          <div className="flex items-center justify-center py-20">
            <svg
              className="w-5 h-5 animate-spin text-blue-500"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">Loading FSC data…</span>
          </div>
        )}

        {!fscLoading && fscError && !(fscError instanceof ApiError && fscError.status === 404) && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4">
            <p className="text-sm text-red-700 dark:text-red-400">
              {fscError instanceof ApiError
                ? `Failed to load FSC data (${fscError.status}): ${fscError.statusText}`
                : 'Failed to load FSC data.'}
            </p>
            <button
              type="button"
              onClick={() => void fscRefetch()}
              className="mt-2 text-sm text-red-600 dark:text-red-400 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {!fscLoading && (!fscError || (fscError instanceof ApiError && fscError.status === 404)) && (
          <>
            {curves.some((c) => c.data.length > 0) ? (
              <FscMultiChart curves={curves.filter((c) => c.data.length > 0)} />
            ) : (
              <PlaceholderContent
                icon={
                  <svg
                    className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={1.5}
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
                    />
                  </svg>
                }
                title="No FSC data available"
                description="FSC curves will appear here after running the avg step. Select cycles on the left to compare resolution across processing iterations."
                outputFiles={['FSC/<prefix>_fsc_GLD.pdf', 'FSC/<prefix>_GLD.mrc']}
                tutorialRef="11.4"
              />
            )}
          </>
        )}
      </div>
    </ThreePanelLayout>
  )
}

// ---------------------------------------------------------------------------
// Tab: Averages (tutorial 11.4)
// ---------------------------------------------------------------------------

const AVERAGE_CYCLES = ['cycle000', 'cycle001', 'cycle002', 'cycle003']

function AveragesTab() {
  const [selectedIndex, setSelectedIndex] = useState(0)

  return (
    <ThreePanelLayout
      listItems={AVERAGE_CYCLES}
      selectedIndex={selectedIndex}
      onSelect={setSelectedIndex}
      listLabel="Cycles"
    >
      <PlaceholderContent
        icon={
          <svg
            className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 7.5l-2.25-1.313M21 7.5v2.25m0-2.25l-2.25 1.313M3 7.5l2.25-1.313M3 7.5l2.25 1.313M3 7.5v2.25m9 3l2.25-1.313M12 12.75l-2.25-1.313M12 12.75V15m0 6.75l2.25-1.313M12 21.75V19.5m0 2.25l-2.25-1.313m0-16.875L12 2.25l2.25 1.313M21 14.25v2.25l-9 5.25-9-5.25v-2.25l9-5.25 9 5.25z"
            />
          </svg>
        }
        title="Averages — No data available"
        description={
          `After running Subtomogram Averaging (avg), the half-map volumes for ` +
          `${AVERAGE_CYCLES[selectedIndex]} will be available for inspection here. ` +
          `Inspect both half-maps and the filtered final map.`
        }
        outputFiles={[
          `cycle${String(selectedIndex).padStart(3, '0')}_REF_ODD.mrc`,
          `cycle${String(selectedIndex).padStart(3, '0')}_REF_EVE.mrc`,
          `cycle${String(selectedIndex).padStart(3, '0')}_REF_FLT.mrc`,
        ]}
        tutorialRef="11.4"
      />
    </ThreePanelLayout>
  )
}

// ---------------------------------------------------------------------------
// Tab: Particle Stats (tutorial 14.4.2)
// ---------------------------------------------------------------------------

interface ParticleStatsContentProps {
  stats: ParticleStats
}

function ParticleStatsContent({ stats }: ParticleStatsContentProps) {
  return (
    <div className="space-y-6">
      {/* Summary stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <StatCard label="Total Particles" value={stats.total_count.toLocaleString()} />
        <StatCard label="Classes" value={stats.class_distribution.length.toString()} />
        {stats.mean_ccc !== null && (
          <StatCard label="Mean CCC Score" value={stats.mean_ccc.toFixed(4)} />
        )}
      </div>

      {/* Class distribution chart */}
      {stats.class_distribution.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Class Distribution
          </h4>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={stats.class_distribution}
              margin={{ top: 4, right: 16, bottom: 8, left: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="class_label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Bar dataKey="count" name="Particles" fill="#3b82f6" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* CCC score histogram */}
      {stats.ccc_histogram.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            CCC Score Histogram
          </h4>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={stats.ccc_histogram}
              margin={{ top: 4, right: 16, bottom: 24, left: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis
                dataKey="bin_center"
                tickFormatter={(v: number) => v.toFixed(2)}
                tick={{ fontSize: 11 }}
                label={{
                  value: 'CCC Score',
                  position: 'insideBottom',
                  offset: -12,
                  style: { fontSize: 11, fill: 'currentColor' },
                }}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value) => [typeof value === 'number' ? value : 0, 'Particles']}
                labelFormatter={(label) =>
                  typeof label === 'number' ? `CCC: ${label.toFixed(3)}` : String(label)
                }
                contentStyle={{ fontSize: 12 }}
              />
              <Bar dataKey="count" name="Particles" fill="#10b981" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

const PARTICLE_STATS_CYCLES = ['cycle000', 'cycle001', 'cycle002', 'cycle003']

function ParticleStatsTab() {
  const [selectedIndex, setSelectedIndex] = useState(0)

  const cycleLabel = PARTICLE_STATS_CYCLES[selectedIndex] ?? `cycle${String(selectedIndex).padStart(3, '0')}`
  const { data, error, isLoading, refetch } = useApiQuery<ParticleStats>(
    ['results', 'particles', cycleLabel],
    `/api/v1/results/particles?cycle=${cycleLabel}`,
  )

  // Distinguish 404 (not available) from other errors
  const is404 = error instanceof ApiError && error.status === 404

  return (
    <ThreePanelLayout
      listItems={PARTICLE_STATS_CYCLES}
      selectedIndex={selectedIndex}
      onSelect={setSelectedIndex}
      listLabel="Cycles"
    >
      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Particle Statistics
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            CCC score distributions and class population counts — global statistics (tutorial §14.4.2)
          </p>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center py-20">
            <svg
              className="w-5 h-5 animate-spin text-blue-500"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">Loading particle statistics…</span>
          </div>
        )}

        {!isLoading && error && !is404 && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4">
            <p className="text-sm text-red-700 dark:text-red-400">
              {`Failed to load particle statistics (${error.status}): ${error.statusText}`}
            </p>
            <button
              type="button"
              onClick={() => void refetch()}
              className="mt-2 text-sm text-red-600 dark:text-red-400 underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && is404 && (
          <PlaceholderContent
            title="No particle statistics available"
            description="Particle statistics will appear here after running particle alignment (alignRaw) or classification (pca / cluster)."
            outputFiles={[
              '<prefix>_ClassIDX.txt',
              'FSC/<prefix>_fsc_GLD.pdf',
            ]}
            tutorialRef="14.4.2"
          />
        )}

        {!isLoading && data && <ParticleStatsContent stats={data} />}
      </div>
    </ThreePanelLayout>
  )
}

// ---------------------------------------------------------------------------
// Shared StatCard component
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string
  value: string
  sub?: string
}

function StatCard({ label, value, sub }: StatCardProps) {
  return (
    <div className="rounded-md bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 px-4 py-3">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ResultsPage — exported page component
// ---------------------------------------------------------------------------

export function ResultsPage() {
  // Active tab — persisted in URL ?tab= query parameter
  const [activeTab, setActiveTab] = useTabParam(RESULT_TAB_IDS)

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Results</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Review processing outputs organized by tutorial stage. Check each tab after running the corresponding pipeline step.
        </p>
      </div>

      {/* Tab bar */}
      <div
        role="tablist"
        aria-label="Result types"
        className="flex gap-0 border-b border-gray-200 dark:border-gray-700 overflow-x-auto"
      >
        {TABS.map((tab) => {
          const isActive = tab.id === activeTab
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={isActive}
              aria-controls={`tabpanel-${tab.id}`}
              id={`tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={
                'whitespace-nowrap px-4 py-2.5 text-sm font-medium border-b-2 transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500 ' +
                (isActive
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600')
              }
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab panels — all rendered but hidden to preserve state and avoid re-fetching */}
      <div className="flex-1 min-h-0">
        {TABS.map((tab) => (
          <div
            key={tab.id}
            role="tabpanel"
            id={`tabpanel-${tab.id}`}
            aria-labelledby={`tab-${tab.id}`}
            hidden={tab.id !== activeTab}
            className="h-full"
          >
            {tab.id === 'alignment' && <AlignmentQualityTab />}
            {tab.id === 'ctf' && <CTFDiagnosticsTab />}
            {tab.id === 'particles' && <ParticlePicksTab />}
            {tab.id === 'fsc' && <FscCurvesTab />}
            {tab.id === 'averages' && <AveragesTab />}
            {tab.id === 'stats' && <ParticleStatsTab />}
          </div>
        ))}
      </div>
    </div>
  )
}
