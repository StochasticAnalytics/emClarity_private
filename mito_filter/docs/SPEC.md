# mito_filter — authoritative data/format spec for emClarity TM output

Scope: reverse-engineered spec of the emClarity template-matching (TM) output consumed by
`mito_filter`. Every semantic claim is labeled **VS** (verified-from-source, file:line) or
**VE** (verified-empirically, this session). Primary dev set = `six_hours_round_4`.

Source of truth (MATLAB): `/sa_shared/git/emClarity_private/alignment/BH_templateSearch3d_2.m`
(search + MIP + writes), `/sa_shared/git/emClarity_private/coordinates/BH_defineMatrix.m`
(rotation convention), `metaData/BH_geometryInitialize.m` (init ingest).

Data root: `/scratch/siracusa/full_enchilada_3/six_hours_round_4/convmap_wedgeType_2_bin5/`
Per-tomo basename: `H99_2_<NNN>_1_bin5` (112 tomos, NNN ∈ 95..230 non-contiguous).

---

## 1. The dense convmap — the PRIMARY input

Per-tomo `<base>_convmap.mrc`.

- **Dims 662 × 942 × 448, MRC mode 12 (float16)**, no extended header; file = 279,374,592 vox × 2 B
  + 1024 = 558,750,208 B exact. Numpy/C order `(nz=448, ny=942, nx=662)`; x fastest. **VE**
- **Value = running MAX over all 864 sampled orientations × 3 templates of a per-orientation
  σ-normalized cross-correlation** (a max-intensity projection of the angular CC search). Each
  per-orientation CC map is divided by its own std before the max (`ccfmap = ccfmap./std(ccfmap(:))`,
  BH_templateSearch3d_2.m:640); no mean subtraction. So a voxel ≈ "σ above 0 of the best-matching
  orientation's CC at that voxel." **NOT** raw CC, **NOT** a true SNR, **NOT** rescaled 0:1 (the
  `mag=mag./std` at :785 and the 0:1 comment :778 are commented out). **VS**
- Build: running max/argmax maintained per chunk (:646–666): seed `magTmp=ccfmap` (:648); then
  `replaceTmp=(magTmp<ccfmap); magTmp(replaceTmp)=ccfmap(replaceTmp)` (:663–665). Gathered into
  `RESULTS_peak` (:702–704), `mag=RESULTS_peak` (:781), saved `SAVE_IMG(mag,{...,'half'})` (:793). **VS**
- **On-disk convmap is FULLY DENSE — saved BEFORE any masking.** Edge-trim (:818), `mag(Ang<0)=0`
  (:835), and the peak-erase loop (:848–1032) all run on an in-memory copy *after* the file is
  written. The peak-erase never touches the saved volume. **VS**
- **Pixel size: header stamped 1.0 (uncalibrated, cosmetic).** True voxel = **12.5 Å** =
  `PIXEL_SIZE=2.5e-10` (param, i.e. 2.5 Å) × `Tmp_samplingRate=5`. **VS+VE**
- Value distribution (H99_2_100, subsample): min 1.55, p50 3.23, p90 3.87, p99 4.69, p99.9 6.20,
  max 12.67; mean 3.28, std 0.48; **0 % zeros, 0 % negatives**. Background ≈ N(3.28, 0.48) with a
  heavy right tail = the hits. **VE**
- **How signal appears:** gold/ice false positives = compact CLUSTERS of extreme values (~8–13);
  membranes = extended elevated-CC SHEETS in the ~4–6 band (p99–p99.9). The csv erases most of both;
  the convmap keeps them. This is why the convmap, not the csv, is the primary signal. **VE**

**Load recipe (never hot-load the whole volume):**
```python
import mrcfile, numpy as np
m = mrcfile.mmap(path, mode='r', permissive=True)   # data.shape == (448,942,662) = (nz,ny,nx)
block = np.asarray(m.data[k0:k1, j0:j1, i0:i1], np.float32)   # index [z, y, x]
```

---

## 2. The 26-column CSV (`<base>.csv`) — LOSSY, peak-masked auxiliary

One `fprintf` (BH_templateSearch3d_2.m:1065–1068). One row per accepted peak (this tomo: 1249). **VS**

