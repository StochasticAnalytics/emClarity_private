/**
 * ActionsPage – processing commands panel.
 *
 * Lists the emClarity pipeline actions (autoAlign, ctf estimate, templateSearch,
 * init, ctf 3d, avg, alignRaw, tomoCPR, classify) with their parameters and
 * run controls.
 *
 * Route: /project/:projectId/actions
 */
import { useProject } from '@/context/ProjectContext.tsx'

/** emClarity pipeline actions in processing order. */
const PIPELINE_ACTIONS = [
  {
    id: 'autoAlign',
    label: 'Align Tilt-Series',
    description: 'Align tilt-series images using gold fiducials or patch tracking.',
    command: 'autoAlign',
  },
  {
    id: 'ctfEstimate',
    label: 'Estimate CTF',
    description: 'Estimate contrast transfer function parameters (defocus, astigmatism).',
    command: 'ctf estimate',
  },
  {
    id: 'reconCoords',
    label: 'Select Sub-regions',
    description: 'Define sub-tomogram extraction coordinates and reconstruction regions.',
    command: 'recon.coords',
  },
  {
    id: 'templateSearch',
    label: 'Pick Particles',
    description: 'Template-based particle picking using cross-correlation search.',
    command: 'templateSearch',
  },
  {
    id: 'init',
    label: 'Initialize Project',
    description: 'Initialize the sub-tomogram averaging project and extract particles.',
    command: 'init',
  },
  {
    id: 'ctf3d',
    label: 'Reconstruct Tomograms',
    description: 'Reconstruct tomograms with CTF correction (phase-flipping or Wiener).',
    command: 'ctf 3d',
  },
  {
    id: 'avg',
    label: 'Subtomogram Averaging',
    description: 'Average aligned sub-tomograms and compute FSC between half-sets.',
    command: 'avg',
  },
  {
    id: 'alignRaw',
    label: 'Subtomogram Alignment',
    description: 'Align individual sub-tomograms against the reference structure.',
    command: 'alignRaw',
  },
  {
    id: 'tomoCPR',
    label: 'Tilt-Series Refinement',
    description: 'Refine tilt-series geometry using particle-based CTF refinement (TomoCPR).',
    command: 'tomoCPR',
  },
  {
    id: 'classify',
    label: 'Classification',
    description: 'Principal component analysis and hierarchical classification of sub-tomograms.',
    command: 'pca / cluster',
  },
  {
    id: 'finalRecon',
    label: 'Final Reconstruction',
    description: 'Generate the final filtered reconstruction at full resolution.',
    command: 'avg FinalAlignment',
  },
] as const

interface ActionCardProps {
  label: string
  description: string
  command: string
  disabled?: boolean
}

function ActionCard({ label, description, command, disabled = false }: ActionCardProps) {
  return (
    <div
      className={`flex items-start justify-between gap-4 rounded-lg border p-4 transition-colors ${
        disabled
          ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 opacity-60'
          : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-blue-300 dark:hover:border-blue-700'
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{label}</h4>
          <code className="inline-flex items-center rounded bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 text-xs font-mono text-gray-600 dark:text-gray-400">
            {command}
          </code>
        </div>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{description}</p>
      </div>

      <button
        type="button"
        disabled={disabled}
        className={
          'shrink-0 inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium ' +
          'border border-blue-300 dark:border-blue-700 ' +
          'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 ' +
          'hover:bg-blue-100 dark:hover:bg-blue-900/50 ' +
          'focus:outline-none focus:ring-2 focus:ring-blue-500 ' +
          'transition-colors disabled:pointer-events-none disabled:opacity-50'
        }
        aria-label={`Run ${label}`}
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M2 10a8 8 0 1116 0 8 8 0 01-16 0zm6.39-2.908a.75.75 0 01.766.027l3.5 2.25a.75.75 0 010 1.262l-3.5 2.25A.75.75 0 018 12.25v-4.5a.75.75 0 01.39-.658z"
            clipRule="evenodd"
          />
        </svg>
        Run
      </button>
    </div>
  )
}

export function ActionsPage() {
  const { projectId } = useProject()

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Actions</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Run emClarity processing commands for project{' '}
          <code className="font-mono text-xs font-medium">{projectId ?? '—'}</code>.
        </p>
      </div>

      {/* Action list */}
      <section aria-labelledby="pipeline-actions-heading">
        <h3
          id="pipeline-actions-heading"
          className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3"
        >
          Pipeline Actions
        </h3>
        <div className="space-y-3">
          {PIPELINE_ACTIONS.map((action) => (
            <ActionCard
              key={action.id}
              label={action.label}
              description={action.description}
              command={action.command}
            />
          ))}
        </div>
      </section>
    </div>
  )
}
