/**
 * Parameter Registry – central manifest of which params are "claimed" by each
 * Action tab (tutorial Tables 3-12).
 *
 * "Claimed" means the parameter appears in an Action tab's parameter list.
 * The Expert panel (/project/:id/expert) shows the UNCLAIMED remainder –
 * schema params not referenced by any tutorial table.
 *
 * Sync enforcement: PARAMS_BY_TAB is typed as Record<ActionTabId, ...>.
 * TypeScript will flag a compile error if PARAMS_BY_TAB is missing a tab ID
 * or uses an ID not in ACTION_TAB_IDS.  ActionsPage.tsx imports ActionTabId
 * and uses it for ActionTabDef.id, so both directions are enforced at compile
 * time — no drift is possible without a build failure.
 *
 * A parameter is also considered claimed if its canonical schema name has a
 * deprecated_name alias that is explicitly claimed by an action tab.
 * See the ALIAS_CLAIMED set below.
 */

// ---------------------------------------------------------------------------
// Canonical tab ID registry — single source of truth for all Action tab IDs
// ---------------------------------------------------------------------------

/**
 * Ordered list of Action tab IDs matching the ACTION_TABS array in
 * ActionsPage.tsx.  Add new tab IDs here first; TypeScript then requires
 * a matching entry in PARAMS_BY_TAB and forces ActionsPage to use a valid ID.
 */
export const ACTION_TAB_IDS = [
  'autoAlign',
  'ctfEstimate',
  'selectSubregions',
  'templateSearch',
  'init',
  'ctf3d',
  'avg',
  'alignRaw',
  'tomoCPR',
  'classification',
  'finalRecon',
] as const

/** Union type of all valid Action tab IDs. */
export type ActionTabId = (typeof ACTION_TAB_IDS)[number]

// ---------------------------------------------------------------------------
// Per-tab claimed sets (sourced from ActionsPage ACTION_TABS definitions)
// ---------------------------------------------------------------------------

/**
 * Maps Action tab ID → set of parameter names it claims.
 *
 * Typed as Record<ActionTabId, ...> so TypeScript enforces that every tab in
 * ACTION_TAB_IDS has a corresponding entry — missing or extra keys are build
 * errors, not silent runtime gaps.
 */