| col (1-idx) | source (BH_templateSearch3d_2.m) | meaning | units | label |
|---|---|---|---|---|
| 1 | `peakMat(i,10)` (:951,1066) | **CC score** = convmap value at the peak's argmax voxel | convmap intensity | VS+VE |
| 2 | `samplingRate` | binning factor = **5** | — | VS+VE |
| 3 | `0` | placeholder const | — | VS |
| 4 | `i+nPreviousSubTomos` | per-tomo peak id 1..N (**reassigned to a global id at init**, BH_geometryInitialize.m:364) | index | VS+VE |
| 5–9 | `1,1,1,1,1` | const flags (col9 = init sortrows key → const ⇒ no reorder) | — | VS+VE |
| 10 | `0` | placeholder const | — | VS |
| 11,12,13 | `peakMat(i,1:3)=samplingRate.*cenP` (:950) | peak **X,Y,Z in FULL-tomo (bin1) px** | full px | VS+VE |
| 14,15,16 | `peakMat(i,4:6)=ANGLE_LIST(angIdx,:)` (:946) | **Euler `[phi, theta, psi−phi]`** (winning orientation, clean, no symmetry) | degrees | VS+VE |
| 17–25 | `r=reshape(BH_defineMatrix(euler,'Bah','inv')*symMat,1,9)` (:1063) | **3×3 rotation matrix, COLUMN-MAJOR** (see §3) | — | VS+VE |
| 26 | `1` | **active flag** (all raw rows =1; set −9999 downstream) | flag | VS+VE |

Column-major unpack of cols 17–25 into `M` (`reshape(M,1,9)` is column-major):
```
M = [[c17, c20, c23],
     [c18, c21, c24],
     [c19, c22, c25]]     # cols 17-19 = M[:,0], 20-22 = M[:,1], 23-25 = M[:,2]
```
**VE:** for 50 real rows, `max|M Mᵀ − I| = 1.1e-6`, `max|det − 1| = 9.1e-7`. Orthonormal, det +1.

**Sibling files, same row order (one write loop `i=1:size(peakMat,1)`, csv :1065 / pos :1086 /
templateIDX :1088 ⇒ row k identical across all three; init copies verbatim so subTomoMeta geometry
row k ↔ csv row k). VS+VE (1249/1249/1249):**
- `<base>.pos` = `peakMat(:,1:3)/samplingRate` = **bin5 voxel coords in the convmap frame directly**. **VS**
- `<base>.templateIDX` = `peakMat(i,7)` = winning reference id (multi-ref). This tomo counts
  **777 / 275 / 197** for refs 1/2/3. **VS+VE**
- `<base>_angles.list` = 864 rows `[phi, theta, psi−phi]` deg (the sampled grid,
  `Tmp_angleSearch=[180,12,180,12]`); same 864 for every tomo. `ANGLE_LIST` printed at :808–810. **VS+VE**
- `<base>.mod` = IMOD model of the peaks. `<base>.path` = `<base>,./cache,.rec,fixedStacks/ctf/<b>_ali1_ctf.tlt`.

---

## 3. Coordinate & pixel conventions (RESOLVED contradiction)

- **CSV cols 11–13 are FULL-tomo (bin1) px; `.pos` is bin5 = convmap-voxel frame.** Not the same.
  `csv[:,10:13] / 5 == .pos` (**VE**, max abs diff 6e-7). Convmap voxel `(i=x, j=y, k=z) = .pos row =
  csv[:,10:13]/5`. **VS** (:950 multiplies by samplingRate; :1086 divides back).
- **Peaks land on convmap local maxima. VE:** for the top 15 peaks, the 3×3×3 convmap max around
  `round(.pos)` equals csv col1 to <0.02 (12.060 vs 12.055, …), **15/15**. The exact-voxel value is
  slightly lower only because `.pos` is CoM-refined sub-voxel off the integer argmax (`cenP=c+cMass'`,
  :932) → always read a **±1 neighborhood** to recover the score.
- Physical position = voxel × **12.5 Å**. Ignore the convmap header's 1.0 apix.
- Frame is the **tomogram .rec voxel frame**, right-handed (det +1). The rescale pipeline already
  applied `-rotate 180` + the physical ±90° Z-rotation to the stacks pre-reconstruction, so the .rec
  (hence M and the normal) is in corrected real-space handedness — **no extra flip.** **VS (CLAUDE.md)+VE**
- The searched **.rec shares the exact voxel grid** with the convmap: `/scratch/salina/alt_cache/<base>.rec`,
  662×942×448 mode-12 fp16 12.5 Å, byte-identical size — convmap voxel (i,j,k) ↔ rec voxel (i,j,k). **VE**

