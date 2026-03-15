/**
 * ExpertPage – advanced parameter panel showing ALL parameters from
 * parameter_schema.json that are NOT claimed by any Action tab.
 *
 * "Claimed" params appear in the tutorial-driven Action tabs (Tables 3–12).
 * What remains are experimental, debug, or rarely-changed settings that are
 * not mentioned in the emClarity tutorial.
 *
 * Layout mirrors the Action tab accordion pattern:
 *   - Parameters grouped by schema category
 *   - Collapsible accordion sections (defaultOpen=false to avoid overwhelming)
 *   - Same ParameterField input pattern as ActionsPage
 *
 * The shared parameterRegistry module drives the claimed/unclaimed split.
 */

import { useState, useMemo } from 'react'
import { ChevronDown, ChevronRight, FlaskConical, Info } from 'lucide-react'
import rawSchema from '@/data/parameter-schema.json'
import { CLAIMED_PARAMS } from '@/data/parameterRegistry'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SchemaParam {
  name: string
  type: 'numeric' | 'string' | 'boolean' | 'numeric_array'
  required: boolean
  default: number | string | boolean | number[] | null
  range: [number, number] | null
  description: string
  category: string
  deprecated_name?: string | null
}

// ---------------------------------------------------------------------------
// Category metadata
// ---------------------------------------------------------------------------

/** Human-readable label for each schema category. */
const CATEGORY_LABELS: Record<string, string> = {
  microscope:       'Microscope',
  hardware:         'Hardware & Performance',
  ctf:              'CTF Processing',
  alignment:        'Alignment',
  classification:   'Classification',
  masking:          'Masking',
  metadata:         'Metadata',
  disk_management:  'Disk Management',
  dose:             'Dose Weighting',
  fsc:              'Fourier Shell Correlation',
  template_matching:'Template Matching',
  tomoCPR:          'TomoCPR / Tilt Refinement',
}

/**
 * Display order for categories (most commonly needed first).
 * Categories not listed here are appended alphabetically at the end.
 */
const CATEGORY_ORDER: string[] = [
  'hardware',
  'metadata',
  'disk_management',
  'alignment',
  'ctf',
  'fsc',
  'masking',
  'template_matching',
  'classification',
  'tomoCPR',
  'microscope',
  'dose',
]

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface AccordionSectionProps {
  title: string
  count: number
  children: React.ReactNode
  defaultOpen?: boolean
}

function AccordionSection({
  title,
  count,
  children,
  defaultOpen = false,
}: AccordionSectionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors text-left"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
            {title}
          </span>
          <span className="inline-flex items-center rounded-full bg-gray-200 dark:bg-gray-700 px-2 py-0.5 text-xs font-medium text-gray-600 dark:text-gray-400">
            {count}
          </span>
        </div>
        {open
          ? <ChevronDown className="h-4 w-4 text-gray-400 shrink-0" />
          : <ChevronRight className="h-4 w-4 text-gray-400 shrink-0" />}
      </button>

      {open && (
        <div className="px-4 py-3 space-y-3 bg-white dark:bg-gray-900">
          {children}
        </div>
      )}
    </div>
  )
}

interface ParameterFieldProps {
  param: SchemaParam
  value: string
  onChange: (name: string, value: string) => void
}