export const PARAMS_BY_TAB: Readonly<Record<ActionTabId, ReadonlySet<string>>> = {
  // Section 5, Table 3
  autoAlign: new Set([
    'autoAli_max_resolution',
    'autoAli_min_sampling_rate',
    'autoAli_max_sampling_rate',
    'autoAli_iterations_per_bin',
    'autoAli_n_iters_no_rotation',
    'autoAli_patch_size_factor',
    'autoAli_patch_tracking_border',
    'autoAli_patch_overlap',
    'autoAli_max_shift_in_angstroms',
    'autoAli_max_shift_factor',
    'autoAli_refine_on_beads',
  ]),

  // Section 6, Table 4
  ctfEstimate: new Set([
    'SuperResolution',
    'erase_beads_after_ctf',
    'CUM_e_DOSE',
    'doseAtMinTilt',
    'oneOverCosineDose',
    'startingAngle',
    'startingDirection',
    'doseSymmetricIncrement',
    'defCutOff',
    'defEstimate',
    'defWindow',
    'deltaZTolerance',
    'zShift',
    'ctfMaxNumberOfTiles',
    'ctf_tile_size',
    'paddedSize',
  ]),

  // Section 7, Table 5
  selectSubregions: new Set([
    'super_sample',
    'expand_lines',
  ]),

  // Section 8, Table 6
  templateSearch: new Set([
    'SuperResolution',
    'Tmp_samplingRate',
    'erase_beads_after_ctf',
    'applyExposureFilter',
    'super_sample',
    'expand_lines',
    'whitenPS',
    'particleRadius',
    'Ali_mRadius',
    'Peak_mType',
    'Peak_mRadius',
    'diameter_fraction_for_local_stats',
    'symmetry',
    'Tmp_angleSearch',
    'Tmp_threshold',
    'Override_threshold_and_return_N_peaks',
    'Tmp_targetSize',
    'Tmp_bandpass',
    'rescale_mip',
  ]),

  // Section 9, Table 7
  init: new Set([
    'subTomoMeta',
    'Tmp_samplingRate',
    'fscGoldSplitOnTomos',
    'lowResCut',
  ]),

  // Section 10, Table 8
  ctf3d: new Set([
    'SuperResolution',
    'Ali_samplingRate',
    'useSurfaceFit',
    'flg2dCTF',
    'erase_beads_after_ctf',
    'applyExposureFilter',
    'super_sample',
    'expand_lines',
  ]),

  // Section 11, Table 9
  avg: new Set([
    'SuperResolution',
    'Ali_samplingRate',
    'Ali_mType',
    'particleRadius',
    'Ali_mRadius',
    'Ali_mCenter',
    'scaleCalcSize',
    'Raw_classes_odd',
    'Raw_classes_eve',
    'symmetry',
    'flgCones',
    'minimumParticleVolume',
    'flgFscShapeMask',
    'shape_mask_test',
    'shape_mask_lowpass',
    'shape_mask_threshold',
    'subTomoMeta',
    'Raw_className',
    'Fsc_bfactor',
    'flgClassify',
    'flgCutOutVolumes',
    'flgQualityWeight',
    'flgCCCcutoff',
    'use_v2_SF3D',
    'mtf_value',
  ]),

  // Section 12, Table 10
  alignRaw: new Set([
    'SuperResolution',
    'Ali_samplingRate',
    'Ali_mType',
    'particleRadius',
    'Ali_mRadius',
    'Ali_mCenter',
    'scaleCalcSize',
    'Peak_mRadius',
    'flgCenterRefCOM',
    'Raw_classes_odd',
    'Raw_classes_eve',
    'symmetry',
    'Raw_angleSearch',
    'subTomoMeta',
    'Raw_className',
    'Cls_className',
    'Fsc_bfactor',
    'flgClassify',
    'use_v2_SF3D',
  ]),

  // Section 13, Table 11
  tomoCPR: new Set([
    'SuperResolution',
    'Ali_samplingRate',
    'Ali_mType',
    'particleRadius',
    'Ali_Radius',
    'Ali_mCenter',
    'tomoCprLowPass',
    'tomo_cpr_defocus_refine',
    'tomo_cpr_defocus_range',
    'tomo_cpr_defocus_step',
    'min_res_for_ctf_fitting',
    'peak_mask_fraction',
    'Peak_mType',
    'Peak_mRadius',
    'particleMass',
    'tomoCPR_random_subset',
    'k_factor_scaling',
    'rot_option_global',
    'rot_option_local',
    'rot_default_grouping_local',
    'mag_option_global',
    'mag_option_local',
    'mag_default_grouping_global',
    'mag_default_grouping_local',
    'tilt_option_global',
    'tilt_option_local',
    'tilt_default_grouping_global',
    'tilt_default_grouping_local',
    'min_overlap',
    'shift_z_to_to_centroid',
    'subTomoMeta',
    'Raw_className',
    'Raw_classes_odd',
    'Raw_classes_eve',
  ]),

  // Section 14, Table 12
  classification: new Set([
    'SuperResolution',
    'Cls_samplingRate',
    'Ali_samplingRate',
    'Ali_mType',
    'Cls_mType',
    'Ali_Radius',
    'Cls_Radius',
    'Ali_mCenter',
    'Cls_mCenter',
    'flgPcaShapeMask',
    'test_updated_bandpass',
    'pcaScaleSpace',
    'Pca_randSubset',
    'Pca_maxEigs',
    'Pca_coeffs',
    'Pca_clusters',
    'Pca_distMeasure',
    'n_replicates',
    'PcaGpuPull',
    'flgClassify',
    'subTomoMeta',
    'flgCutOutVolumes',
    'scaleCalcSize',
    'use_v2_SF3D',
  ]),

  // Section 15 (same params as avg, Table 9)
  finalRecon: new Set([
    'SuperResolution',
    'Ali_samplingRate',
    'Ali_mType',
    'particleRadius',
    'Ali_mRadius',
    'Ali_mCenter',
    'scaleCalcSize',
    'Raw_classes_odd',
    'Raw_classes_eve',
    'symmetry',
    'flgCones',
    'minimumParticleVolume',
    'flgFscShapeMask',
    'shape_mask_test',
    'shape_mask_lowpass',
    'shape_mask_threshold',
    'subTomoMeta',
    'Raw_className',
    'Fsc_bfactor',
    'flgClassify',
    'flgCutOutVolumes',
    'flgQualityWeight',
    'flgCCCcutoff',
    'use_v2_SF3D',
    'mtf_value',
  ]),
}

// ---------------------------------------------------------------------------
// Canonical-name aliases for deprecated params
// ---------------------------------------------------------------------------
// Some schema params have a deprecated_name that matches a param in an action
// tab.  Both names refer to the same concept, so neither should appear in
// Expert.  This set holds the *canonical* (new) names whose deprecated alias
// is already claimed above.

const ALIAS_CLAIMED: ReadonlySet<string> = new Set([
  'scale_calc_size',              // deprecated: scaleCalcSize
  'distance_metric',              // deprecated: Pca_distMeasure
  'ccc_cutoff',                   // deprecated: flgCCCcutoff
  'classification',               // deprecated: flgClassify
  'fsc_shape_mask',               // deprecated: flgFscShapeMask
  'minimum_particle_for_fsc_weighting', // deprecated: minimumParticleVolume
  'move_reference_by_com',        // deprecated: flgCenterRefCOM
  'pca_scale_spaces',             // deprecated: pcaScaleSpace
])

// ---------------------------------------------------------------------------
// Combined claimed set
// ---------------------------------------------------------------------------

/** Union of all claimed param names across all action tabs + their aliases. */
export const CLAIMED_PARAMS: ReadonlySet<string> = (() => {
  const all = new Set<string>()
  for (const names of Object.values(PARAMS_BY_TAB)) {
    for (const name of names) {
      all.add(name)
    }
  }
  for (const name of ALIAS_CLAIMED) {
    all.add(name)
  }
  return all
})()

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/** Returns true if the param is claimed by at least one Action tab. */
export function isClaimedParam(name: string): boolean {
  return CLAIMED_PARAMS.has(name)
}

/**
 * Returns the list of Action tab IDs that claim a given param.
 * May return multiple IDs if the param appears in several tabs.
 */
export function claimingTabs(name: string): string[] {
  return Object.entries(PARAMS_BY_TAB)
    .filter(([, params]) => params.has(name))
    .map(([tabId]) => tabId)
}