---

## 4. Template-Z / outward-normal extraction (the key orientation deliverable)

`BH_defineMatrix('Bah','inv')`: **Bah = ZXZ active; 'inv' = particle(template)→microscope(tomogram)**
(BH_defineMatrix.m:12,17–18). For 'inv' the impl flips euler order (no negation) then builds
`Rz·Rx·Rz` (:109,125–133), giving net `M = Rz(phi)·Rx(theta)·Rz(psi−phi)`. So `M · v_template = v_tomogram`.
Template **+Z is the outward membrane normal**, so the normal in the tomogram frame = `M·[0;0;1]` =
**3rd column of M = CSV cols 23, 24, 25.** **VS**

**`template_z_formula` (both equivalent, VE):**
```python
# (A) directly from the stored matrix — cols 23,24,25 (0-indexed 22:25), already unit length:
n = row[22:25]                      # outward normal, tomogram voxel frame (+x,+y,+z)

# (B) from the euler triple cols 14,15,16 (phi, theta, psi-phi); psi-phi is unused:
phi, theta = np.radians(row[13]), np.radians(row[14])
n = np.array([ np.sin(phi)*np.sin(theta),
              -np.cos(phi)*np.sin(theta),
               np.cos(theta) ])
```
**VE:** `max|M[:,2] − analytic n| = 1.0e-6` over 50 rows; row1 θ=72° → cos72°=0.309017 == col25 exactly.

**C12-symmetry robustness (critical): use cols 23–25, NOT cols 17–22.** The stored matrix is
post-multiplied by a *per-peak cycling* C12 mate about template-Z (`iSym=mod(nSym,nSymMats)+1`,
incremented every peak, :1059–1063; `symmetry=C12`). A Z-rotation `S` leaves `M·S·ẑ = M·ẑ`, so the 3rd
column (normal) is invariant, but cols 17–22 (in-plane) are scrambled and the full matrix ≠
`BH_defineMatrix(cols14-16)` in general. **VE:** 46/50 rows differ from the plain matrix by exactly
`Rz(k·30°)`, k∈±1..6 (residual `S₃₃=1`), 4/50 identical (k=0). Do not try to recover psi from the csv.
**Do not re-sign the normal** — the raw sign IS the outward-vs-inward discriminative signal.

---

## 5. Dense per-voxel orientation index → normal (for a regenerated angle volume)

The running **argmax** volume `RESULTS_angle` is computed voxel-aligned with the convmap (:349, :649,
:666) but its save is **commented out** (:806) — no dense angle field exists on disk. If regenerated
(§7), each voxel holds a **packed index** `p = (angleIdx−1)*nTemplates + refIdx` (:618, nTemplates=3):

**`angleindex_to_normal` recipe (VE against `_angles.list` ↔ csv, error 6.4e-5, limited by the list's
2-decimal rounding):**
```python
angleIdx = (p - 1) // nTemplates + 1     # 1-based row of _angles.list   (:615,946)
refIdx   = (p - 1) %  nTemplates + 1     # winning template 1..3          (:614,947)
phi, theta, _ = angles_list[angleIdx - 1]           # degrees
phi, theta = np.radians(phi), np.radians(theta)
n = np.array([ np.sin(phi)*np.sin(theta),
              -np.cos(phi)*np.sin(theta),
               np.cos(theta) ])          # outward normal; NO symmetry to undo (dense field stores raw argmax)
```
The C12 mate is applied only at csv write-out, so the dense field needs no symmetry correction.

---

## 6. CSV lossiness — quantified

The csv is greedy non-max suppression with a large oriented erase; the convmap keeps everything. **VS**
- After each accepted peak, a **cylinder** (`eraseMaskType=cylinder`) of radius
  `Peak_mRadius=[210,210,320] Å` → bin5 `floor(R/12.5)+parity ≈ [16,16,26]` voxels, **rotated to the
  peak's own orientation** (`rmInt.interp3d(peakMat(n,4:6))`, :1004), is zeroed in the working copy
  (`mag(box).*=(rmMask<0.98)`, :1010–1015) — ~2.1e4 voxels erased per peak. The saved convmap is untouched.
- Score floor: `highThr = sqrt(2)·erfcinv(ceil(peakThreshold·0.1)·2 /(prod(size(tomo))·nAngles))`
  (:290), `Tmp_threshold=1500`, `nAngles=864`. Loop `while MAX>highThr` (:882). Cap = `2·1500=3000`
  peaks. Empirically the floor bound it (~6.07 CC ≈ p99.9 of the field). **VS+VE**
