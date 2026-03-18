/**
 * ActionsPage – Actions panel with one tab per emClarity tutorial section.
 *
 * 11 tabs in pipeline order (tutorial sections 5–15), each showing:
 *   Left  panel: parameters in collapsible accordion sections
 *   Right panel: help text (objectives, command signature, key outputs)
 *   Bottom bar:  Run Profile dropdown + Start Command button (stub)
 *
 * Progressive parameter disclosure (3 levels per TASK-020):
 *   Level 1 (default):  starred params (* in tutorial tables)
 *   Level 2 (toggle):   optional params in same tutorial table (no *)
 *   Level 3 (TASK-021): schema params not in any tutorial table → ExpertPage
 *
 * Parameters sourced from parameter_schema.json with types/defaults/ranges.
 * Manual fallbacks cover tutorial params absent from the schema.
 */

import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { useParams, Navigate, useNavigate } from 'react-router-dom'
import { useTabParam } from '@/hooks/useTabParam'
import { DEMO_PROJECT_ID } from '@/constants'
import { ChevronDown, ChevronRight, Settings2, Play, BookOpen, Info, ExternalLink, History, Download } from 'lucide-react'
import rawSchema from '@/data/parameter-schema.json'
import type { ParameterDefinition } from '@/types/parameters'
import { ACTION_TAB_IDS, type ActionTabId } from '@/data/parameterRegistry'
import { useRunProfiles } from '@/hooks/useRunProfiles'
import { apiClient, ApiError } from '@/api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Alias to the canonical parameter definition from types/parameters.ts.
 * Using the canonical type eliminates the duplicate SchemaParam interface
 * that previously diverged from ExpertPage's definition (missing numeric_array
 * and deprecated_name).
 */
type SchemaParam = ParameterDefinition

/** Response from creating a parameter snapshot. */
interface SnapshotResponse {
  snapshot_id: string
  filename: string
  created_at: string
}

/** Response from exporting a snapshot to .m format. */
interface ExportMResponse {
  m_file_path: string
}

/** Snapshot list item from the list endpoint */
interface SnapshotListItem {
  snapshot_id: string
  filename: string
  created_at: string
}

interface SnapshotListResponse {
  snapshots: SnapshotListItem[]
}

interface SnapshotDetailResponse {
  snapshot_id: string
  parameters: Record<string, unknown>
  created_at: string
}

/** Response from the workflow run endpoint. */
interface RunCommandResponse {
  project_id: string
  command: string
  status: string
  message: string
  param_file: string | null
}

/** A parameter entry within a tab's accordion section. */
interface TabParamDef {
  /** Parameter name – matches schema key (best-effort). */
  name: string
  /** Accordion section label. */
  group: string
  /**
   * `false` = default visible (starred in tutorial table).
   * `true`  = hidden behind "Show Expert Options" toggle.
   */
  optional: boolean
}

/** Full definition of one action tab. */
interface ActionTabDef {
  /** Must match an entry in ACTION_TAB_IDS — enforced at compile time. */
  id: ActionTabId
  label: string
  shortLabel: string
  tutorialSection: number
  command: string
  objectives: string
  commandSignature: string
  keyOutputs: string[]
  notes?: string
  params: TabParamDef[]
}

// ---------------------------------------------------------------------------
// Manual fallbacks for params not found in parameter_schema.json
// ---------------------------------------------------------------------------

interface FallbackParam {
  type: 'numeric' | 'string' | 'boolean'
  default: number | string | boolean | null
  range?: [number, number] | null
  description: string
}

const PARAM_FALLBACKS: Record<string, FallbackParam> = {
  // ── autoAlign ────────────────────────────────────────────────────────────
  autoAli_max_resolution: {
    type: 'numeric', default: 18, range: [1, 100],
    description: 'Low-pass cutoff in Å used in alignment. An additional median filter is applied before alignment. Default=18.',
  },
  autoAli_min_sampling_rate: {
    type: 'numeric', default: 10, range: [1, 50],
    description: 'Maximum pixel size (Å/pix) used for alignment. Alignment starts at this bin level. Default=10.',
  },
  autoAli_max_sampling_rate: {
    type: 'numeric', default: 3, range: [1, 20],
    description: 'Minimum pixel size (Å/pix) used for alignment. Alignment ends at this bin level. Default=3.',
  },
  autoAli_iterations_per_bin: {
    type: 'numeric', default: 3, range: [1, 20],
    description: 'Number of patch tracking iterations per bin. Default=3.',
  },
  autoAli_n_iters_no_rotation: {
    type: 'numeric', default: 3, range: [0, 20],
    description: 'Number of patch tracking iterations per bin before activating local alignments. Default=3.',
  },
  autoAli_patch_size_factor: {
    type: 'numeric', default: 4, range: [1, 20],
    description: 'Sets the size of patches for patch tracking. Larger values yield more patches and more local areas. Default=4.',
  },
  autoAli_patch_tracking_border: {
    type: 'numeric', default: 64, range: [0, 256],
    description: 'Number of pixels to trim off each edge in X and Y. Corresponds to -BordersInXandY in tiltxcorr. Default=64.',
  },
  autoAli_patch_overlap: {
    type: 'numeric', default: 0.5, range: [0, 1],
    description: 'Fractional overlap in X and Y between patches tracked by correlation. Corresponds to -OverlapOfPatchesXandY. Default=0.5.',
  },
  autoAli_max_shift_in_angstroms: {
    type: 'numeric', default: 40, range: [1, 500],
    description: 'Maximum shifts allowed (Å) for the patch tracking alignment. Default=40.',
  },
  autoAli_max_shift_factor: {
    type: 'numeric', default: 1, range: [0, 10],
    description: 'The maximum shifts allowed are progressively reduced with iterations. Default=1.',
  },
  autoAli_refine_on_beads: {
    type: 'boolean', default: false, range: null,
    description: 'Whether the patch tracking alignment should be refined using gold beads. Substantially improves quality but is slower. Default=false.',
  },
  // ── ctf estimate ─────────────────────────────────────────────────────────
  SuperResolution: {
    type: 'boolean', default: false, range: null,
    description: 'Whether the stacks are super-sampled. If 1, emClarity will Fourier crop by factor 2, doubling the effective pixel size. Default=0.',
  },
  CUM_e_DOSE: {
    type: 'numeric', default: null, range: null,
    description: 'Total exposure in e/Å².',
  },
  defCutOff: {
    type: 'numeric', default: 7e-10, range: null,
    description: 'The power spectrum is considered from slightly before the first zero past the first zero to this cutoff, in meters (e.g. 7e-10).',
  },
  defEstimate: {
    type: 'numeric', default: 2.5e-6, range: null,
    description: 'Initial rough estimate of the defocus, in meters. With defWindow, defines the search window of defoci.',
  },
  defWindow: {
    type: 'numeric', default: 1.5e-6, range: null,
    description: 'Defocus window around defEstimate, in meters; e.g. defEstimate=2.5e-6 and defWindow=1.5e-6 tries 1e-6 to 4e-6.',
  },
  // ── templateSearch ────────────────────────────────────────────────────────
  Tmp_samplingRate: {
    type: 'numeric', default: null, range: [1, 20],
    description: 'Sampling (binning) at which the sub-region should be reconstructed for template matching (1 = no binning). Choose to give 8–12 Å/pix.',
  },
  Ali_samplingRate: {
    type: 'numeric', default: null, range: [1, 20],
    description: 'Current bin factor (1 = no binning). Sub-region tomograms at this binning must exist in the cache directory.',
  },
  applyExposureFilter: {
    type: 'boolean', default: true, range: null,
    description: 'Whether or not the exposure filter should be applied. If turned off, ensure it is also off during subtomogram averaging.',
  },
  particleRadius: {
    type: 'string', default: null, range: null,
    description: 'Particle radii in Å. Format is [Rx, Ry, Rz]. Defines a region around a cross-correlation peak to remove after a particle is selected.',
  },
  Ali_mRadius: {
    type: 'string', default: null, range: null,
    description: '[x, y, z] mask radius in Å. Used to pad/trim the template to this size during template search; must be larger than particleRadius.',
  },
  Peak_mRadius: {
    type: 'string', default: null, range: null,
    description: 'Radius of the cross-correlation peaks in Å. Format is [Rx, Ry, Rz]. Default = 0.75 × particleRadius.',
  },
  diameter_fraction_for_local_stats: {
    type: 'numeric', default: 1, range: null,
    description: 'TODO. Default=1.',
  },
  Tmp_angleSearch: {
    type: 'string', default: '[180,15,180,12]', range: null,
    description: 'Angular search in degrees. Format [Θout, Δout, Θin, Δout]. Example [180,15,180,12] = ±180° out-of-plane (15° steps) and ±180° in-plane (12° steps).',
  },
  Tmp_threshold: {
    type: 'numeric', default: null, range: null,
    description: 'Estimate of the number of particles. A threshold will be calculated to yield fewer false positives (estimated 10%).',
  },
  Override_threshold_and_return_N_peaks: {
    type: 'numeric', default: null, range: null,
    description: 'Overrides Tmp_threshold and selects the N highest scoring peaks.',
  },
  Tmp_targetSize: {
    type: 'string', default: '[512,512,512]', range: null,
    description: 'Size in pixels of the chunk to process. If sub-region is too big, split into chunks. Format [X, Y, Z]. Default=[512,512,512].',
  },
  rescale_mip: {
    type: 'numeric', default: 1, range: null,
    description: 'TODO. Default=1.',
  },
  // ── init ─────────────────────────────────────────────────────────────────
  fscGoldSplitOnTomos: {
    type: 'boolean', default: false, range: null,
    description: 'Whether particles from the same sub-regions should be kept in the same half-set (0/false) or distributed randomly. Recommend 0/false to avoid overlapping sub-regions.',
  },
  // ── ctf 3d ────────────────────────────────────────────────────────────────
  flg2dCTF: {
    type: 'boolean', default: false, range: null,
    description: 'Whether the CTF correction should correct for defocus gradients along the electron beam (thickness). If 1, only one z-section is used.',
  },
  // ── avg ───────────────────────────────────────────────────────────────────
  Ali_mCenter: {
    type: 'string', default: '[0,0,0]', range: null,
    description: '[x, y, z] shifts in Å relative to the center of the reconstruction. Positive shifts translate the Ali_mType mask to the right of the axis.',
  },
  Raw_classes_odd: {
    type: 'string', default: '[0; C1.*ones(2,1)]', range: null,
    description: 'Controls C symmetry of the first half-set. Should be "[0; <C>.*ones(2,1)]" where <C> is the central symmetry. Equivalent to [0; <C>; <C>].',
  },
  Raw_classes_eve: {
    type: 'string', default: '[0; C1.*ones(2,1)]', range: null,
    description: 'Controls C symmetry of the second half-set. Should be identical to Raw_classes_odd.',
  },
  Raw_className: {
    type: 'numeric', default: 0, range: null,
    description: 'Class ID for subtomogram averaging and alignment. Leave set to zero.',
  },
  flgClassify: {
    type: 'boolean', default: false, range: null,
    description: 'Whether or not this cycle is a classification cycle. Must be 0 if subtomogram alignment is the next step.',
  },
  minimumParticleVolume: {
    type: 'numeric', default: 0.1, range: [0, 1],
    description: 'Defines a minimum value for the fmask/fparticle ratio. Default=0.1.',
  },
  flgFscShapeMask: {
    type: 'boolean', default: true, range: null,
    description: 'Apply a soft mask based on the particle envelope before calculating the FSC. Highly recommended. Default=1.',
  },
  flgCCCcutoff: {
    type: 'numeric', default: 0, range: null,
    description: 'Particles with alignment score (CCC) below this value are ignored from reconstruction. Default=0.',
  },
  use_v2_SF3D: {
    type: 'boolean', default: true, range: null,
    description: 'Whether to use the new per-particle sampling function procedure. Default since emClarity 1.5.1.0. Default=1.',
  },
  // ── alignRaw ──────────────────────────────────────────────────────────────
  scaleCalcSize: {
    type: 'numeric', default: 1.5, range: [1, 4],
    description: 'Scale the box size used for calculations. Default=1.5.',
  },
  flgCenterRefCOM: {
    type: 'boolean', default: true, range: null,
    description: 'Whether the references should be shifted to their center-of-mass before starting the alignment. Default=1.',
  },
  Raw_angleSearch: {
    type: 'string', default: '[180,15,180,12]', range: null,
    description: 'Angular search in degrees. Format [Θout, Δout, Θin, Δout]. Example [180,15,180,12] = ±180° out-of-plane search (15° steps) and ±180° in-plane search (12° steps).',
  },
  Cls_className: {
    type: 'numeric', default: 0, range: null,
    description: 'Class ID for classification. Leave set to zero for now.',
  },
  // ── tomoCPR ───────────────────────────────────────────────────────────────
  Ali_Radius: {
    type: 'string', default: null, range: null,
    description: '[x, y, z] mask radius in Å. Must be large enough to contain the entire particle (larger than particleRadius), proper apodization, and avoid wraparound error in cross-correlation.',
  },
  min_res_for_ctf_fitting: {
    type: 'numeric', default: 10, range: [1, 50],
    description: 'Low-pass filter cutoff applied to tiles in Å. Replaces tomoCprLowPass in case of a defocus search. If the Nyquist limit is below this value, the defocus search is turned off. Default=10.',
  },
  particleMass: {
    type: 'numeric', default: null, range: null,
    description: 'Rough estimate of the particle mass in MDa. Used to set the number of particles per patch. Smaller particles give less reliable alignments, so more are included per patch.',
  },
  // ── pca ───────────────────────────────────────────────────────────────────
  Cls_samplingRate: {
    type: 'numeric', default: null, range: [1, 20],
    description: 'Current binning factor (1 = no binning). Sub-region tomograms at this binning must be reconstructed in cache/.',
  },
  Cls_mType: {
    type: 'string', default: 'sphere', range: null,
    description: 'Type of mask to use for the PCA; "cylinder", "sphere", or "rectangle".',
  },
  Cls_mCenter: {
    type: 'string', default: '[0,0,0]', range: null,
    description: '[x, y, z] shifts in Å to use for the PCA. Relative to the center of the reconstruction.',
  },
  Cls_Radius: {
    type: 'string', default: null, range: null,
    description: '[x, y, z] mask radius in Å to use for the PCA.',
  },
  flgPcaShapeMask: {
    type: 'boolean', default: true, range: null,
    description: 'Calculate and apply a molecular mask to the difference maps. Calculated using the combined reference. Default=true.',
  },
  test_updated_bandpass: {
    type: 'boolean', default: false, range: null,
    description: 'If true, use band-pass filters to calculate the length scales. Default=0/false.',
  },
  pcaScaleSpace: {
    type: 'string', default: null, range: null,
    description: 'Length scales (resolution bands) in Å for the PCA. If a vector, PCA is performed for each length scale.',
  },
  Pca_coeffs: {
    type: 'string', default: null, range: null,
    description: 'Selected principal axes for each length scale. Each length scale is a row. Use zeros to fill empty places.',
  },
  PcaGpuPull: {
    type: 'numeric', default: null, range: null,
    description: 'Controls how many difference maps are held on the GPU at any given time. The decomposition is calculated on the CPU but difference maps are computed on GPU.',
  },
}