function ParameterField({ param, value, onChange }: ParameterFieldProps) {
  const id = `expert-param-${param.name}`

  const defaultStr = (() => {
    if (param.default === null || param.default === undefined) return ''
    if (Array.isArray(param.default)) return JSON.stringify(param.default)
    return String(param.default)
  })()

  const placeholder = defaultStr || (param.type === 'string' ? '…' : '0')

  return (
    <div className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 items-start">
      {/* Label + description */}
      <div className="min-w-0">
        <label
          htmlFor={id}
          className="block text-xs font-medium text-gray-800 dark:text-gray-200 font-mono"
          title={param.description}
        >
          {param.name}
          {param.required && (
            <span className="ml-0.5 text-red-500" aria-label="required">*</span>
          )}
          {param.deprecated_name && (
            <span className="ml-1.5 text-xs font-normal font-sans text-amber-600 dark:text-amber-400">
              (was: {param.deprecated_name})
            </span>
          )}
        </label>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 leading-snug line-clamp-2">
          {param.description}
        </p>
      </div>

      {/* Input */}
      <div className="shrink-0 w-36">
        {param.type === 'boolean' ? (
          <select
            id={id}
            value={value !== '' ? value : (param.default !== null ? String(param.default) : '0')}
            onChange={(e) => onChange(param.name, e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-xs text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="1">true (1)</option>
            <option value="0">false (0)</option>
          </select>
        ) : (
          <input
            id={id}
            type="text"
            inputMode={param.type === 'numeric' ? 'decimal' : 'text'}
            placeholder={placeholder}
            value={value}
            onChange={(e) => onChange(param.name, e.target.value)}
            className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-xs text-gray-900 dark:text-gray-100 font-mono placeholder:text-gray-300 dark:placeholder:text-gray-600 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        )}
        {param.range && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 text-right">
            [{param.range[0]}, {param.range[1]}]
          </p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ExpertPage() {
  const [values, setValues] = useState<Record<string, string>>({})

  function handleChange(name: string, val: string) {
    setValues((prev) => ({ ...prev, [name]: val }))
  }

  // Compute unclaimed params once (schema params not in any Action tab)
  const unclaimedParams = useMemo<SchemaParam[]>(() => {
    const schemaParams = (rawSchema as { parameters: SchemaParam[] }).parameters
    return schemaParams.filter((p) => !CLAIMED_PARAMS.has(p.name))
  }, [])

  // Group unclaimed params by category
  const groupedParams = useMemo<Map<string, SchemaParam[]>>(() => {
    const groups = new Map<string, SchemaParam[]>()
    for (const p of unclaimedParams) {
      const cat = p.category ?? 'general'
      if (!groups.has(cat)) groups.set(cat, [])
      groups.get(cat)!.push(p)
    }
    return groups
  }, [unclaimedParams])

  // Sort categories by display order
  const sortedCategories = useMemo<string[]>(() => {
    const cats = Array.from(groupedParams.keys())
    return cats.sort((a, b) => {
      const ai = CATEGORY_ORDER.indexOf(a)
      const bi = CATEGORY_ORDER.indexOf(b)
      if (ai === -1 && bi === -1) return a.localeCompare(b)
      if (ai === -1) return 1
      if (bi === -1) return -1
      return ai - bi
    })
  }, [groupedParams])

  // Total claimed count (schema params only, not fallback-only params)
  const totalSchemaParams = (rawSchema as { parameters: SchemaParam[] }).parameters.length
  const claimedSchemaCount = totalSchemaParams - unclaimedParams.length

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <FlaskConical className="h-5 w-5 text-amber-500" aria-hidden="true" />
          <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
            Expert Options
          </h2>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Advanced parameters not exposed in Action tabs. These are experimental,
          debug, or rarely-changed settings not covered by the emClarity tutorial
          tables (Tables 3–12).
        </p>
      </div>

      {/* Stats banner */}
      <div className="rounded-lg border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 flex items-start gap-3">
        <Info className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
        <p className="text-sm text-amber-800 dark:text-amber-300">
          Showing{' '}
          <span className="font-semibold">{unclaimedParams.length} unclaimed parameters</span>
          {' '}from the schema.{' '}
          The other{' '}
          <span className="font-semibold">{claimedSchemaCount} parameters</span>
          {' '}are covered by tutorial Action tabs and will not appear here.
        </p>
      </div>

      {/* Category accordion sections */}
      <div className="space-y-3">
        {sortedCategories.map((cat) => {
          const params = groupedParams.get(cat)!
          const label = CATEGORY_LABELS[cat] ?? cat

          return (
            <AccordionSection
              key={cat}
              title={label}
              count={params.length}
              defaultOpen={false}
            >
              <div className="space-y-3">
                {params.map((p) => (
                  <ParameterField
                    key={p.name}
                    param={p}
                    value={values[p.name] ?? ''}
                    onChange={handleChange}
                  />
                ))}
              </div>
            </AccordionSection>
          )
        })}
      </div>

      {unclaimedParams.length === 0 && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-8 text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            All schema parameters are claimed by Action tabs.
          </p>
        </div>
      )}
    </div>
  )
}