- **Empirical (112 tomos): 136,418 peaks total; per-tomo min 633 / median 1215 / max 1977 / mean 1218.
  col26 == −9999 fraction = 0.00 %** (removal flags live only in the `.mat`, applied at
  classification, never in raw TM output). For H99_2_100: **291,224 voxels ≥ 6.07 vs 1249 csv peaks** —
  the dense sheets/clusters (membranes, gold/ice) are collapsed to sparse survivors. **VE**

---

## 7. Dense angle/orientation field — concrete plan

**RECOMMENDED: minimal source patch + recompile + re-run (option b).** All prior findings agree; this
is ~1 line.
1. In `BH_templateSearch3d_2.m` replace the commented `:806` with a **float32/mode-2** save of the
   already-computed argmax volume, e.g. `SAVE_IMG(single(RESULTS_angle), anglesOUT);`. **Do NOT use
   `'half'`:** packed max = `nAngles·nTemplates = 864·3 = 2592`, and float16 represents integers exactly
   only to 2048 → indices 2049–2592 corrupt. fp32 (or int16, ≤32767) is exact. **VS** (:349,618,806).
2. Recompile — **SALINA-ONLY** (per-host `/home` MATLAB license lives on salina;
   `testScripts/mCompile.sh <wrapper>.m`, `skipMex=1` for a pure-`.m` change). Watch the NFS symlink
   attr-cache on `current_emClarity` before relaunching remote hosts.
3. Re-run the (already-tuned) 112-tomo bin5 search. Inputs all present on disk: searched recs
   `/scratch/salina/alt_cache/<base>.rec` (112, frame-identical, ~62 GB), 3 templates,
   `_angles.list`, ctf/tilt geom.
- **Output:** one extra ~0.5 GB/tomo (fp32) volume, voxel-exact to the convmap, encoding **both**
  best-angle (→ per-voxel outward normal via §5) **and** best-template per voxel.
- **Cost:** one recompile + one search re-run (hours across 8 GPUs, params exist). Cannot be recovered
  from existing outputs — the argmax was RAM-only.
- Optional polish: gate behind a new `Tmp_write_angles` key (opt-in) and/or also emit a decoded
  3-channel normal volume.
- **Fallback (option c), only if recompile/re-run is impossible or a different angular grid is needed:**
  a cupy/torch FFT-CC engine over the 864 angles + 3 templates + wedge (all inputs on disk). ~10–50× the
  effort; bit-matching emClarity's template bandpass/RMS-norm, wedge/CTF weighting, and 'Bah' texture
  rotation is hard, but the **argmax-angle field is robust** even with approximate scores. Verdict: b ≫ c.

---

## 8. Membrane-reference dense field — concrete plan

**RECOMMENDED: add a membrane/bilayer template to the multi-reference search, then reuse the §7 patch.**
The search is already multi-reference (`template_list=strsplit(TEMPLATE,',')`, :190; round_4 ran 3
templates C12). Each voxel's packed index already carries the winning template (:947, emitted sparsely
to `.templateIDX`). **VS**
1. Build a synthetic bilayer/edge template (or low-pass density slab) at bin5, **box must equal the
   protein templates' 288³** (hard-fail on mismatch, :226–230; it is rescaled to ~58³ internally).
2. Add it as an extra element of the comma-separated template list and apply the §7 patch. Then the
   single `RESULTS_angle` volume yields, per voxel: **membrane-likelihood** = voxels where
   `refIdx == membrane_ref` (with the co-located convmap CC as strength) → segments elevated-CC bilayer
   sheets; **membrane-normal** = §5 normal of that voxel → the local bilayer normal field to distinguish
   the outer mito membrane (coherent, low-curvature normals) from interior replication vesicles
   (small closed shells).
3. **Caveat:** in a *combined* MIP a strong membrane template can out-compete weak protein hits at
   protein voxels. To get independent fields, run membrane detection as a **SEPARATE** search
   (membrane-only vs the protein-only run), or accept the argmax-selection labeling from one combined run.
- No new plumbing beyond §7; reuses the packed-index argmax + `.templateIDX` semantics.
- **No membrane/mito reference or per-hit spatial ground truth exists anywhere on disk today**
  (find over project + emClarity `templates/` = none). Building it is genuine from-scratch work. Only
  low-res substrate toward segmentation: `bin10/*.rec` (112 bin10 tomos), unlabeled. **VE**

