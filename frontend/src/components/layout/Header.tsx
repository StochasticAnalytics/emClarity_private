import { Microscope } from 'lucide-react'

/**
 * Top header bar displayed above the main content area.
 */
export function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6 dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        <Microscope className="h-4 w-4" />
        <span>Cryo-EM Sub-Tomogram Averaging</span>
      </div>
      <div className="text-xs text-gray-400 dark:text-gray-500">
        emClarity GUI
      </div>
    </header>
  )
}