// ---------------------------------------------------------------------------
// Schema lookup helpers
// ---------------------------------------------------------------------------

// Build schema lookup at module level — cast the static JSON directly to the
// canonical ParameterDefinition type (same shape as the backend schema response).
const SCHEMA_MAP = new Map<string, SchemaParam>(
  (rawSchema as { parameters: SchemaParam[] }).parameters.map((p) => [p.name, p]),
)

function resolveParam(name: string): SchemaParam {
  if (SCHEMA_MAP.has(name)) {
    return SCHEMA_MAP.get(name)!
  }
  const fb = PARAM_FALLBACKS[name]
  if (fb) {
    return {
      name,
      type: fb.type,
      required: false,
      default: fb.default,
      range: fb.range ?? null,
      n_elements: null,
      allowed_values: null,
      deprecated_name: null,
      description: fb.description,
      category: 'metadata',
    }
  }
  // Minimal fallback
  return {
    name,
    type: 'string',
    required: false,
    default: null,
    range: null,
    n_elements: null,
    allowed_values: null,
    deprecated_name: null,
    description: `Parameter: ${name}`,
    category: 'metadata',
  }
}

// ---------------------------------------------------------------------------
// Tab definitions – sourced from tutorial Tables 3-12 + Section 15
// ---------------------------------------------------------------------------