---

## 9. Data inventory (dev/validation)

- **112 tomograms**, identical set across rounds 1–4 (successive tilt-align/tomoCPR iterations of the
  SAME data, not different data). Each round `convmap_wedgeType_2_bin5/` has the full 7-file set/tomo,
  ~58 GB. **VE**
- **PRIMARY dev set = `six_hours_round_4`**: latest/best alignment (`_ali4`); same 3 original FE2
  templates as round_3 (near-identical outputs); richest downstream weak labels; **its `_ali4` recs are
  the only search recs currently on disk** (`/scratch/salina/alt_cache/<base>.rec`, 112, frame-identical
  to the convmap). round_1/2/3 search recs were deleted/rebuilt by each bridge. **VE**
- round_2 is NOT comparable (different consensus templates cls13/31/51, 322k peaks, 84 % ref#3).
- **Templates (templateIDX order), all 288³ mode-2 fp32 @2.5 Å bin1, in `six_hours_round_1/` symlinked
  into round_4:** `1=ref_old.mrc`, `2=ref_proto_8fm9_288_resampled.mrc`, `3=ref_proto_29289_resampled.mrc`.
  Protein target, template +Z = outward membrane normal. **VS+VE**
- Key TM params (`six_hours_round_4/param_TM_bin5_half.m`): `symmetry=C12`, `particleRadius=[180,180,150] Å`,
  `Peak_mRadius=[210,210,320] Å` (the erase radius), `Tmp_samplingRate=5`, `Tmp_bandpass=[0.01,1200,25]`,
  `Tmp_threshold=1500`, `Tmp_angleSearch=[180,12,180,12]`, `measure_noise_variance=0`, `PIXEL_SIZE=2.5e-10`. **VE**

---

## 10. Weak labels (no per-hit spatial ground truth)

Ranked by directness:
1. **`.templateIDX` (on disk, no .mat).** `ref_old` (idx 1) = 57 % of round_4 hits but survives culls
   worst — after cyc8 the active pool flips to prototype-majority (%kept: ref_old 24.9, 8fm9 48.2,
   29289 54.9). So **templateIDX==1 hits are enriched in false positives** — a usable weak negative
   prior straight from the file. **VE (CHANGELOG)**
2. **Classification culls → per-particle keep/−9999 in the `.mat`** (row-order mapped to TM hits,
   verified 112/112). round_4 progressive: cyc2 133867→89767, cyc5→73618, cyc8→49181, then branches.
   Surviving-to-branch = strong positives; removed at cyc2 = weak negatives. Class-level lists:
   `six_hours_round_4/cycle{002,005,008}_ClassMods_STD.txt` (+ `cycle005_ClassKeep_STD.txt`).
3. **subTomoMeta `.mat`** (source of −9999): `full_enchilada_3_4.mat` (~480 MB, **scipy `loadmat`
   FAILS — zlib CRC**; read via MATLAB on salina or use the v6 snapshots
   `full_enchilada_3_4_nosym_branch_{1,2}_v6.mat`). Helpers: `scripts/tm_ref_cull.py`,
   `scripts/tm_ref_stats.py`, `scripts/verify_cull.py`.
4. **`bin10/*.mod` = reconstruction ROI boxes (1/tomo), NOT membrane traces.** `cyc{2,5,8}_remove/keep.mod`
   = class-montage picks, not spatial. **No spatial per-hit labels exist.**

---

## 11. Open questions

- Exact per-voxel score normalization is per-orientation σ (no shared mean) — a convmap voxel is
  z-like but not a calibrated SNR. If a true SNR is wanted, re-run with `measure_noise_variance=1`
  (emits `<base>_noise_variance.mrc`; `convmap/sqrt(noise_variance)` ≈ per-voxel SNR). Currently off.
- Does a strong membrane template in a combined multi-ref MIP mask weak protein hits? (§8 caveat →
  probably run membrane-only separately; needs empirical test.)
- The `.mat` row↔hit mapping is verified via csv cols 14–16 copied verbatim by init, but positions
  drift after alignment cycles — always map by the angle triple / subtomo id, not position.
- No mito membrane vs interior-vesicle ground truth for training/validation — must be
  bootstrapped (segmentation on `bin10` recs, or normal-coherence heuristics on a regenerated field).
```
