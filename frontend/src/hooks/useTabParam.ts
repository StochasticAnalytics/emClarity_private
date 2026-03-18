/**
 * useTabParam — persist active tab selection in URL query parameters.
 *
 * Replaces per-page `useState` for tab tracking so that:
 *   - Tabs survive page refresh (URL is the source of truth)
 *   - Tabs survive navigate-away + navigate-back (browser history)
 *   - Direct URLs like `?tab=ctf-estimate` open the correct tab
 *   - Unknown/invalid `?tab=` values fall back to the first tab
 *
 * Internal tab IDs (camelCase, snake_case, or already-kebab) are
 * converted to lowercase-dash-separated URL values automatically.
 */
import { useMemo, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'

// ---------------------------------------------------------------------------
// Conversion helpers
// ---------------------------------------------------------------------------

/**
 * Convert an internal tab ID to a URL-friendly kebab-case string.
 *
 * Handles camelCase (`autoAlign` → `auto-align`), snake_case
 * (`disk_management` → `disk-management`), and mixed forms
 * (`tomoCPR` → `tomo-cpr`, `ctf3d` → `ctf-3d`).
 */
function toKebabCase(s: string): string {
  return s
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/_/g, '-')
    .replace(/([a-zA-Z])(\d)/g, '$1-$2')
    .toLowerCase()
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Read and write the active tab via the `?tab=` URL query parameter.
 *
 * @param validIds  Ordered list of valid internal tab IDs.  The first entry
 *                  is the default when the URL contains no `tab` param or an
 *                  unrecognised value.
 * @returns `[activeId, setActiveId]` — the current internal ID and a setter
 *          that updates the URL (using `replace` to avoid polluting history).
 */
export function useTabParam<T extends string>(
  validIds: readonly [T, ...T[]],
): [T, (id: T) => void] {
  const defaultId: T = validIds[0]

  // Build bidirectional maps (kebab URL value ↔ internal ID).
  // Memoised on the identity of validIds so we don't rebuild every render.
  const fromUrl = useMemo(() => {
    const map = new Map<string, T>()
    for (const id of validIds) {
      map.set(toKebabCase(id), id)
    }
    return map
  }, [validIds])

  const [searchParams, setSearchParams] = useSearchParams()

  const urlTab = searchParams.get('tab')
  const resolvedId: T =
    urlTab !== null && fromUrl.has(urlTab) ? (fromUrl.get(urlTab) as T) : defaultId

  const activeId = resolvedId

  // Normalize an invalid/missing ?tab= value so the URL always reflects the
  // active tab.  Runs after render to avoid setState-during-render warnings.
  const needsNormalization =
    urlTab === null || !fromUrl.has(urlTab)
  useEffect(() => {
    if (needsNormalization) {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('tab', toKebabCase(defaultId))
          return next
        },
        { replace: true },
      )
    }
  }, [needsNormalization, defaultId, setSearchParams])

  const setActiveId = useCallback(
    (id: T) => {
      const urlId = toKebabCase(id)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('tab', urlId)
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  return [activeId, setActiveId]
}