const ACTION_TABS: ActionTabDef[] = [
  // ─────────────────────────────────────────────────────────────────────────
  // Tab 1 – Section 5: Align Tilt-Series (Table 3: autoAlign)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'autoAlign',
    label: 'Align Tilt-Series',
    shortLabel: 'Align TS',
    tutorialSection: 5,
    command: 'autoAlign',
    objectives:
      'Find an initial alignment for the raw tilt-series: tilt, rotation, and shift for ' +
      'each image within the series. After alignment, the tilt-axis must be parallel to ' +
      'the y-axis. This alignment can be refined later using particle positions (tomoCPR).',
    commandSignature: 'emClarity autoAlign <param> <stack> <rawtlt> <rot> [views_to_remove]',
    keyOutputs: [
      'fixedStacks/<prefix>_3dfind.ali — aligned tilt-series',
      'fixedStacks/<prefix>_binX.ali — binned aligned stack',
      'emC_autoAlign_<prefix>/ — log directory with alignment residuals',
    ],
    notes:
      'Requires IMOD (tilt and tiltalign). Works with or without gold beads. ' +
      'If no beads are present, patch-tracking alignment is used without bead refinement.',
    params: [
      // Required (*)
      { name: 'autoAli_max_resolution',         group: 'Alignment settings', optional: false },
      { name: 'autoAli_min_sampling_rate',      group: 'Alignment settings', optional: false },
      { name: 'autoAli_max_sampling_rate',      group: 'Alignment settings', optional: false },
      { name: 'autoAli_refine_on_beads',        group: 'Bead refinement',  optional: false },
      // Expert options
      { name: 'autoAli_iterations_per_bin',     group: 'Patch tracking',   optional: true },
      { name: 'autoAli_n_iters_no_rotation',    group: 'Patch tracking',   optional: true },
      { name: 'autoAli_patch_size_factor',      group: 'Patch tracking',   optional: true },
      { name: 'autoAli_patch_tracking_border',  group: 'Patch tracking',   optional: true },
      { name: 'autoAli_patch_overlap',          group: 'Patch tracking',   optional: true },
      { name: 'autoAli_max_shift_in_angstroms', group: 'Patch tracking',   optional: true },
      { name: 'autoAli_max_shift_factor',       group: 'Patch tracking',   optional: true },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 2 – Section 6: Estimate CTF (Table 4: ctf estimate)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'ctfEstimate',
    label: 'Estimate CTF',
    shortLabel: 'CTF Est.',
    tutorialSection: 6,
    command: 'ctf estimate',
    objectives:
      'Two main objectives: (1) Create aligned, optionally bead-erased, exposure-weighted stacks. ' +
      '(2) Estimate the defocus of each view (two defoci + astigmatism angle per view). ' +
      'The resulting stacks are used to compute tomograms at later stages.',
    commandSignature: 'emClarity ctf estimate <param> <prefix> [views_to_remove]',
    keyOutputs: [
      'aliStacks/<prefix>_ali1.fixed — aligned bead-erased stack',
      'fixedStacks/ctf/<prefix>_ali1_psRadial_1.pdf — radial average of power spectrum',
      'fixedStacks/ctf/<prefix>_ccFIT.pdf — cross-correlation score vs defocus',
      'fixedStacks/ctf/<prefix>_ali1_ctf.tlt — tilt-series CTF metadata',
    ],
    params: [
      // Sampling (required *)
      { name: 'SuperResolution',       group: 'Sampling',            optional: false },
      // Fiducials (optional)
      { name: 'erase_beads_after_ctf', group: 'Fiducials',           optional: true },
      // Tilt-scheme (required *)
      { name: 'CUM_e_DOSE',            group: 'Tilt-scheme',         optional: false },
      { name: 'doseAtMinTilt',         group: 'Tilt-scheme',         optional: false },
      { name: 'oneOverCosineDose',     group: 'Tilt-scheme',         optional: false },
      { name: 'startingAngle',         group: 'Tilt-scheme',         optional: false },
      { name: 'startingDirection',     group: 'Tilt-scheme',         optional: false },
      { name: 'doseSymmetricIncrement',group: 'Tilt-scheme',         optional: false },
      // Defocus estimate (expert/required *)
      { name: 'defCutOff',             group: 'Defocus estimate',    optional: false },
      { name: 'defEstimate',           group: 'Defocus estimate',    optional: false },
      { name: 'defWindow',             group: 'Defocus estimate',    optional: false },
      { name: 'deltaZTolerance',       group: 'Defocus estimate',    optional: false },
      { name: 'zShift',                group: 'Defocus estimate',    optional: false },
      { name: 'ctfMaxNumberOfTiles',   group: 'Defocus estimate',    optional: false },
      { name: 'ctf_tile_size',         group: 'Defocus estimate',    optional: false },
      { name: 'paddedSize',            group: 'Defocus estimate',    optional: false },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 3 – Section 7: Select Sub-regions (Table 5: recon.coords)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'selectSubregions',
    label: 'Select Sub-regions',
    shortLabel: 'Sub-regions',
    tutorialSection: 7,
    command: './recScript2.sh',
    objectives:
      'Select sub-regions of interest from the tilt-series field of view. Sub-regions speed ' +
      'up processing and reduce memory usage. They can be changed until the project is ' +
      'initialized (init). Each sub-region is defined by 6 boundary points.',
    commandSignature:
      './recScript2.sh -1          # Generate full-FOV tomograms\n' +
      './recScript2.sh <prefix>    # Convert .mod to recon.coords',
    keyOutputs: [
      'bin10/<prefix>_bin10.rec — full-FOV tomogram for sub-region selection',
      'recon/<prefix>_recon.coords — sub-region boundary coordinates',
    ],
    notes:
      'Use 3dmod to open the bin10 tomogram and define sub-region boundaries in Model mode. ' +
      'Each sub-region requires 6 points: x_min, x_max, y_min, y_max, z_min, z_max. ' +
      'This step does NOT use a parameter file — it uses the recScript2.sh shell script.',
    params: [
      // Table 5 fields (recon.coords format — informational, not a param file)
      { name: 'super_sample', group: 'Reference parameters', optional: false },
      { name: 'expand_lines', group: 'Reference parameters', optional: false },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 4 – Section 8: Pick Particles (Table 6: templateSearch)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'templateSearch',
    label: 'Pick Particles',
    shortLabel: 'Pick',
    tutorialSection: 8,
    command: 'templateSearch',
    objectives:
      'Pick particles (subtomograms) using template matching. Each particle is described by ' +
      'its x, y, z coordinates and φ, θ, ψ Euler angles. Requires a template (reference volume) ' +
      'at the same pixel size as the reconstructed tomogram.',
    commandSignature:
      'emClarity ctf 3d <param> templateSearch   # Generate tomograms\n' +
      'emClarity templateSearch <param> <prefix> <region> <template> <symmetry> <GPU>',
    keyOutputs: [
      'convmap_wedgeType_2_binX/<prefix>_<region>_binX_convmap.mrc — cumulative correlation map',
      'convmap_wedgeType_2_binX/<prefix>_<region>_binX.mod — 3D IMOD model of selected peaks',
      '→ Rename to convmap/ before running init',
    ],
    notes:
      'Prepare template first: emClarity rescale <in> <out> <inPixel> <outPixel> <method>. ' +
      'After reviewing results in 3dmod, rename the output directory to convmap/.',
    params: [
      // Sampling (required *)
      { name: 'SuperResolution',                      group: 'Sampling',               optional: false },
      { name: 'Tmp_samplingRate',                     group: 'Sampling',               optional: false },
      // Tomogram reconstruction (mixed)
      { name: 'erase_beads_after_ctf',                group: 'Tomogram reconstruction', optional: true },
      { name: 'applyExposureFilter',                  group: 'Tomogram reconstruction', optional: true },
      { name: 'super_sample',                         group: 'Tomogram reconstruction', optional: false },
      { name: 'expand_lines',                         group: 'Tomogram reconstruction', optional: false },
      { name: 'whitenPS',                             group: 'Tomogram reconstruction', optional: false },
      // Particle (required *)
      { name: 'particleRadius',                       group: 'Particle',               optional: false },
      { name: 'Ali_mRadius',                          group: 'Particle',               optional: false },
      { name: 'Peak_mType',                           group: 'Particle',               optional: true },
      { name: 'Peak_mRadius',                         group: 'Particle',               optional: true },
      { name: 'diameter_fraction_for_local_stats',    group: 'Particle',               optional: true },
      // Template matching (required *)
      { name: 'symmetry',                             group: 'Template matching',       optional: false },
      { name: 'Tmp_angleSearch',                      group: 'Template matching',       optional: false },
      { name: 'Tmp_threshold',                        group: 'Template matching',       optional: false },
      { name: 'Override_threshold_and_return_N_peaks',group: 'Template matching',       optional: true },
      { name: 'Tmp_targetSize',                       group: 'Template matching',       optional: true },
      { name: 'Tmp_bandpass',                         group: 'Template matching',       optional: true },
      { name: 'rescale_mip',                          group: 'Template matching',       optional: true },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 5 – Section 9: Initialize Project (Table 7: init)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'init',
    label: 'Initialize Project',
    shortLabel: 'Init',
    tutorialSection: 9,
    command: 'init',
    objectives:
      'Create the project metadata that will be used throughout processing. ' +
      'Grabs: (1) sub-region coordinates from recon/<prefix>.coords, ' +
      '(2) tilt-series CTF from fixedStacks/ctf/<prefix>_ali1_ctf.tlt, ' +
      '(3) particle coordinates from convmap/<prefix>_<nb>_<bin>.csv. ' +
      'Once run, these source files are ignored and metadata is fixed.',
    commandSignature: 'emClarity init <param>',
    keyOutputs: [
      '<subTomoMeta>.mat — project metadata file',
      'Terminal output: total particle count and counts per sub-region (before/after cleaning)',
    ],
    notes:
      'This step should only take a few seconds. ' +
      'If you need to modify sub-region coordinates or particle picks after init, ' +
      'you must re-run init.',
    params: [
      // Required (*)
      { name: 'subTomoMeta',         group: 'Project',  optional: false },
      { name: 'Tmp_samplingRate',    group: 'Project',  optional: false },
      { name: 'fscGoldSplitOnTomos', group: 'Project',  optional: false },
      // Optional
      { name: 'lowResCut',           group: 'Project',  optional: true },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 6 – Section 10: Reconstruct Tomograms (Table 8: ctf 3d)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'ctf3d',
    label: 'Reconstruct Tomograms',
    shortLabel: 'Recon',
    tutorialSection: 10,
    command: 'ctf 3d',
    objectives:
      'Reconstruct tomograms for particle extraction and averaging. ' +
      'Accounts for the defocus gradient perpendicular to the tilt-axis and through the ' +
      'sample thickness (Ewald sphere curvature). Each projection is Fourier transformed, ' +
      'multiplied by its measured CTF, then inverse-transformed. Views are weighted by ' +
      'cumulative electron dose.',
    commandSignature: 'emClarity ctf 3d <param>',
    keyOutputs: [
      'cache/<prefix>_binX.rec — CTF-corrected tomogram reconstruction',
      'cache/ — binned tilt-series and reconstructions',
    ],
    notes:
      'If cache/ already contains reconstructions at this binning (Ali_samplingRate), ' +
      'emClarity will skip them. Remove existing reconstructions to force re-computation.',
    params: [
      // Sampling settings (required *)
      { name: 'SuperResolution',       group: 'Sampling',            optional: false },
      { name: 'Ali_samplingRate',      group: 'Sampling',            optional: false },
      // CTF correction (required *)
      { name: 'useSurfaceFit',         group: 'CTF correction',      optional: false },
      { name: 'flg2dCTF',              group: 'CTF correction',      optional: false },
      // Others (optional + expert *)
      { name: 'erase_beads_after_ctf', group: 'Others',              optional: true },
      { name: 'applyExposureFilter',   group: 'Others',              optional: true },
      { name: 'super_sample',          group: 'Others',              optional: false },
      { name: 'expand_lines',          group: 'Others',              optional: false },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 7 – Section 11: Subtomogram Averaging (Table 9: avg)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'avg',
    label: 'Subtomogram Averaging',
    shortLabel: 'Average',
    tutorialSection: 11,
    command: 'avg',
    objectives:
      'Calculate subtomogram averages (one per half-set). A volume-normalized single-particle ' +
      'Wiener (SPW) filter minimizes reconstruction error by applying an optimal (low-pass) ' +
      'filter and correcting for systematic changes to the signal imposed by the microscope ' +
      'and image processing algorithms.',
    commandSignature: 'emClarity avg <param> <cycle_nb> RawAlignment',
    keyOutputs: [
      'cycle<NNN>_<project>_class0_REF_EVE.mrc — even half-map',
      'cycle<NNN>_<project>_class0_REF_ODD.mrc — odd half-map',
      'FSC/cycle<NNN>_<project>_Raw-1-fsc_GLD.pdf — FSC curve',
      'FSC/cycle<NNN>_<project>_Raw-1-fsc_GLD.txt — FSC values (resolution + CCs)',
    ],
    params: [
      // Sampling (required *)
      { name: 'SuperResolution',      group: 'Sampling',               optional: false },
      { name: 'Ali_samplingRate',     group: 'Sampling',               optional: false },
      // Mask (required *)
      { name: 'Ali_mType',            group: 'Mask',                   optional: false },
      { name: 'particleRadius',       group: 'Mask',                   optional: false },
      { name: 'Ali_mRadius',          group: 'Mask',                   optional: false },
      { name: 'Ali_mCenter',          group: 'Mask',                   optional: false },
      { name: 'scaleCalcSize',        group: 'Mask',                   optional: false },
      // Symmetry (required *)
      { name: 'Raw_classes_odd',      group: 'Symmetry',               optional: false },
      { name: 'Raw_classes_eve',      group: 'Symmetry',               optional: false },
      { name: 'symmetry',             group: 'Symmetry',               optional: true },
      // Fourier shell correlation (required *)
      { name: 'flgCones',             group: 'Fourier shell correlation', optional: false },
      { name: 'minimumParticleVolume',group: 'Fourier shell correlation', optional: false },
      { name: 'flgFscShapeMask',      group: 'Fourier shell correlation', optional: false },
      { name: 'shape_mask_test',      group: 'Fourier shell correlation', optional: true },
      { name: 'shape_mask_lowpass',   group: 'Fourier shell correlation', optional: true },
      { name: 'shape_mask_threshold', group: 'Fourier shell correlation', optional: true },
      // Others (required *)
      { name: 'subTomoMeta',          group: 'Others',                 optional: false },
      { name: 'Raw_className',        group: 'Others',                 optional: false },
      { name: 'Fsc_bfactor',          group: 'Others',                 optional: false },
      { name: 'flgClassify',          group: 'Others',                 optional: false },
      { name: 'flgCutOutVolumes',     group: 'Others',                 optional: false },
      { name: 'flgQualityWeight',     group: 'Others',                 optional: false },
      { name: 'flgCCCcutoff',         group: 'Others',                 optional: false },
      { name: 'use_v2_SF3D',          group: 'Others',                 optional: false },
      { name: 'mtf_value',            group: 'Others',                 optional: false },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 8 – Section 12: Subtomogram Alignment (Table 10: alignRaw)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'alignRaw',
    label: 'Subtomogram Alignment',
    shortLabel: 'Align',
    tutorialSection: 12,
    command: 'alignRaw',
    objectives:
      'Estimate φ, θ, ψ rotations and x, y, z translations between references and each ' +
      'particle by maximising the constrained cross-correlation (CCC). The references result ' +
      'from the average of transformed particles, so averaging and alignment should be run ' +
      'until convergence.',
    commandSignature: 'emClarity alignRaw <param> <cycle_nb>',
    keyOutputs: [
      'alignResume/ — alignment results per sub-region (rotation + shifts + CCC score)',
      'Metadata updated with new particle orientations',
    ],
    notes:
      'Sub-regions are loaded and processed independently. emClarity will not re-run alignment ' +
      'for a sub-region if alignResume/ results already exist for it. Run multiple instances ' +
      'on different sub-regions in parallel for speed.',
    params: [
      // Sampling (required *)
      { name: 'SuperResolution',  group: 'Sampling',       optional: false },
      { name: 'Ali_samplingRate', group: 'Sampling',       optional: false },
      // Mask (required *)
      { name: 'Ali_mType',        group: 'Mask',           optional: false },
      { name: 'particleRadius',   group: 'Mask',           optional: false },
      { name: 'Ali_mRadius',      group: 'Mask',           optional: false },
      { name: 'Ali_mCenter',      group: 'Mask',           optional: false },
      { name: 'scaleCalcSize',    group: 'Mask',           optional: false },
      { name: 'Peak_mRadius',     group: 'Mask',           optional: true },
      { name: 'flgCenterRefCOM',  group: 'Mask',           optional: true },
      // Symmetry (required *)
      { name: 'Raw_classes_odd',  group: 'Symmetry',       optional: false },
      { name: 'Raw_classes_eve',  group: 'Symmetry',       optional: false },
      { name: 'symmetry',         group: 'Symmetry',       optional: true },
      // Angular search (required *)
      { name: 'Raw_angleSearch',  group: 'Angular search', optional: false },
      // Others (required *)
      { name: 'subTomoMeta',      group: 'Others',         optional: false },
      { name: 'Raw_className',    group: 'Others',         optional: false },
      { name: 'Cls_className',    group: 'Others',         optional: false },
      { name: 'Fsc_bfactor',      group: 'Others',         optional: false },
      { name: 'flgClassify',      group: 'Others',         optional: false },
      { name: 'use_v2_SF3D',      group: 'Others',         optional: false },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 9 – Section 13: Tilt-Series Refinement (Table 11: tomoCPR)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'tomoCPR',
    label: 'Tilt-Series Refinement',
    shortLabel: 'TomoCPR',
    tutorialSection: 13,
    command: 'tomoCPR',
    objectives:
      'Refine tilt-series alignment using particle positions and subtomogram averages as ' +
      'fiducial markers. The subtomogram average is placed at each particle position in the ' +
      'tomogram, re-projected to a tilt-series, and aligned locally to the raw data. This ' +
      'defines a new fiducial model for tiltalign to refine tilt-series alignment.',
    commandSignature:
      'emClarity tomoCPR <param> <cycle_nb>\n' +
      'emClarity ctf update <param> <cycle_nb>   # Apply updated alignment',
    keyOutputs: [
      'mapBack<n>/ — tiltalign outputs from the n-th tomoCPR run',
      'aliStacks/<prefix>_ali<n+1>.fixed — updated aligned tilt-series',
      'fixedStacks/ctf/<prefix>_ali<n+1>_ctf.tlt — updated CTF metadata',
    ],
    notes:
      'Optional step. Run after avg or alignRaw. ' +
      'tomoCPR does NOT update the aligned tilt-series automatically — ' +
      'you must also run "emClarity ctf update" to apply the refined alignment.',
    params: [
      // Sampling (required *)
      { name: 'SuperResolution',         group: 'Sampling',              optional: false },
      { name: 'Ali_samplingRate',        group: 'Sampling',              optional: false },
      // Fiducial alignment (required *)
      { name: 'Ali_mType',               group: 'Fiducial alignment',    optional: false },
      { name: 'particleRadius',          group: 'Fiducial alignment',    optional: false },
      { name: 'Ali_Radius',              group: 'Fiducial alignment',    optional: false },
      { name: 'Ali_mCenter',             group: 'Fiducial alignment',    optional: false },
      { name: 'tomoCprLowPass',          group: 'Fiducial alignment',    optional: true },
      { name: 'tomo_cpr_defocus_refine', group: 'Fiducial alignment',    optional: false },
      { name: 'tomo_cpr_defocus_range',  group: 'Fiducial alignment',    optional: false },
      { name: 'tomo_cpr_defocus_step',   group: 'Fiducial alignment',    optional: false },
      { name: 'min_res_for_ctf_fitting', group: 'Fiducial alignment',    optional: false },
      { name: 'peak_mask_fraction',      group: 'Fiducial alignment',    optional: true },
      { name: 'Peak_mType',              group: 'Fiducial alignment',    optional: true },
      { name: 'Peak_mRadius',            group: 'Fiducial alignment',    optional: true },
      // Tilt-series alignment (required *)
      { name: 'particleMass',            group: 'Tilt-series alignment', optional: false },
      { name: 'tomoCPR_random_subset',   group: 'Tilt-series alignment', optional: true },
      { name: 'k_factor_scaling',        group: 'Tilt-series alignment', optional: true },
      { name: 'rot_option_global',       group: 'Tilt-series alignment', optional: true },
      { name: 'rot_option_local',        group: 'Tilt-series alignment', optional: true },
      { name: 'rot_default_grouping_local',group: 'Tilt-series alignment',optional: true },
      { name: 'mag_option_global',       group: 'Tilt-series alignment', optional: true },
      { name: 'mag_option_local',        group: 'Tilt-series alignment', optional: true },
      { name: 'mag_default_grouping_global',group: 'Tilt-series alignment',optional: true },
      { name: 'mag_default_grouping_local', group: 'Tilt-series alignment',optional: true },
      { name: 'tilt_option_global',      group: 'Tilt-series alignment', optional: true },
      { name: 'tilt_option_local',       group: 'Tilt-series alignment', optional: true },
      { name: 'tilt_default_grouping_global',group: 'Tilt-series alignment',optional: true },
      { name: 'tilt_default_grouping_local', group: 'Tilt-series alignment',optional: true },
      { name: 'min_overlap',             group: 'Tilt-series alignment', optional: true },
      { name: 'shift_z_to_to_centroid',  group: 'Tilt-series alignment', optional: true },
      // Others (required *)
      { name: 'subTomoMeta',             group: 'Others',                optional: false },
      { name: 'Raw_className',           group: 'Others',                optional: false },
      { name: 'Raw_classes_odd',         group: 'Others',                optional: false },
      { name: 'Raw_classes_eve',         group: 'Others',                optional: false },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 10 – Section 14: Classification (Table 12: pca/cluster)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'classification',
    label: 'Classification',
    shortLabel: 'Classify',
    tutorialSection: 14,
    command: 'pca',
    objectives:
      'Analyse heterogeneity by comparing individual particles to the current subtomogram average. ' +
      'Dimensionality of differences is reduced by principal component analysis (SVD) at multiple ' +
      'length scales. Singular vectors are concatenated into feature vectors and clustered ' +
      'with k-means or other algorithms.',
    commandSignature:
      'emClarity avg <param> <cycle_nb> RawAlignment   # Start new cycle first\n' +
      'emClarity pca <param> <cycle_nb> 0              # Compute PCA\n' +
      'emClarity cluster <param> <cycle_nb>            # Cluster results',
    keyOutputs: [
      '<project>_cycle<NNN>_ClassIDX.txt — class populations per requested clustering',
      'Class montage images for visual review',
      'FSC/<project>_cycle<NNN>_Cluster_cls*_REF_*.mrc — class averages',
    ],
    notes:
      'Optional step. Classifications are self-contained cycles; ' +
      'run them between any two averaging cycles. Set flgClassify=1 in avg and alignRaw ' +
      'for the classification cycle.',
    params: [
      // Sampling (required *)
      { name: 'SuperResolution',        group: 'Sampling',  optional: false },
      { name: 'Cls_samplingRate',       group: 'Sampling',  optional: false },
      { name: 'Ali_samplingRate',       group: 'Sampling',  optional: false },
      // Masks (required *)
      { name: 'Ali_mType',              group: 'Masks',     optional: false },
      { name: 'Cls_mType',              group: 'Masks',     optional: false },
      { name: 'Ali_Radius',             group: 'Masks',     optional: false },
      { name: 'Cls_Radius',             group: 'Masks',     optional: false },
      { name: 'Ali_mCenter',            group: 'Masks',     optional: false },
      { name: 'Cls_mCenter',            group: 'Masks',     optional: false },
      { name: 'flgPcaShapeMask',        group: 'Masks',     optional: true },
      { name: 'test_updated_bandpass',  group: 'Masks',     optional: true },
      // PCA (required *)
      { name: 'pcaScaleSpace',          group: 'PCA',       optional: false },
      { name: 'Pca_randSubset',         group: 'PCA',       optional: false },
      { name: 'Pca_maxEigs',            group: 'PCA',       optional: false },
      // Clustering (required *)
      { name: 'Pca_coeffs',             group: 'Clustering',optional: false },
      { name: 'Pca_clusters',           group: 'Clustering',optional: false },
      { name: 'Pca_distMeasure',        group: 'Clustering',optional: true },
      { name: 'n_replicates',           group: 'Clustering',optional: true },
      // Others (required *)
      { name: 'PcaGpuPull',             group: 'Others',    optional: false },
      { name: 'flgClassify',            group: 'Others',    optional: false },
      { name: 'subTomoMeta',            group: 'Others',    optional: false },
      { name: 'flgCutOutVolumes',       group: 'Others',    optional: true },
      { name: 'scaleCalcSize',          group: 'Others',    optional: false },
      { name: 'use_v2_SF3D',            group: 'Others',    optional: true },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  // Tab 11 – Section 15: Final Reconstruction (Table 9: avg FinalAlignment)
  // ─────────────────────────────────────────────────────────────────────────
  {
    id: 'finalRecon',
    label: 'Final Reconstruction',
    shortLabel: 'Final',
    tutorialSection: 15,
    command: 'avg FinalAlignment',
    objectives:
      'Produce the final reconstruction by combining two half-sets. emClarity reconstructs ' +
      'the half-maps, calculates the FSC, aligns the second FSC group to the first using the ' +
      'between-half-set transform, re-extracts and combines the two maps, then filters using ' +
      'the calculated FSC. Uses the same parameters as subtomogram averaging (Table 9).',
    commandSignature:
      'emClarity avg <param> <cycle_nb> RawAlignment    # Reconstruct half-maps + FSC\n' +
      'emClarity avg <param> <cycle_nb> FinalAlignment  # Final filtered reconstruction',
    keyOutputs: [
      'cycle<NNN>_<project>_class0_REF_EVE.mrc — even half-map',
      'cycle<NNN>_<project>_class0_REF_ODD.mrc — odd half-map',
      'Final filtered map (one per fsc_bfactor value)',
      'FSC/<project>_cycle<NNN>_*_fsc_GLD.pdf — final FSC curve',
    ],
    notes:
      'Same parameters as subtomogram averaging (Section 11 / Table 9). ' +
      'The key difference is fsc_bfactor, which can be a vector of B-factors: emClarity ' +
      'will produce one final reconstruction per value. ' +
      'Assumes SuperResolution=0.',
    params: [
      // Same groups/params as avg (Tab 7) — reused for Final Reconstruction
      { name: 'SuperResolution',      group: 'Sampling',               optional: false },
      { name: 'Ali_samplingRate',     group: 'Sampling',               optional: false },
      { name: 'Ali_mType',            group: 'Mask',                   optional: false },
      { name: 'particleRadius',       group: 'Mask',                   optional: false },
      { name: 'Ali_mRadius',          group: 'Mask',                   optional: false },
      { name: 'Ali_mCenter',          group: 'Mask',                   optional: false },
      { name: 'scaleCalcSize',        group: 'Mask',                   optional: false },
      { name: 'Raw_classes_odd',      group: 'Symmetry',               optional: false },
      { name: 'Raw_classes_eve',      group: 'Symmetry',               optional: false },
      { name: 'symmetry',             group: 'Symmetry',               optional: true },
      { name: 'flgCones',             group: 'Fourier shell correlation', optional: false },
      { name: 'minimumParticleVolume',group: 'Fourier shell correlation', optional: false },
      { name: 'flgFscShapeMask',      group: 'Fourier shell correlation', optional: false },
      { name: 'shape_mask_test',      group: 'Fourier shell correlation', optional: true },
      { name: 'shape_mask_lowpass',   group: 'Fourier shell correlation', optional: true },
      { name: 'shape_mask_threshold', group: 'Fourier shell correlation', optional: true },
      { name: 'subTomoMeta',          group: 'Others',                 optional: false },
      { name: 'Raw_className',        group: 'Others',                 optional: false },
      { name: 'Fsc_bfactor',          group: 'Others',                 optional: false },
      { name: 'flgClassify',          group: 'Others',                 optional: false },
      { name: 'flgCutOutVolumes',     group: 'Others',                 optional: false },
      { name: 'flgQualityWeight',     group: 'Others',                 optional: false },
      { name: 'flgCCCcutoff',         group: 'Others',                 optional: false },
      { name: 'use_v2_SF3D',          group: 'Others',                 optional: false },
      { name: 'mtf_value',            group: 'Others',                 optional: false },
    ],
  },
]

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Collapsible accordion section for parameter groups. */
interface AccordionSectionProps {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}

function AccordionSection({ title, children, defaultOpen = true }: AccordionSectionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors text-left"
        aria-expanded={open}
      >
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">{title}</span>
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

/** Renders a single parameter field based on its schema type. */
interface ParameterFieldProps {
  param: SchemaParam
  value: string
  onChange: (name: string, value: string) => void
}

function ParameterField({ param, value, onChange }: ParameterFieldProps) {
  const id = `param-${param.name}`
  const displayDefault = param.default !== null ? String(param.default) : ''
  const placeholder = displayDefault || (param.type === 'string' ? '…' : '0')

  return (
    <div className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 items-start">
      <div className="min-w-0">
        <label
          htmlFor={id}
          className="block text-xs font-medium text-gray-800 dark:text-gray-200 font-mono"
          title={param.description}
        >
          {param.name}
          {param.required && <span className="ml-0.5 text-red-500" aria-label="required">*</span>}
        </label>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 leading-snug line-clamp-2">
          {param.description}
        </p>
      </div>

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

/** Right-side help panel for a tab. */
interface HelpPanelProps {
  tab: ActionTabDef
}

function HelpPanel({ tab }: HelpPanelProps) {
  return (
    <div className="flex flex-col gap-5 text-sm">
      {/* Section header */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <BookOpen className="h-4 w-4 text-blue-500 shrink-0" />
          <span className="text-xs font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">
            Tutorial Section {tab.tutorialSection}
          </span>
        </div>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">{tab.label}</h3>
        <p className="mt-1.5 text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
          {tab.objectives}
        </p>
      </div>

      {/* Command signature */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5">
          Command
        </h4>
        <pre className="bg-gray-50 dark:bg-gray-800 rounded-md px-3 py-2 text-xs font-mono text-gray-800 dark:text-gray-200 whitespace-pre-wrap overflow-x-auto leading-relaxed border border-gray-200 dark:border-gray-700">
          {tab.commandSignature}
        </pre>
      </div>

      {/* Key outputs */}
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5">
          Key Outputs
        </h4>
        <ul className="space-y-1.5">
          {tab.keyOutputs.map((output, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400 dark:bg-blue-500" />
              <span className="text-xs text-gray-600 dark:text-gray-400 font-mono leading-relaxed">
                {output}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Notes */}
      {tab.notes && (
        <div className="rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 px-3 py-2.5">
          <div className="flex items-start gap-2">
            <Info className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
              {tab.notes}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

/** Bottom run bar: Run Profile dropdown + Start Command button. */
interface RunBarProps {
  command: string
  onRun: () => void
  isRunning: boolean
  runMessage: string | null
}

function RunBar({ command, onRun, isRunning, runMessage }: RunBarProps) {
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const { profiles, selectedId, select, loading, loadError, saveError } = useRunProfiles(projectId ?? null)
  const isDemo = projectId === DEMO_PROJECT_ID

  // Brief visible feedback when a keyboard user activates the button while in demo mode.
  // Without this, pressing Enter produces a completely silent no-op for sighted keyboard users.
  const [demoBlocked, setDemoBlocked] = useState(false)
  const demoBlockedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (demoBlockedTimerRef.current !== null) clearTimeout(demoBlockedTimerRef.current)
    }
  }, [])

  const showDemoBlocked = useCallback(() => {
    if (demoBlockedTimerRef.current !== null) clearTimeout(demoBlockedTimerRef.current)
    setDemoBlocked(true)
    demoBlockedTimerRef.current = setTimeout(() => setDemoBlocked(false), 1500)
  }, [])

  return (
    <div className="flex items-center gap-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-4 py-3">
      <div className="flex items-center gap-2">
        <label
          htmlFor="run-profile"
          className="text-xs font-medium text-gray-600 dark:text-gray-400 whitespace-nowrap"
        >
          Run Profile:
        </label>
        <select
          id="run-profile"
          value={selectedId}
          onChange={(e) => select(e.target.value)}
          className="rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-xs text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          disabled={profiles.length === 0 || loading}
        >
          {loading ? (
            <option value="">Loading profiles…</option>
          ) : loadError ? (
            <option value="">Error loading profiles</option>
          ) : profiles.length === 0 ? (
            <option value="">No profiles — create one in Settings</option>
          ) : (
            profiles.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))
          )}
        </select>
        <button
          type="button"
          title="Manage run profiles in Settings"
          onClick={() => projectId !== null && navigate(`/project/${projectId}/settings`)}
          className="rounded p-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
          aria-label="Open Settings to manage run profiles"
        >
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </button>
      </div>

      <div className="flex-1 min-w-0">
        {saveError && (
          <p role="alert" className="text-xs text-red-600 dark:text-red-400 truncate">{saveError}</p>
        )}
        {runMessage && (
          <p
            className={`text-xs truncate ${
              runMessage.startsWith('\u2717')
                ? 'text-red-600 dark:text-red-400'
                : 'text-green-700 dark:text-green-400'
            }`}
            role={runMessage.startsWith('\u2717') ? 'alert' : 'status'}
            aria-live={runMessage.startsWith('\u2717') ? undefined : 'polite'}
          >
            {runMessage}
          </p>
        )}
      </div>

      {/*
       * Browsers do not show `title` tooltips on disabled buttons because
       * pointer events are suppressed on the button itself. Wrapping the button
       * in a <span> restores hover events so the tooltip is visible in demo mode.
       * The span is also `relative` so the keyboard-activated tooltip can be
       * absolutely positioned without shifting surrounding layout.
       */}
      <span
        title={isDemo ? 'Commands cannot be run in demo mode' : undefined}
        className="relative"
      >
        {/*
         * `aria-disabled` keeps the button in the tab order so keyboard users
         * can Tab onto it and hear the `aria-describedby` explanation. Native
         * `disabled` removes it from tab order entirely, making the description
         * unreachable (WCAG 2.1.1, 4.1.2). The click handler is a no-op when
         * aria-disabled is true.
         *
         * Hover styles are suppressed when the button is inert (isRunning or
         * isDemo) to avoid the contradictory "cursor=stop, color=go" signal.
         *
         * Keyboard users who press Enter/Space in demo mode receive a brief
         * visible tooltip via showDemoBlocked() — identical information to what
         * mouse users see on hover — satisfying WCAG 2.1.1 for sighted
         * keyboard-only users.
         */}
        <button
          type="button"
          onClick={isRunning || isDemo ? undefined : onRun}
          onKeyDown={(e) => {
            if ((e.key === 'Enter' || e.key === ' ') && isDemo) {
              e.preventDefault()
              showDemoBlocked()
            }
          }}
          aria-disabled={isRunning || isDemo}
          aria-describedby={isDemo ? 'run-demo-tooltip' : undefined}
          className={[
            'flex items-center gap-2 rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white shadow-sm',
            isRunning || isDemo
              ? 'cursor-not-allowed opacity-60'
              : 'hover:bg-blue-700 dark:hover:bg-blue-600',
            'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
            'dark:bg-blue-500 transition-colors',
          ].join(' ')}
        >
          <Play className="h-3.5 w-3.5" aria-hidden="true" />
          {isRunning ? 'Starting…' : `Start: ${command}`}
        </button>
        {isDemo && (
          <span
            id="run-demo-tooltip"
            role="tooltip"
            className={
              demoBlocked
                ? 'absolute right-0 top-full z-10 mt-1 whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-xs text-white shadow-lg dark:bg-gray-700'
                : 'sr-only'
            }
          >
            Commands cannot be run in demo mode
          </span>
        )}
        {/* Separate live region: content changes on keyboard activation so screen readers
            actually announce the message. aria-live on static text (CSS-toggled only)
            never fires — the DOM content must change for the announcement to trigger. */}
        <span aria-live="polite" className="sr-only">
          {demoBlocked ? 'Commands cannot be run in demo mode' : ''}
        </span>
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Viewer launcher
// ---------------------------------------------------------------------------

const VIEWER_PATH_KEY = 'emclarity_viewer_path'

interface ViewerLauncherProps {
  projectId: string
  isDemo: boolean
}

interface ProjectSettingsResponse {
  viewer_path: string | null
}

function ViewerLauncher({ projectId, isDemo }: ViewerLauncherProps) {
  const [viewerPath, setViewerPath] = useState<string>('')
  const [configOpen, setConfigOpen] = useState<boolean>(false)
  const [draftPath, setDraftPath] = useState<string>('')
  const [launching, setLaunching] = useState<boolean>(false)
  const [isSaving, setIsSaving] = useState<boolean>(false)
  const [message, setMessage] = useState<string | null>(null)
  const [projectDirectory, setProjectDirectory] = useState<string | null>(null)
  const [settingsLoading, setSettingsLoading] = useState<boolean>(true)
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const gearButtonRef = useRef<HTMLButtonElement>(null)

  // Read viewer_path from project settings API on mount, with one-time
  // migration from localStorage if the server value is empty.
  useEffect(() => {
    if (isDemo || !projectId) {
      setSettingsLoading(false)
      return
    }
    const controller = new AbortController()
    setSettingsLoading(true)
    setSettingsError(null)
    apiClient
      .get<ProjectSettingsResponse>(`/api/v1/projects/${projectId}/settings`, controller.signal)
      .then(async (data) => {
        const serverPath = data.viewer_path ?? ''
        const localPath = localStorage.getItem(VIEWER_PATH_KEY)

        // Migration: localStorage has a value, server does not → migrate
        // Capture projectId now to avoid using a stale closure value if the
        // component re-renders with a different project before the PATCH resolves.
        const capturedProjectId = projectId
        if (!serverPath && localPath) {
          try {
            const updated = await apiClient.patch<ProjectSettingsResponse>(
              `/api/v1/projects/${capturedProjectId}/settings`,
              { viewer_path: localPath },
            )
            localStorage.removeItem(VIEWER_PATH_KEY)
            const migrated = updated.viewer_path ?? ''
            setViewerPath(migrated)
            setDraftPath(migrated)
          } catch (migrationErr: unknown) {
            // Migration failed — fall back to localStorage value for now
            console.warn('[ViewerLauncher] Failed to migrate viewer path from localStorage to server:', migrationErr)
            setViewerPath(localPath)
            setDraftPath(localPath)
          }
        } else {
          // Server has a value, or nothing to migrate — use server value
          // Also clear localStorage if it still exists (migration already done or not needed)
          if (localPath !== null) {
            localStorage.removeItem(VIEWER_PATH_KEY)
          }
          setViewerPath(serverPath)
          setDraftPath(serverPath)
        }
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === 'AbortError') return
        const fallback = localStorage.getItem(VIEWER_PATH_KEY) ?? ''
        setViewerPath(fallback)
        setDraftPath(fallback)
        setSettingsError('Failed to load viewer settings from server')
        console.warn('[ViewerLauncher] Failed to fetch project settings:', err)
      })
      .finally(() => setSettingsLoading(false))
    return () => controller.abort()
  }, [isDemo, projectId])

  // Fetch the project directory so it can be forwarded to the viewer as an argument.
  // AbortController ensures a stale response from a previous projectId is discarded
  // when the project switches before the fetch completes.
  // Skip in demo mode — there is no real project record to fetch.
  useEffect(() => {
    if (isDemo || !projectId) return
    const controller = new AbortController()
    apiClient
      .get<{ directory: string }>(`/api/v1/projects/${projectId}`, controller.signal)
      .then((data) => setProjectDirectory(data.directory))
      .catch((err: unknown) => {
        // Non-fatal: viewer can still be launched without a directory argument.
        // Suppress AbortError — it is expected when the effect is cleaned up.
        if (err instanceof Error && err.name === 'AbortError') return
        // Log unexpected failures so they are visible in the console.
        console.warn('[ViewerLauncher] Failed to fetch project directory:', err)
      })
    return () => controller.abort()
  }, [isDemo, projectId])

  const handleLaunch = useCallback(async () => {
    if (!viewerPath) {
      setMessage('Set a viewer path first (click the gear icon)')
      return
    }
    setLaunching(true)
    setMessage(null)
    try {
      const args = projectDirectory ? [projectDirectory] : []
      const result = await apiClient.post<{ launched: boolean; pid: number }>(
        '/api/v1/viewer/launch',
        { viewer_path: viewerPath, args },
      )
      setMessage(`Viewer launched (PID ${result.pid})`)
    } catch (err: unknown) {
      let detail = 'Failed to launch viewer'
      if (err instanceof ApiError) {
        const body: unknown = err.body
        if (
          body !== null &&
          typeof body === 'object' &&
          'detail' in body &&
          typeof (body as Record<string, unknown>).detail === 'string'
        ) {
          detail = (body as { detail: string }).detail
        } else {
          detail = err.message
        }
      } else if (err instanceof Error) {
        detail = err.message
      }
      setMessage(`Error: ${detail}`)
    } finally {
      setLaunching(false)
    }
  }, [viewerPath, projectDirectory])

  const handleSavePath = useCallback(async () => {
    if (isSaving) return
    const trimmed = draftPath.trim()
    if (!isDemo && projectId) {
      setIsSaving(true)
      setMessage(null)
      try {
        await apiClient.patch<ProjectSettingsResponse>(
          `/api/v1/projects/${projectId}/settings`,
          { viewer_path: trimmed || null },
        )
      } catch (err: unknown) {
        let detail = 'Failed to save viewer path'
        if (err instanceof ApiError) {
          const body: unknown = err.body
          if (
            body !== null &&
            typeof body === 'object' &&
            'detail' in body &&
            typeof (body as Record<string, unknown>).detail === 'string'
          ) {
            detail = (body as { detail: string }).detail
          } else {
            detail = err.message
          }
        } else if (err instanceof Error) {
          detail = err.message
        }
        setMessage(`Error: ${detail}`)
        setIsSaving(false)
        return
      } finally {
        setIsSaving(false)
      }
    }
    setMessage(null)
    setViewerPath(trimmed)
    setSettingsError(null)
    setConfigOpen(false)
    gearButtonRef.current?.focus()
  }, [isSaving, draftPath, isDemo, projectId])

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-3 bg-gray-50 dark:bg-gray-800/30">
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={isDemo || launching || settingsLoading}
          onClick={() => { void handleLaunch() }}
          className="flex items-center gap-1.5 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
          aria-label="Open in Viewer — launches project in external viewer application"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          {settingsLoading ? 'Loading…' : launching ? 'Launching…' : 'Open in Viewer\u2026'}
        </button>
        <button
          ref={gearButtonRef}
          type="button"
          disabled={settingsLoading}
          onClick={() => setConfigOpen((v) => !v)}
          aria-expanded={configOpen}
          aria-controls="viewer-config-panel"
          className="rounded p-1.5 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Configure viewer path"
        >
          <Settings2 className="h-4 w-4" />
        </button>
      </div>
      {/* aria-live region ensures screen readers announce launch feedback */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="mt-1.5 text-xs text-gray-600 dark:text-gray-400 min-h-[1rem]"
      >
        {settingsError && <span className="text-amber-600 dark:text-amber-400">{settingsError}</span>}
        {settingsError && message && <span role="separator" aria-orientation="vertical" className="mx-1 select-none" aria-label=", "> </span>}
        {message}
      </div>
      {/* Always rendered so aria-controls="viewer-config-panel" references a valid DOM element.
          Inline style is used instead of the `hidden` HTML attribute because Tailwind v4's
          `flex` utility (applied via className) overrides the attribute-derived display:none,
          making the panel permanently visible. An inline style has higher cascade specificity
          than any class rule and reliably hides the panel when configOpen is false. */}
      <div id="viewer-config-panel" style={configOpen ? undefined : { display: 'none' }} className="mt-3 flex items-center gap-2">
        <input
          type="text"
          value={draftPath}
          onChange={(e) => setDraftPath(e.target.value)}
          placeholder="/usr/bin/3dmod"
          className="flex-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-xs font-mono text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          aria-label="External viewer executable path"
        />
        <button
          type="button"
          disabled={isSaving}
          onClick={() => { void handleSavePath() }}
          className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          {isSaving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          onClick={() => { setDraftPath(viewerPath); setConfigOpen(false); gearButtonRef.current?.focus() }}
          className="rounded border border-gray-300 dark:border-gray-600 px-2 py-1 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SnapshotHistoryDropdown
// ---------------------------------------------------------------------------

interface SnapshotHistoryDropdownProps {
  projectId: string
  isDemo: boolean
  onLoadSnapshot: (parameters: Record<string, string>) => void
}

function formatSnapshotDate(isoString: string): string {
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    }).format(new Date(isoString))
  } catch {
    return isoString
  }
}

function SnapshotHistoryDropdown({
  projectId,
  isDemo,
  onLoadSnapshot,
}: SnapshotHistoryDropdownProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [snapshots, setSnapshots] = useState<SnapshotListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadingSnapshotId, setLoadingSnapshotId] = useState<string | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setIsOpen(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  const handleToggle = useCallback(async () => {
    if (isOpen) {
      setIsOpen(false)
      return
    }
    setIsOpen(true)
    setLoading(true)
    setError(null)
    try {
      const result = await apiClient.get<SnapshotListResponse>(
        `/api/v1/projects/${projectId}/parameter-snapshots`,
      )
      setSnapshots(result.snapshots)
    } catch (err: unknown) {
      let detail = 'Failed to load snapshots'
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown> | null
        detail = (body && typeof body.detail === 'string') ? body.detail : err.statusText
      } else if (err instanceof Error) {
        detail = err.message
      }
      setError(detail)
    } finally {
      setLoading(false)
    }
  }, [isOpen, projectId])

  const handleSelectSnapshot = useCallback(async (snapshotId: string) => {
    setLoadingSnapshotId(snapshotId)
    try {
      const result = await apiClient.get<SnapshotDetailResponse>(
        `/api/v1/projects/${projectId}/parameter-snapshots/${snapshotId}`,
      )
      // Convert all parameter values to strings for the form
      const stringParams: Record<string, string> = {}
      for (const [key, value] of Object.entries(result.parameters)) {
        stringParams[key] = String(value ?? '')
      }
      onLoadSnapshot(stringParams)
      setIsOpen(false)
    } catch (err: unknown) {
      let detail = 'Failed to load snapshot'
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown> | null
        detail = (body && typeof body.detail === 'string') ? body.detail : err.statusText
      } else if (err instanceof Error) {
        detail = err.message
      }
      setError(detail)
    } finally {
      setLoadingSnapshotId(null)
    }
  }, [projectId, onLoadSnapshot])

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={isDemo ? undefined : handleToggle}
        disabled={isDemo}
        aria-label="Load parameters from a previous run"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <History className="h-4 w-4" />
        Load from previous run
      </button>

      {isOpen && (
        <div
          role="listbox"
          aria-label="Snapshot history"
          className="absolute left-0 top-full mt-1 w-80 max-h-64 overflow-y-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-md shadow-lg z-20"
        >
          {loading && (
            <div className="p-3 text-sm text-gray-500 dark:text-gray-400">Loading snapshots...</div>
          )}

          {error && (
            <div className="p-3 text-sm text-red-600 dark:text-red-400">{error}</div>
          )}

          {!loading && !error && snapshots.length === 0 && (
            <div className="p-3 text-sm text-gray-500 dark:text-gray-400">No previous snapshots found.</div>
          )}

          {!loading && !error && snapshots.map((snap) => {
            const truncatedFilename = snap.filename.length > 30
              ? snap.filename.slice(0, 27) + '...'
              : snap.filename
            return (
              <button
                key={snap.snapshot_id}
                type="button"
                role="option"
                aria-selected={false}
                aria-label={`Load snapshot ${snap.filename} from ${formatSnapshotDate(snap.created_at)}`}
                disabled={loadingSnapshotId === snap.snapshot_id}
                onClick={() => handleSelectSnapshot(snap.snapshot_id)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors border-b border-gray-100 dark:border-gray-700 last:border-b-0 disabled:opacity-50"
              >
                <div className="font-medium text-gray-800 dark:text-gray-200">
                  {formatSnapshotDate(snap.created_at)}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                  {truncatedFilename}
                </div>
                {loadingSnapshotId === snap.snapshot_id && (
                  <div className="text-xs text-blue-500 mt-0.5">Loading...</div>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ExportMButton
// ---------------------------------------------------------------------------

interface ExportMButtonProps {
  projectId: string
  isDemo: boolean
  currentParams: Record<string, string>
}

function ExportMButton({ projectId, isDemo, currentParams }: ExportMButtonProps) {
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const handleExport = useCallback(async () => {
    setLoading(true)
    setMessage(null)
    try {
      // Step 1: Save a snapshot of current parameters
      const snapshotResult = await apiClient.post<SnapshotResponse>(
        `/api/v1/projects/${projectId}/parameter-snapshots`,
        { parameters: currentParams },
      )

      if (!snapshotResult.snapshot_id) {
        throw new Error('Snapshot response missing snapshot_id')
      }

      // Step 2: Export to .m format
      const exportResult = await apiClient.post<ExportMResponse>(
        `/api/v1/projects/${projectId}/parameter-snapshots/${snapshotResult.snapshot_id}/export-m`,
      )

      setMessage(`Exported to: ${exportResult.m_file_path}`)
    } catch (err: unknown) {
      let detail = 'Export failed'
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown> | null
        detail = (body && typeof body.detail === 'string') ? body.detail : err.statusText
      } else if (err instanceof Error) {
        detail = err.message
      }
      setMessage(`Error: ${detail}`)
    } finally {
      setLoading(false)
    }
  }, [projectId, currentParams])

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={isDemo ? undefined : handleExport}
        disabled={loading || isDemo}
        aria-label="Export current parameters to .m file"
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Download className="h-4 w-4" />
        {loading ? 'Exporting...' : 'Export to .m file'}
      </button>
      {message && (
        <span className={`text-xs ${message.startsWith('Error:') ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
          {message}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Action tab content
// ---------------------------------------------------------------------------

interface ActionTabContentProps {
  tab: ActionTabDef
  values: Record<string, string>
  showExpert: boolean
  onValueChange: (name: string, value: string) => void
  onToggleExpert: () => void
  onRun: () => void
  isRunning: boolean
  runMessage: string | null
  projectId: string
  isDemo: boolean
}

function ActionTabContent({
  tab,
  values,
  showExpert,
  onValueChange,
  onToggleExpert,
  onRun,
  isRunning,
  runMessage,
  projectId,
  isDemo,
}: ActionTabContentProps) {
  // Resolve all params for this tab from schema / fallbacks
  const resolvedParams = useMemo(
    () => tab.params.map((pd) => ({ def: pd, schema: resolveParam(pd.name) })),
    [tab],
  )

  // Separate required (starred) from optional
  const visibleParams = resolvedParams.filter((p) => !p.def.optional)
  const optionalParams = resolvedParams.filter((p) => p.def.optional)

  // Group params into accordion sections
  function groupBySection(
    params: typeof resolvedParams,
  ): Map<string, typeof resolvedParams> {
    const groups = new Map<string, typeof resolvedParams>()
    for (const p of params) {
      const key = p.def.group
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(p)
    }
    return groups
  }

  const visibleGroups = useMemo(() => groupBySection(visibleParams), [visibleParams])
  const optionalGroups = useMemo(() => groupBySection(optionalParams), [optionalParams])

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Main content area */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left: Parameters panel */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 min-w-0">
          {/* Snapshot controls */}
          <div className="flex items-center gap-2 pb-3 border-b border-gray-200 dark:border-gray-700">
            <SnapshotHistoryDropdown
              projectId={projectId}
              isDemo={isDemo}
              onLoadSnapshot={(params) => {
                for (const [name, value] of Object.entries(params)) {
                  onValueChange(name, value)
                }
              }}
            />
            <ExportMButton
              projectId={projectId}
              isDemo={isDemo}
              currentParams={values}
            />
          </div>

          {/* Required parameters */}
          {Array.from(visibleGroups.entries()).map(([groupName, params]) => (
            <AccordionSection key={groupName} title={groupName} defaultOpen={true}>
              {params.map(({ def, schema }) => (
                <ParameterField
                  key={def.name}
                  param={schema}
                  value={values[def.name] ?? ''}
                  onChange={onValueChange}
                />
              ))}
            </AccordionSection>
          ))}

          {/* Expert options toggle */}
          {optionalParams.length > 0 && (
            <div>
              <button
                type="button"
                onClick={onToggleExpert}
                className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium py-1 transition-colors"
              >
                <Settings2 className="h-4 w-4" />
                {showExpert ? 'Hide Expert Options' : 'Show Expert Options'}
                <span className="text-xs text-gray-400 dark:text-gray-500 font-normal">
                  ({optionalParams.length} param{optionalParams.length !== 1 ? 's' : ''})
                </span>
              </button>

              {showExpert && (
                <div className="mt-3 space-y-3">
                  {Array.from(optionalGroups.entries()).map(([groupName, params]) => (
                    <AccordionSection key={groupName} title={groupName} defaultOpen={true}>
                      {params.map(({ def, schema }) => (
                        <ParameterField
                          key={def.name}
                          param={schema}
                          value={values[def.name] ?? ''}
                          onChange={onValueChange}
                        />
                      ))}
                    </AccordionSection>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="w-px bg-gray-200 dark:bg-gray-700 shrink-0" />

        {/* Right: Help panel */}
        <div className="w-72 xl:w-80 shrink-0 overflow-y-auto p-4 bg-gray-50 dark:bg-gray-800/30">
          <HelpPanel tab={tab} />
        </div>
      </div>

      {/* Viewer launcher — only on selectSubregions tab */}
      {tab.id === 'selectSubregions' && (
        <ViewerLauncher projectId={projectId} isDemo={isDemo} />
      )}

      {/* Bottom run bar */}
      <RunBar
        command={tab.command}
        onRun={onRun}
        isRunning={isRunning}
        runMessage={runMessage}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// ActionsPage – main exported component
// ---------------------------------------------------------------------------

export function ActionsPage() {
  const { projectId } = useParams<{ projectId: string }>()

  // Active tab — persisted in URL ?tab= query parameter
  const [activeTabId, setActiveTabId] = useTabParam(ACTION_TAB_IDS)

  // Per-tab parameter values: tabId → paramName → value string
  const [tabValues, setTabValues] = useState<Record<string, Record<string, string>>>({})

  // Per-tab expert options visibility
  const [expertOpen, setExpertOpen] = useState<Record<string, boolean>>({})

  // Per-tab run state
  const [runState, setRunState] = useState<Record<string, { running: boolean; message: string | null }>>({})

  const activeTab = ACTION_TABS.find((t) => t.id === activeTabId) ?? ACTION_TABS[0]

  const handleValueChange = useCallback(
    (paramName: string, value: string) => {
      setTabValues((prev) => ({
        ...prev,
        [activeTabId]: {
          ...(prev[activeTabId] ?? {}),
          [paramName]: value,
        },
      }))
    },
    [activeTabId],
  )

  const handleToggleExpert = useCallback(() => {
    setExpertOpen((prev) => ({
      ...prev,
      [activeTabId]: !prev[activeTabId],
    }))
  }, [activeTabId])

  const handleRun = useCallback(async () => {
    setRunState((prev) => ({
      ...prev,
      [activeTabId]: { running: true, message: null },
    }))

    try {
      // Collect current parameter values for the active tab
      const currentParams = tabValues[activeTabId] ?? {}

      // Step 1: Save parameter snapshot
      const snapshotResult = await apiClient.post<SnapshotResponse>(
        `/api/v1/projects/${projectId}/parameter-snapshots`,
        { parameters: currentParams },
      )

      // Step 2: Export snapshot to .m format
      if (!snapshotResult.snapshot_id) {
        throw new Error('Snapshot response missing snapshot_id')
      }
      const exportResult = await apiClient.post<ExportMResponse>(
        `/api/v1/projects/${projectId}/parameter-snapshots/${snapshotResult.snapshot_id}/export-m`,
      )

      // Step 3: Launch the command via workflow run endpoint, passing .m file path
      const runResult = await apiClient.post<RunCommandResponse>(
        `/api/v1/workflow/${projectId}/run`,
        {
          command: activeTab.command,
          args: currentParams,
          param_file: exportResult.m_file_path,
        },
      )

      // Show success with .m file path
      setRunState((prev) => ({
        ...prev,
        [activeTabId]: {
          running: false,
          message: `\u2713 ${runResult.message || `Command '${activeTab.command}' queued.`} Parameters saved to: ${exportResult.m_file_path}`,
        },
      }))
    } catch (err: unknown) {
      let detail = 'Unknown error'
      if (err instanceof ApiError) {
        // Extract specific error detail from backend response if available
        const body = err.body as Record<string, unknown> | null
        detail = (body && typeof body.detail === 'string') ? body.detail : err.statusText
      } else if (err instanceof Error) {
        detail = err.message
      }
      setRunState((prev) => ({
        ...prev,
        [activeTabId]: {
          running: false,
          message: `\u2717 Failed to launch command: ${detail}`,
        },
      }))
    }
  }, [activeTabId, activeTab.command, tabValues, projectId])

  if (!projectId) {
    return <Navigate to="/" replace />
  }

  const currentValues = tabValues[activeTabId] ?? {}
  const currentExpert = expertOpen[activeTabId] ?? false
  const currentRun = runState[activeTabId] ?? { running: false, message: null }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page header */}
      <div className="px-6 pt-5 pb-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shrink-0">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Actions</h2>
        <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
          Configure and run emClarity processing steps. Parameters sourced from the tutorial (Sections 5–15).
        </p>
      </div>

      {/* Horizontal tab bar */}
      <div
        className="flex overflow-x-auto border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shrink-0"
        role="tablist"
        aria-label="Processing steps"
        onKeyDown={(e) => {
          // WAI-ARIA APG: roving tabindex requires arrow-key navigation between tabs.
          const tabEls = Array.from(
            e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]'),
          )
          // Compare by identity — avoids unsafe cast of document.activeElement
          const currentIndex = tabEls.findIndex((el) => el === document.activeElement)
          if (currentIndex === -1) return

          let newIndex = currentIndex
          if (e.key === 'ArrowRight') {
            newIndex = (currentIndex + 1) % tabEls.length
          } else if (e.key === 'ArrowLeft') {
            newIndex = (currentIndex - 1 + tabEls.length) % tabEls.length
          } else if (e.key === 'Home') {
            newIndex = 0
          } else if (e.key === 'End') {
            newIndex = tabEls.length - 1
          } else {
            return
          }
          e.preventDefault()
          tabEls[newIndex].focus()
          // Update state directly instead of dispatching a DOM click event,
          // which would bubble and could trigger unintended side effects.
          // Guard access in case ACTION_TABS length diverges from DOM tab count.
          const nextTab = ACTION_TABS[newIndex]
          if (nextTab) setActiveTabId(nextTab.id)
        }}
      >
        {ACTION_TABS.map((tab) => {
          const isActive = tab.id === activeTabId
          return (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              role="tab"
              aria-selected={isActive}
              aria-controls={`tabpanel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setActiveTabId(tab.id)}
              className={[
                'flex flex-col items-center px-3 py-2.5 text-xs font-medium whitespace-nowrap transition-colors border-b-2 min-w-[72px]',
                isActive
                  ? 'border-blue-600 text-blue-700 dark:border-blue-400 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-gray-600',
              ].join(' ')}
            >
              <span className="text-center leading-snug">{tab.shortLabel}</span>
            </button>
          )
        })}
      </div>

      {/* Tab panels — all rendered in DOM so aria-controls IDs are always valid;
          inactive panels are hidden with the HTML hidden attribute. */}
      {ACTION_TABS.map((tab) => {
        const isActive = tab.id === activeTabId
        return (
          <div
            key={tab.id}
            id={`tabpanel-${tab.id}`}
            role="tabpanel"
            aria-labelledby={`tab-${tab.id}`}
            hidden={!isActive}
            className="flex-1 overflow-hidden"
          >
            {isActive && (
              <ActionTabContent
                tab={tab}
                values={currentValues}
                showExpert={currentExpert}
                onValueChange={handleValueChange}
                onToggleExpert={handleToggleExpert}
                onRun={handleRun}
                isRunning={currentRun.running}
                runMessage={currentRun.message}
                projectId={projectId}
                isDemo={projectId === DEMO_PROJECT_ID}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
