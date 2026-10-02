# BAC Camera-Through S-band Antenna – Project Handoff

**Version:** 0.7.3
**Handoff date:** 2026-09-23
**Status:** cavity-model design space explored; openEMS backend runs end-to-end (coarse mesh only so far)

## 1. Objective and constraints

The goal is a fixed S-band antenna on a CubeSat face that leaves a central optical path for a camera, avoiding a deployable camera or antenna.

| Constraint | Value |
|---|---|
| Board area | cross, 80 × 80 mm overall, arms 40 mm wide |
| Stack height | ≤ 6 mm, ground board bottom to patch copper |
| Camera bore | 10 mm (larger bores under consideration) |
| Connector | SMP on the underside of the ground board |
| Radio | SatNOGS COMMS S-band |
| Primary band | 2200–2290 MHz Tx (downlink) – the priority |
| Secondary bands | 2025–2110 MHz Rx – nice to have; 2400–2450 MHz Rx/Tx – future avenue |
| Polarization | RHCP (confirmed against the ground segment, 2026-09-22) |

**Regulatory note.** 2025–2110 and 2200–2290 MHz are space research / space operation allocations. The amateur-satellite S-band is 2400–2450 MHz. The antenna design is unaffected, but the licensing route differs: a filing through the national administration versus amateur coordination. `cross_2400.toml` covers the amateur band.

## 2. Current state

| Area | State | Evidence / caveat |
|---|---|---|
| Package, CLI, configs | Working | `uv build` clean; `--set` overrides for variants |
| Cavity backend | Working | FD eigen solver: exact for a rectangle; ≤ 1.2 % from analytic ring roots (open, shorted, monopolar TM01) at 0.25 mm grid; Q within 1.6× of Jackson |
| Topologies | Cross patch, annular ring | Shared stack, bore, tube, capacitive feed pads |
| Dual feed | Cavity: ideal 90° hybrid; openEMS: superposition of per-port runs | Hybrid orientation chosen for the wanted hand |
| openEMS backend | Runs end-to-end | openEMS 0.37.0 built from source; coarse-mesh runs only; see §4a |
| Tests | 20 passing | geometry, solver, cross-patch physics, scoring |
| Hardware readiness | Not ready | No full-wave result yet |

## 3. Repository map

```text
config/cross_2200.toml        Lead config: 2200–2290 MHz Tx
config/cross_2400.toml        2400–2450 MHz amateur-satellite variant
config/annular_2200.toml      Annular-ring baseline
src/bac_antenna/config.py     Schema, bands, stack, overrides
src/bac_antenna/geometry.py   Primitives, outlines, Shape, model checks
src/bac_antenna/topologies.py CrossPatch, AnnularRing: params -> Shape and Model
src/bac_antenna/cavity.py     Cavity model: rasterise, eigenmodes, impedance, radiation
src/bac_antenna/openems_backend.py  Model -> CSXCAD, per-port runs, superposition
src/bac_antenna/core.py       Optimiser, multi-band score, mock backend, reports
src/bac_antenna/rf.py         Axial ratio, RHCP/LHCP components (IEEE, +z)
src/bac_antenna/vtk.py        ParaView preview of the metal parts
tests/                        Unit tests
```

## 4. Findings from the cavity model (2026-09-21)

All numbers are cavity-model estimates for a 5.9 mm stack: 1.0 mm ground board, 4.4 mm air gap and a 0.508 mm RO4003C-class top board. Confirm them in openEMS.

1. **The cross is sized for an air gap.** A broadside pair at 2.245 GHz needs arms of about 65 mm with an open bore, or about 70 mm with a shorted one. The limit is 77 mm. On thin laminate the patch would be about 35 mm and wasteful.
2. **Q_rad ≈ 16–23 depending on arm width**, which gives roughly 3–4 % VSWR-2 bandwidth per mode. The 90 MHz Tx band is 4 % wide.
3. **The centre short adds a monopolar mode.** It has no broadside radiation, sits at 1.6–1.8 GHz and has Q ≈ 8–13. It stays below both bands in every design seen so far, but it is new, so check it in openEMS. The short also raises the broadside pair by about 7 %. The open-bore variant has a clean spectrum up to ~3 GHz.
4. **Single feed.** Arms that differ by about 5 mm, with the feed on the diagonal, give ≥ 8.8 dBic RHCP realized gain across 2200–2290 MHz. Axial ratio stays ≤ 3 dB only over ~10–30 MHz; with AR over 10 MHz the design reaches S11 ≤ −13 dB across the band. For the RHCP x-arm is shorter than the y-arm with the feed in the first quadrant. Swapping arms flips the hand (tested).
5. **Dual feed with an ideal hybrid** gives AR ≤ 0.7 dB and ≥ 7.9 dBic across the Tx band, with ~3 dBic at the Rx band and ~4 dBic at 2400–2450 MHz. Match looks excellent because reflections go into the hybrid's isolated port; that loss is already inside the realized gain. A real hybrid covering 2.0–2.45 GHz (about 20 % bandwidth) will be worse at the band edges.
6. **For a CP ground station, RHCP realized gain is the link-relevant number.** The single feed matches the dual feed on it across the Tx band. The AR ≤ 3 dB target is the stricter constraint and drives the choice of feed.
7. **Rx 2025–2110 MHz** gets roughly 3–7 dBic from either feed. That is fine for an uplink with ground-station EIRP to spare; it is not scored for polarization.
8. **2400–2450 MHz, dual feed:** meets all targets (≥ 7.5 dBic, AR ≤ 1.4 dB) with a smaller patch.
9. **Larger bores:** 16 and 20 mm designs came out near or at the targets, at about 1 dB gain cost. The results were noisy across runs, so rerun with more candidates. Bore isolation drops to 1.55 dB/mm at 20 mm, so the sleeve must roughly double in length for the same isolation.
10. **The annular ring is dominated.** On an air gap with a shorted inner edge it cannot reach 2.2 GHz inside the cross (largest circle r = 28.3 mm), and it scored worst of all variants.

### Findings carried over from 0.2.0

- **Zero-height CSXCAD cylinders cover the whole domain.** All planar copper is now polygons, and `check_model` rejects degenerate primitives.
- **Resonance is searched over the whole excited span**, not only the band.
- **Port priority sits below the metals.**
- **The bore acts as a waveguide below cutoff.** At 10 mm it gives 3.17 dB/mm, so 25 dB over the 8 mm sleeve.

## 4a. First openEMS runs (2026-09-21, sandbox, 1 core)

**Bugs found and fixed in 0.3.1**

- **Polygon points.** CSXCAD wants polygon points as `[xs, ys]`, not a list of pairs. v0.3.0 crashed on the first polygon.
- **`PML_8` boundary.** With a coarse mesh the PML reached into the near field and absorbed power; efficiency read 34 %. The default is now `MUR`, as in the upstream patch tutorial. A guard extends the air margin if PML is chosen.
- **Timestep cap.** 40 000 steps truncated the excitation pulse on the full mesh. The cap is now 400 000, the end criterion stops the run, and the excitation band is wider for a shorter pulse.
- **Relative output paths (0.3.2).** `openEMS.Run()` changes the working directory into the simulation folder; the backend now resolves the output path first and restores the directory afterwards. Found on the first user run.
- **New command.** `simulate` evaluates a given design file, with `--geometry-only` and `--reuse`. The earlier `optimize --runs 1` simulated a random point.

**Checks**

- **Material assignment.** CSXCAD was probed at 14 points: patch, cross ground, tube joining patch and ground, bore cut, pad and probe are all correct.
- **Reference build.** The upstream `Simple_Patch_Antenna.py` runs correctly in the same build (95 % efficiency).
- **Power balance.** Far-field P_rad over port P_acc is 0.965 for the design below.

**Results**

- **Resonance offset – full-mesh data (user's machine, 683 k cells, 200 s).** `cross_2200_single_x094.json` resonates at 2.2045 GHz (x arm) and 2.0940 GHz (y arm); the unscaled cavity model was 12.7 % and 8.7 % high. `cavity.extension_scale = 2.05` brings both within about 2 %; the residual is a shape effect the Hammerstad strip formula cannot capture. Power balance 0.956, efficiency 95–96 %. `designs/cross_2200_single_v2.json` targets 2.313 / 2.177 GHz (split f0/Q for CP at 2.245 GHz) using per-mode correction factors from that run.
- **Earlier coarse-mesh note.** openEMS resonated about 6 % below the cavity model for `designs/cross_2200_single.json`. The offset does not depend on the mesh (2.047 GHz coarse, 2.050 GHz at the default mesh) or on the ground size (2.042 GHz on a 94 mm conducting panel). Treat the cavity model as about 6 % high for this stack until correlated.
- **Scaled design.** `designs/cross_2200_single_x094.json` has arms and feed scaled by 0.94. On a coarse mesh it puts the S11 minimum at 2.221 GHz, gives ≥ 7.0 dBic over 2200–2290 MHz and 96.5 % efficiency.
- **Single-feed CP not yet achieved in openEMS.** Axial ratio is about 20 dB, so the two modes are not split as the cavity model predicts. The next tuning job is the arm-length difference and feed position, done in openEMS, or the dual feed.

## 4b. Dual-feed result and hand calibration (2026-09-22)

**Dual feed, full mesh (user's machine), `designs/cross_2200_dual_v1.json`, 60.7 × 60.7 × 37 mm, feed 13.97 mm, pad 2.51 mm, ideal hybrid:**

| Band | Gain min (dBic) | AR worst | Efficiency | Hybrid-input S11 |
|---|---|---|---|---|
| Tx 2200–2290 | 9.7 | 0.9 dB | 94 % | ≤ −26.6 dB |
| Rx 2025–2110 | 4.2 | 2.1 dB | 92 % | ≤ −13.7 dB |
| 2400–2450 | 7.4 | 1.5 dB | 98 % | ≤ −17.0 dB |

All Tx targets met on the first full-mesh run; cavity model within 0.5 dB on gain and 0.1 dB on AR. Power balance 0.939. Each probe individually reflects about 15 % at 2.245 GHz (accepted 8.54 of 10 mW), which the hybrid's load absorbs – about 0.3 W at 2 W transmit. A feed-offset adjustment can reduce that. The −26 dB hybrid-input figure shows port-to-port coupling is low; `sparams.csv` and `per_port_at_primary_centre` now expose the per-port values.

**Single feed, v3 (58.62 × 62.52 mm, feed 19.6 mm):** modes merged into one minimum at 2.2435 GHz, 83 Ω real; AR 8 dB worst in band, gain 9.7 dBic. Close, but tuning it needs per-frequency AR (`farfield_samples.csv`, added in 0.3.3). Kept as fallback; the dual feed is the lead design.

**Hand calibration.** The upstream `Helical_Antenna.py` tutorial models a geometrically right-handed helix (z increases with counter-clockwise angle seen from +z) radiating along +z – RHCP by the IEEE/Kraus definition, independent of any solver convention. Run in this build: `rf.rotation_sense(E_theta, E_phi)` at broadside = +1, openEMS `E_cprh` dominant by 24 dB, AR 1.1 dB. Therefore `polarization.openems_rhcp_sense = 1` in all configs. Reprocessing the dual run with `--reuse` reports the hand.

**Real hybrid.** The X3C22E3-03S (1800–2700 MHz) has ±0.3 dB amplitude and 90 ± 4° phase balance (datasheet p. 1), which sets an AR floor of about 0.6 dB and costs ~0.2 dB; expect ~1.5 dB AR and ~9.3 dBic in practice. Swapping hybrid pins 1 and 2 flips the hand.

## 4c. Robustness sweep (0.3.5)

`bac-antenna sweep` runs every case of a plan file (`plans/robustness.toml`, `plans/hybrid.toml`), skips finished cases, and appends one row per case to `sweep_summary.csv`. `scripts/run_robustness.sh` runs both plans in sequence; the hybrid plan reuses the nominal case's field data through symlinks, so hybrid phase/amplitude imbalance costs no FDTD time. `polarization.hybrid_phase_deg` and `hybrid_amplitude_db` set the imperfection (ideal: 90, 0). Coarse-mesh results from the sweep runner are not comparable with full-mesh ones – the `mesh_fine` case exists to bound the mesh error of the full mesh itself.

## 4d. Laminate choice: FR4 versus RF laminates (2026-09-22)

The air gap carries ~97 % of the field energy, so the top board's laminate barely matters electrically. What laminate quality buys is (a) feed-line loss on the ground board, (b) frequency stability over temperature and lot, and (c) moisture/outgassing behaviour. Estimates: cavity model for the patch, closed-form microstrip (Wheeler width, Hammerstad loss) for 4 cm of 50 Ω line at 2.245 GHz. Datasheet values: Rogers RO4000 datasheet p. 3 (design Dk 3.55, Df 0.0021 at 2.5 GHz, TCDk +40 ppm/°C, moisture 0.06 %); Shengyi S7136H datasheet p. 2 (design Dk 3.61, Df 0.0030 at 10 GHz, TCDk 50 ppm/°C, moisture 0.06 %, standard thicknesses 0.254 / 0.51 / 0.76 / 1.52 mm); FR4 figures are generic (Dk 4.3 ± 0.2, Df 0.020, TCDk roughly −200 ppm/°C, moisture 0.1–0.2 %).

| Metric | FR4 (0.6 / 1.0 mm) | Shengyi S7136H (0.51 / 0.76 mm) | Rogers RO4003C (0.508 / 0.813 mm) |
|---|---|---|---|
| Patch resonance (cavity, same geometry) | 2.221 GHz | 2.239 GHz | 2.239 GHz |
| Patch dielectric loss | 0.04 dB | 0.01 dB | 0.01 dB |
| Feed pad C (2.51 mm pad) | 1.26 pF | 1.24 pF | 1.22 pF |
| 4 cm of 50 Ω feed line, per port | 0.31 dB | 0.09 dB | 0.07 dB |
| Line width for 50 Ω | 1.94 mm | 1.68 mm | 1.82 mm |
| Dk tolerance → resonance | ±0.2 → ~±0.4 % | ±0.05 → ~±0.1 % | ±0.05 → ~±0.1 % |
| TCDk, −40…+85 °C | ~−200 ppm/°C (pad C drifts ~1.5 %) | 50 ppm/°C | 40 ppm/°C |
| Moisture absorption | 0.1–0.2 % | 0.06 % | 0.06 % |
| Outgassing | grade-dependent; verify | not in NASA database as far as known – test | TML 0.06 %, CVCM 0.00 % (fab-reported) |
| Fab availability | everywhere | Chinese fabs (JLC/PCBWay on request) | most RF fabs |
| **Realized gain difference vs FR4** | 0 | **+0.25 dB** | **+0.27 dB** |

Conclusion: the RF laminates are worth about a quarter of a dB, essentially all of it in the feed lines, plus better stability. That is the same order as the hybrid's own loss. For a first flight, FR4 with a tightened line-length budget is defensible; RO4003C or S7136H is the low-risk choice if the fab offers it at reasonable cost, mainly for the ground board. S7136H is the RO4350B-class part (Dk 3.61 vs 3.55), a drop-in with a 1 % change of line width; the SCGA-500 PTFE line (Dk 2.65) is lower loss still but PTFE processing costs more and buys nothing here. A stack with an FR4 top board and an RF-laminate ground board is a reasonable compromise.

**Prototype-to-flight transfer.** The `proto_fr4`, `proto_fr4_er4.0/4.6` and `flight_stack` cases in the robustness sweep give the model's prediction of the FR4→flight shift directly (expected: under 1 % in frequency, ~0.3 dB in gain). The plan is: measure the FR4 prototype, correlate it with the `proto_fr4` case, carry the residual correction over to the `flight_stack` case, and confirm with one openEMS run. A full re-tune is only needed if the prototype disagrees with the model by more than the FR4-to-flight difference itself.

## 4e. Mounting outline (0.3.6)

The mounting area is an 80 × 80 mm square with 12 mm corner chamfers (96 mm across the chamfers). Proposal: make both boards that chamfered square – the ground board with full ground copper, the top board with the copper cross – and mount the sandwich with four corner standoffs plus the centre tube. The corners lie between the arms where the fields are weakest, ~16 mm beyond the ends of the radiating edges; bare laminate there costs nothing. No aluminium plate: if the structure under the board is conductive it extends the ground anyway (`ground_panel_94` case). Config: `outline.boards = "square"`, `outline.ground = "square"`, `panel_mm`, `panel_chamfer_mm`; the `boards_square` case in `plans/robustness.toml` simulates it.

**Mounting holes (0.3.7).** The actual pattern is (35, −25), (25, 35), (−35, 25), (−25, −35) mm from the board centre – 90° rotationally symmetric, not on the diagonals, and only ~8 mm from the patch tip corners (30.4, ±18.5), where the fringing field is strongest. The rotational symmetry means both modes see the same environment, so the posts shift the resonance but do not split the modes. `outline.posts`, `post_diameter_mm`, `post_material` (`peek` between the copper layers, or `metal` as a screw through both boards) model them; the `boards_square`, `boards_square_metal_posts` and `boards_square_no_posts` cases quantify the effect. Default: PEEK. The 3 mm fillets on the octagon corners are ignored.

## 4f. Mesh-line merging (0.3.8) – rerun everything before this

The first robustness sweep exposed two mesh bugs. (1) The second feed pad's edge at 2.51 mm sat 10 µm from a bore-refinement grid line at 2.50 mm; that 10 µm cell set the FDTD time step for the whole domain, so every full-mesh run so far (nominal, single v2/v3, dual v1, sweep nominal) took ~7× longer than necessary. Results are unaffected – only the speed. (2) With `refine_cell_mm = 0.15` the grid produced a line at 10⁻¹⁵ mm next to the fixed line at 0: a zero-width cell, and the `mesh_fine` case ran 400 000 timesteps with zero energy, then crashed in post-processing. `merge_lines()` now treats fixed lines as authoritative, drops grid lines within `mesh.merge_tolerance_mm` (0.05) of them, and averages fixed lines that are closer than that; the port's z-line is part of the gap grid; the smallest cell is printed; a port with no incident wave raises a clear error. Smallest cell on the nominal mesh: 169 µm (was 10). Because the discretisation changed slightly, the sweep should be restarted from scratch (`rm -r runs/robustness`) so all cases share one mesh; the new nominal must reproduce the old one (2.2533 GHz, −26.6 dB, 9.66 dBic, AR 0.89) within ~1 %.

## 4g. Robustness sweep results (2026-09-22, v0.3.9, `runs/robustness/sweep_summary.csv`)

All 24 FDTD cases and 5 hybrid cases completed (~150 s per dual case after the mesh fix). Nominal reproduced the earlier run (2.2500 vs 2.2533 GHz, 9.7 dBic, AR 0.87). Findings:

- **Mesh:** `mesh_fine` differs from nominal by +0.4 % in frequency, 0.1 dB in gain, 0.08 dB in AR – the error bar for everything below.
- **Gap 4.1–4.9 mm:** all targets met; −32 MHz/mm; gain and load fraction improve with gap (9.57 → 9.95 dBic, 15 % → 12 %). ±0.3 mm is comfortable.
- **Feed offset:** 12.5 mm beats 13.97 on every metric (load fraction 6.5 % vs 14 %, AR 0.72 dB); 15.5 and 17.0 are worse (22 %, 30 %). The 50 Ω point extrapolates to ~11.5–12 mm. **Proposed design change: feed_offset_mm = 12.5** (one confirmation run pending).
- **Etching ±0.2 mm:** ±10 MHz; a 0.4 mm x/y asymmetry gives AR 1.25 dB, S11 −21.8 dB – still fine.
- **Pad ±10 %:** no measurable effect → FR4 permittivity spread (4.0–4.6) is irrelevant for the coupling.
- **Chamfered square boards with posts at the real hole pattern:** −13 MHz, otherwise unchanged; metal screws vs PEEK: AR 0.80 vs 0.77 dB, i.e. metal is acceptable (heads on the ground side).
- **Bore unbonded (open):** −130 MHz, gain 7.95 dBic, 41 % into the load. The tube-to-patch bond is a single point of failure: soldered ring on the patch side is mandatory.
- **94 mm conducting panel behind the stack:** +0.35 dB, load fraction halved (7 %).
- **Sleeve 4 mm:** no RF effect (isolation only).
- **FR4 prototype stack:** resonance 1.5 % below the flight stack (2.211 vs 2.2435 GHz), 0.2 dB more loss; εr 4.0–4.6 moves it only ±0.3 %.
- **Hybrid tolerances (X3C22E3-03S corners):** AR ≤ 1.2 dB in all combinations; gain unchanged. The `resonance_hz` column is meaningless for `hyb_*` rows (input-reflection minimum wanders with the weights).
- **`gap_3.9` failed** in v0.3.9: `merge_lines` rounded mesh lines to 6 decimals while the patch polygon kept the unrounded elevation `gap + top`; for 3.9 + 0.508 they differed by 10⁻¹⁵ mm, openEMS reported "Unused primitive ... patch" and ran without the patch. Fixed in 0.3.10 (no rounding; a polygon without a mesh line at its elevation now raises an error). Rerun `gap_3.9` to complete the gap series.

Still to evaluate before layout: axial ratio and gain over angle (±60°), front-to-back ratio, and one run at feed 12.5 with the square boards and posts as the frozen design.

## 4h. Freeze plan and pattern cuts (0.3.11, 2026-09-22)

**Reading the feed-offset result.** For the dual feed, `resonance_hz` in the summary is the hybrid-input S11 minimum, which is set by port-to-port coupling and asymmetry, not by the probes' own match: with two identical probes the hybrid cancels their reflections at its input and sums them in the load. The load fraction over the band is governed by where each probe's *own* S11 minimum sits. From `sparams.csv` that is 2.273 GHz at feed 13.97 and 2.263 GHz at 12.5 – above the 2.245 GHz band centre – which is why the Tx low edge carries 22–25 % into the load at either offset (per-probe |S11|² at 2.200 GHz: 0.247 / 0.215) and why the Tx gain minimum always sits at 2.200 GHz. The −20 MHz that the square boards (−13) and the flight stack (−6.5) bring should land the probe minimum on band centre without touching the arms. The backend now reports `probe_resonance_hz` (mean over ports of the per-port S11 minimum) in the diagnostics and as `probe_res_hz` in the summary; centre *that*, not `resonance_hz`.

**Frozen candidate.** `config/cross_2200_dual_v2.toml` + `designs/cross_2200_dual_v2.json`: feed 12.5 mm, chamfered square boards with PEEK posts at the mounting holes, flight stack (RO4003C 0.813 mm ground board, 4.67 mm gap, 0.508 mm top, Df 0.0021 per Rogers RO4000 datasheet p. 3). The v1 config stays as the reference for `runs/robustness`.

**`plans/freeze.toml`** (`scripts/run_freeze.sh`, ~150 s per case): `frozen`; gap ±0.3 mm at the new offset (the only tolerance that moves the match); `proto_fr4` on the frozen geometry (the correlation reference for the PCBWay panel); `metal_posts`; and an arm-length bracket ±0.5 mm (~24 MHz/mm) to interpolate a trim from, only needed if `frozen` lands more than ~10 MHz off centre on `probe_res_hz`. Acceptance: probe minimum within 10 MHz of 2.245 GHz, load fraction ≤ 8 % at the gap corners, all Tx targets met, `frozen` within the mesh error bar of `boards_square` + the known feed/stack shifts. Then tag v0.4.0 and start layout.

**Pattern over angle.** Every openEMS evaluation now also computes the far field on θ = 0…180° (1° step) in the φ = 0/45/90/135° planes (both halves), at the primary band's low, centre and high frequency, from the same nf2ff box dumps (`nf2ff_cuts.h5`, a few seconds, no FDTD). Per direction it gives realized RHCP/LHCP gain (normalised to incident power, so hybrid-load loss stays inside) and axial ratio, using the broadside polarization helpers with (E_θ, E_φ) in place of (E_x, E_y) – valid because (θ̂, φ̂, r̂) is right-handed like (x̂, ŷ, ẑ). Outputs: `farfield_cuts.csv` (one row per frequency/φ/θ), `openems_diagnostics.json["pattern"]` (per-frequency and worst-case: gain and AR at 45° and 60° in the worst plane, front-to-back, rear-hemisphere power share from the full-sphere grid at band centre), and summary columns `tx_gain_45`, `tx_ar_45`, `tx_gain_60`, `tx_ar_60`, `fb_db`, `back_fraction`. `[pattern]` in the config sets the step, planes and summary angles. 60° off nadir is a 20° elevation pass from 500 km; `tx_gain_60` is the number the low-elevation link budget uses. Verified against a crossed Huygens source (directivity 3, perfect CP, 1/8 of the power behind, −2.50 dB at 60°) in `tests/test_pattern.py`. `scripts/plot_cuts.py` (`uv run --with matplotlib`) draws the cuts and prints the summary.

## 4i. Pattern over angle – result (2026-09-22, reprocessed `runs/robustness`)

RHCP realized gain at 2.245 GHz, feed 12.5: 10.8 dBic at boresight, −3 dB at ±23°, −10 dB at 45°, −16 dB at 60° (−5 dBic), then flat at −5 to −6.5 dBic to the horizon. AR ≤ 3 dB to 35° in the worst plane, ~5 dB from 45° outward. Front-to-back 11 dB, 13 % of the power behind the panel (10 % with the conducting bus, `ground_panel_94`). Every case in the sweep shows the same shape within 0.5 dB and `mesh_fine` agrees at 60° to 0.4 dB, so the wide-angle numbers are good to about ±0.5 dB.

**Why.** A half-wave patch in air has its radiating slots about 0.56 λ apart; each mode's E-plane array factor cos(π·0.56·sin θ) is −4 dB at 30°, −10 dB at 45° and has a null near 63°, which the small ground fills to about −6. A patch on εr ≈ 4 laminate has 0.24 λ₀ between its slots and is only ~2 dB down at 60° in the E-plane, at 6–7 dBic boresight. The air gap trades roughly +4 dB at boresight for −8 to −10 dB at 60°. The cavity model only scored broadside, so this trade was invisible until the cuts existed.

**Decision (2026-09-22).** The CONOPS is to point the camera face at the ground station during passes, so the high-gain air-gap design stands: ≥ 8 dBic inside a ±20° pointing error. For reference, nadir-fixed operation would put a 20° elevation pass (60° nadir angle from 500 km) about 24 dB below zenith (16 dB antenna, 7.6 dB range); a 10 dB zenith margin then covers only elevations above ~47°.

**Beam-width comparison (`plans/beamwidth.toml`, `scripts/run_beamwidth.sh`).** Kept as the documented alternative: the gap filled with PTFE (εr 2.1, cross 46.8 × 37 mm) or PEEK (εr 3.2, the cross collapses to a 36.8 mm square around the bore), same outline, height and ground board. Cavity model: 6.8 / 5.6 dBic boresight with 3.9 / 3.2 % VSWR-2 bandwidth (Q 18 / 22 against 15 for air), so the load fraction at the band edges will be higher. Each variant carries an arm bracket of −8/−4/0/+4 % (the cavity edge extension is uncalibrated for a filled gap; scales 1.0–2.05 bound the resonance at 2.08–2.28 GHz PTFE, 2.17–2.46 GHz PEEK) and two feed offsets. Read `tx_gain_60`/`tx_gain_45` from the nominal case of each variant, gain-in-band and load fraction from whichever bracket case is centred. A full 80 mm slab at 4.67 mm is ~66 g PTFE or ~39 g PEEK; it would replace the spacers and the venting question of the air gap.

**`gap_3.9` note.** The 0.3.10 rerun of `gap_3.9` had been written outside `runs/robustness/gap_3.9`, so the first reprocess picked up the failed run's patchless field data (probe minimum at 2.9 GHz, 99 % into the load). The data has since been copied into place; a summary row with those numbers is stale, not a model result.

## 4j. Freeze confirmed – v0.4.0 (2026-09-23, `runs/freeze`, `runs/beamwidth`)

**Frozen design** (`config/cross_2200_dual_v2.toml` + `designs/cross_2200_dual_v2.json`, 135 s): probe minimum 2.247 GHz (band centre, as the −20 MHz estimate said), hybrid-input minimum 2.231 GHz, load fraction 3.2 %, Tx S11 ≤ −26.9 dB, gain ≥ 10.2 dBic, AR ≤ 0.7 dB, efficiency 93.5 %, score 0. Gap ±0.3 mm: 2.240–2.253 GHz, load 2.8–4.1 %. Arms ±0.5 mm: 26 MHz/mm. Metal screws instead of PEEK posts: 2.240 GHz, load 2.5 % – equivalent, so the fastener choice is mechanical. Pattern: −3 dB at ±22–25°, 8.1 dBic at 20° and 5.3 dBic at 30° in the worst plane, −3.9 dBic at 60°, AR ≤ 2.6 dB to 30°, F/B 11.6 dB, 11 % behind. No arm trim needed. **This is the v0.4.0 reference; layout starts from it.**

**FR4 prototype on the frozen geometry** (`proto_fr4`: 0.6 mm FR4 top, 1.0 mm FR4 ground, 4.4 mm gap): probe minimum 2.208 GHz, i.e. 39 MHz below the flight design, load 9.7 %, 9.0 dBic. The 0.97 arm-length variant of the PCBWay panel (58.9 mm, +47 MHz) lands in band; the 1.00 variant is the direct correlation point for the −39 MHz offset. Efficiency 89 % on FR4.

**Beam-width comparison – negative result.** Filling the gap with PTFE (εr 2.1) or PEEK (εr 3.2) does not broaden the usable beam in this form factor; it narrows it and moves power sideways and backward. The tuned PEEK case (`peek_arms_-4pct`, 35.3 mm square, probe minimum 2.250 GHz, load 0.9 %, 9.9 dBic, efficiency 88 %) gives −2.9 dBic at 45° and −10.1 dBic at 60° against −0.5 / −4.7 for the air patch, with AR 15 dB at 60° and 25 % of the power in the rear hemisphere (air: 11 %). PTFE behaves the same (19 %). The likely mechanism: the slab follows the board outline, so 17–22 mm of grounded dielectric extend beyond the patch edges and carry energy to the board edge, which radiates sideways and backward, linearly polarized; the whole 80 mm board becomes the aperture (boresight gain nearly unchanged despite the 37 mm patch) and the beam does not widen. A loaded variant would need the dielectric confined to the patch footprint, which the model cannot represent today (`gap_foam` uses the board outline). Not pursued: the CONOPS points the face at the station (§4i).

**Cavity model calibration for filled gaps.** openEMS resonances of the loaded variants match `cavity.extension_scale ≈ 2.05` (PEEK 36.8 mm: cavity 2.170 vs openEMS 2.172 GHz; PTFE 46.8 mm: 2.084 vs 2.107, scale ≈ 1.9), so the air-gap fit carries over; the 1.5 used to seed `plans/beamwidth.toml` was 2.5–5 % high in frequency. Keep 2.05.

**`probe_res_hz` window.** Three loaded cases reported 1.600 GHz because the per-port S11 has its global minimum in the excitation's noisy low edge; the search is now restricted to the primary band ±200 MHz (0.4.0). Rows written by 0.3.11 with `probe_res_hz` = 1.6e9 are that artefact.

**Hole pattern correction (0.4.1).** The spacecraft hole pattern in the model frame (x right, y up from the antenna side) is (35, 25), (−25, 35), (−35, −25), (25, −35), each 20° clockwise of a cable egress point at 56°, −34°, −124°, 146°. Until 0.4.0 the configs carried the mirror image across the diagonal. The structure is symmetric under that mirror except for the CP hand, and `metal_posts` showed the posts do not register, so `runs/freeze` stands; rerun `frozen` on the corrected config if you want the reference geometry file to match the hardware exactly.

## 4k. Feed pin construction – through the top board (0.4.2, 2026-09-23)

The pad is etched on the underside of the top board, so the pin has to be joined to it. A butt joint of a 1 mm pin to a pad face is not a flight joint, and a top-side solder joint would need a hole through the patch and solder next to it. The construction chosen for layout: the pin passes through a plated 1.2 mm hole at the pad centre, inserted from the patch side and soldered on the pad side before the boards are stacked; the patch copper is cleared 2.4 mm dia around it with the plated hole's 1.6 mm top land inside the clearance; no solder on the patch side. The pin then goes through the ground board and is soldered on its underside. Pin: 1.0 mm dia, about 7 mm long (gap + both boards + fillet).

The clearance removes ~20 % of the pad-to-patch overlap, and the pad radius was tuned without it, so the pad needs re-tuning: `feed.through_pin`, `feed.patch_clearance_mm`, `feed.top_ring_mm` add the construction to the model (off by default, so the frozen reference is unchanged), and `plans/through_pin.toml` runs pad 2.51 / 2.70 / 2.90 plus a 3.0 mm clearance variant. Read `probe_res_hz` and `hybrid_load_fraction` against `frozen` (2.247 GHz, 3.2 %), pick the pad that restores the load fraction, then set `through_pin = true` and that radius in the v2 config and design. Expect 2.7–2.9 and a resonance shift under 10 MHz.

Top board (drawing `top_board_layout.svg`): no solder mask on either side (matches the model), ENIG; patch ordered at 62.5 × 37 mm and trimmed 0.9 mm per arm end to 60.7, then to 58.9 for the FR4 in-band variant, silk ticks at both lengths; bare copper ring around the 11.2 mm bore hole out to 15 mm for the tube joint. Ground board (`ground_board_placement.svg`): mask on both sides, top mask opened 11.2 → 15 mm at the bore and at the four post holes; probe holes 1.2 mm plated with 2.6 mm clearance in the ground; mask over the 50 Ω lines accepted (~1 Ω).

## 4l. 2400–2450 MHz amateur variant (0.4.3)

Same stack, outline, hybrid and ground-board layout as the frozen design; only the patch and the feed offset scale. Cavity model on the v2 stack: ~54 mm arms (the edge extension does not scale, so not 60.7 × 2245/2425), feed ~11.6 mm, 5 % bandwidth against the 2 % band. `config/cross_2400_dual_v2.toml`, `designs/cross_2400_dual_v2.json`, `plans/s2400.toml` (arm and feed brackets, five cases). Tx-only as configured; a shared 2.4 GHz uplink would be a diplexer on the ground board. Supersedes `config/cross_2400.toml` (v1 stack, single feed) as the starting point.

**Result (2026-09-23, `runs/s2400`).** The cavity scaling was 2.4 % short (32.5 MHz/mm from the arm bracket). The feed bracket at 11.0 / 11.6 / 12.5 mm shows the same intrinsic match at centre once detuning is taken out – the smaller patch's impedance is flat over that range – so the feed stays at 12.5 and **the ground board is shared with the 2200 design**. Confirmed: arms 55.7 × 37 mm, feed 12.5, pad 2.51 → probe minimum 2.4255 GHz, 2.9 % load, 10.96 dBic, AR 0.73 dB, −5.0 dBic at 60°, 27 MHz/mm (`plans/s2400_confirm.toml`). `designs/cross_2400_dual_v2.json` carries it; `drawings/cross_2400_*` are generated from it.

**Through-pin result (2026-09-23, `runs/through_pin`).** With the clearance and top land in the model, pad 2.51 gives 2.2435 GHz and 3.3 % load against 2.2468 GHz / 3.2 % for `frozen`; larger pads lose gain; the 3.0 mm clearance variant is identical. Pad 2.51 stays on both bands, `through_pin = true` in both configs, `frozen` remains the reference.

**Board drawings from config + design (0.4.4).** `scripts/draw_boards.py -c <config> -p <design> --out drawings/<name>` writes the ground-board placement, the top-board drawing and a coordinate table for any variant (`uv run --with cairosvg` for PNGs). The hybrid stays at (20, 20); only the probe vias and the patch follow the design. Regenerate after every design change so the drawings never drift from the model.

**Report outputs (0.4.6).** Every evaluation now also writes `sparams_complex.csv` (re/im for each port pair, for Smith charts and bench correlation) and `farfield_sphere.csv` (the 5° × 10° sphere at band centre: total/co/cross gain and AR). `[dump] efield = true` adds frequency-domain E-field planes at band centre per port run (`E_gap.h5`, `E_top.h5`, `E_xz.h5`, HDF5, NZYX order) with the hybrid weights recorded in the diagnostics; it needs a fresh FDTD run. `scripts/report_charts.py <case> --out <dir>` turns a case into the datasheet charts (S11 and coupling, Smith, gain/AR vs frequency, pattern cuts, 3D pattern, E-field planes) plus `summary.md`; `sweep --reprocess` adds the two new CSVs to older runs. The documentation bundle for bac-hardware (README, simulation report, test plan, drawings, chart folders) is kept there, not here.

**KiCad board files (0.4.7).** `scripts/kicad_boards.py -c <config> -p <2200 design> --patch-2400 <2400 design> --out <dir>` writes `ground_board.kicad_pcb`, `patch_board_2200.kicad_pcb`, `patch_board_2400.kicad_pcb` in the KiCad 8 file format (KiCad 9/10 upgrade on open): outline, plated M3 holes on GND, NPTH bore with a 15 mm mask opening, probe pins as B.Cu-only plated pads with F.Cu keepout circles, the hybrid with square 1.5 mm pads, 0603 links, 1206 loads with GND vias, a generic 5-pin right-angle SMP placeholder, routed 50 Ω lines (1.94 mm FR4 / `--ground-stack ro4003c_0.813` for 1.82), the F.Cu GND zone; on the patch boards the cross as an F.Cu zone at the ordered length, feed footprints (B.Cu disc + plated hole with a 1.6 mm land) inside 2.4 mm keepouts, full-board mask openings, silk trim ticks. All footprints are written at rotation 0 with explicit pad positions, so the flip convention cannot mirror anything. Zones are unfilled; the SMP footprint is a placeholder. The exit segments from the hybrid pads are 3.5 mm (`draw_boards.py` matches) so the 0603 link clears the hybrid pad by 0.5 mm.

**0.4.8.** `report_charts.py` clips the curves to the axes in data (some SVG viewers ignore clip paths) and copies its inputs into `<out>/data/` for notebooks (`--no-data` to skip); `draw_boards.py` adds `<out>_stack.svg`, a stack section through the bore with z drawn 3x. The bac-hardware docs folder carries a marimo notebook (`docs/sim/report.py`) that redraws the charts from those data folders.

## 5. Reports and the antenna folder (0.5.0)

The drawing, chart and KiCad generators moved from `scripts/` into `bac_antenna.report` (`drawings.py`, `charts.py`, `kicad.py`) behind one command, `bac-antenna report antenna.toml`, driven by a manifest in the antenna's folder of the hardware repo (`bac-hardware/rf/antenna/s-band-cross-patch` on Codeberg). The tool lives in the bac-utils repo on GitHub (`bac-utils/tools/bac-antenna-optimizer/`, tags `bac-antenna-optimizer-vX.Y.Z`), with `.venv/` and `runs/` gitignored; the manifest's `tool_project` is the relative path between the two checkouts and `regenerate.sh` in the antenna folder resolves it. That folder is the source of truth for the antenna: `design/<band>.toml|json` and `design/plans/` (the tool's `config/` and `designs/` stay as examples and test fixtures), `sim/runs/` holds the copied result directories (a `.gitignore` drops the field data), `templates/` the prose with `{{ key }}` placeholders, and `generated/` everything derived: `drawings/<band>_{ground,top,stack}.svg`, `charts/<band>/` (+ `summary.md`, `data/`), `boards/*.kicad_pcb`, `values.json` (every placeholder value), `STATUS.md` (what was produced, what is missing and the exact commands). `README.md` and `docs/simulation.md` are rendered from the templates. Numbers come from each band's `reference_run` (a `simulate --set dump.efield=true` run, or any sweep case; a list of candidates is allowed, the first existing directory wins; a case without `result.json` falls back to its sweep summary row). Run it from the antenna folder: `uv run --project <tool> --extra report bac-antenna report antenna.toml` (the `report` extra brings matplotlib, h5py, cairosvg). `tests/test_report.py` covers the renderer and the manifest path without matplotlib.

**0.5.2.** E-field dump reader handles both openEMS HDF5 layouts: the current one (one compound-complex dataset `f0` per frequency, dims N,X,Y,Z, complex members `r`/`i`) and the legacy one (`f0_real`/`f0_imag`, dims N,Z,Y,X); the mesh is converted from metres. `read_fd_dump()` in `report/charts.py` returns (3, nx, ny, nz) either way.

**0.5.3.** Pattern-cut chart: axial ratio drawn only where the realized gain (either hand) is within 20 dB of the peak; in the nulls it is noise over noise and was filling the panel.

**0.5.4.** Every `[antenna]` key of the manifest is available to the templates (`tool_url`, `repo_url`, …).

## 6. General-purpose core (0.6.0, 2026-09-24)

The tool is now a generic core plus antenna types. `bac_antenna.antennas` holds the interface (`AntennaType`: `params`, `valid`, `model`, optional `shape` for the cavity estimator, `report_values`/`report_globals`/`exporters` for the report) and the built-ins `cross_patch`, `annular_ring` (moved from `topologies.py`, which stays as a shim), `dipole` (the example and openEMS smoke test) and `turnstile` (four tape elements on the end face of a body, four ports, elements in the face plane; not yet run in openEMS). A config picks the type with `[antenna] type`, or `type = "file:path.py"` for a type defined next to the design. `Model` gained `grid_lines`, `bounds`, `phase_centre`, `edge_props` and `field_planes`, and the openEMS backend reads only those: no `[stack]`/`[outline]`/`[feed]` knowledge is left in it (`build_lines()` is the mesh-line assembly, testable without openEMS). `[feed_network]` (`feednetwork.py`) replaces the built-in hybrid assumption: single / quadrature / turnstile / custom weights, the network's phase and amplitude errors, both hands evaluated and the better one kept; the legacy `[polarization] hybrid_*` keys still map. `CoarseBackend` (`--backend coarse`) is the fast estimator for types without a cavity model.

Config layout: the type's section is `[geometry]` (`[geometry.stack]` etc. for the patches). Legacy top-level sections and `stack.*` overrides in plans still load and are routed into `[geometry]`; `bac-antenna migrate` rewrites configs and plans (comments preserved). The report reads the type's values and exporters, so the antenna folder, its templates and its result files are unchanged. `tests/golden/*.json` were captured with 0.5.4 for the two frozen designs; `test_golden.py` asserts the 0.6 types build the identical primitives, ports, fixed lines and pre-smoothing mesh lines, and `test_antennas.py` checks that the legacy and migrated configs build the same model, so no rerun was needed to prove the refactor changed nothing.

### 6.1 End criterion and run-to-run reproducibility (0.6.1, 2026-09-24)

Repeating the frozen 2200 MHz run showed that openEMS stops at a different timestep every time (identical `geometry.xml`, port files 203/214/221 samples long on three runs, dumps on or off). At `end_criteria = 1e-4` the truncated ringing moves the results between runs by 0.006 dB gain, 0.03 dB AR and 0.5 points of efficiency, and biases the absolute efficiency about a point low (Tx 93.1–93.6 % vs 94.1–94.2 % converged; 2400 MHz band 96–97 % vs 98.7 %; resonance one 3.25 MHz bin). At `1e-5` the spread is 0.0002 dB, 0.004 dB and 0.09 points in the primary band (0.2 points off-band) for ~15 % more runtime. All configs now use 1e-5; the sweeps in `sim/runs` were run at 1e-4 and are consistent among themselves but carry the efficiency bias. The refactor itself was confirmed on the way: model and mesh identical (`geometry.xml` byte-identical), so the only differences between 0.5.4 and 0.6.0 results were this stopping-point effect.

### 6.2 Sensitivity packs (0.7.0, 2026-09-24)

`pack.py` / `bac-antenna pack`: the axes file `design/sensitivity.toml` defines the sliders of the antenna visualizer (bac-utils `tools/bac-antenna-visualizer`). Matching is by effective state – design parameters plus the flattened config with the case's overrides applied – so any existing case on the same stack qualifies and a case on another stack is excluded on its own; `ignore` lists keys allowed to differ (validation limits), `also` carries extra overrides into the plan for an axis. The pack ships the case files reduced to gzipped CSV (cases, sweeps, samples, cuts, sphere), the primitives of every case's model (`models.json`) and the nominal config and design, so a notebook can rebuild geometry live where the tool is importable. 0.7.1 adds the complex probe S-parameters to `sweeps.csv.gz` (for the Smith chart) and `efield.csv.gz`: |E| of the combined excitation on every dumped plane, resampled to `efield_grid_mm` (2 mm), for the cases run with dumps – needs the `report` extra (h5py). `tests/test_pack.py` builds a mini antenna folder with the cavity backend and checks the matching, the plan and the files. The S-band axes file lives in the antenna folder; its sensitivity plan (about 15 openEMS runs) still has to be run before the shipped pack carries FDTD numbers.

### 6.3 WebP, pack zips, local-only visualizer (0.7.2, 2026-09-28)

Raster output is lossless WebP through Pillow (`report/charts.py` `save_raster`, `report/drawings.py`); the 3D pattern went from 160 kB PNG to 65 kB. `pack --zip` writes `<name>-pack.zip` beside the pack folder for the antenna's release; `pack.json` carries `tool_version`, `source` and `release`. Decision of 2026-09-28: the visualizer no longer targets molab (WebAssembly). Consequences: packs are not tracked in any repo (gitignored in bac-hardware, none in bac-utils; the release zip is the archive), the visualizer discovers packs on the local machine or takes a path/URL/upload, the optimizer is its hard dependency so geometry is always live, and the wheel-release workflow was dropped. The cavity estimator behind the sliders (patches) is the next visualizer step.

### 6.4 Idempotent regenerate and the missing-runs guard (0.7.3, 2026-09-28)

`regenerate` on an unchanged folder must leave git clean; three sources of noise are gone: KiCad UUIDs are now `uuid5` from a fixed namespace and a per-file counter (`kicad.uid_scope`), the chart SVGs carry no Date metadata and use a fixed `svg.hashsalt`, and the drawings no longer get raster copies (cairo's text rendering differed run to run, and the templates only embed the SVGs). `STATUS.md` still carries the generation date, the one line that legitimately changes. Second, since `sim/runs` is not tracked, `bac-antenna report` in a checkout without the reference runs used to overwrite the finished datasheet with one full of dashes; it now stops after the drawings with a message and exit 1 unless `--allow-missing` is given. `tests/test_report.py` checks the board files are byte-identical across two runs.

Open: run `config/turnstile_435.toml` in openEMS (first real exercise of a multi-port non-patch type), and give the turnstile a deployment angle and a stowed state.

**Refreshing old sweeps.** `bac-antenna sweep --reprocess` re-evaluates every case of a plan from its existing field data (no FDTD) and replaces its summary row in place, adding any new columns; `scripts/reprocess_robustness.sh` does this for `runs/robustness` (both plans, ~5–10 s per case). The summary writer now appends under the file's existing header, so an old file is never misaligned by new columns – columns appear when the file is created or reprocessed. Reprocessing is only valid while the mesh generation is unchanged from the run (true for 0.3.8–0.3.11).

## 5. openEMS model

The model is built from the same `Model` the preview uses:

- cross-shaped ground polygon at z = 0;
- ground board, optional foam gap and top board as extruded cross polygons;
- patch polygon on top of the top board;
- circular feed pads on the underside of the top board, giving capacitive coupling through the board;
- a 1 mm square probe from a 0.5 mm lumped port at the ground up to each pad;
- a camera tube, solid PEC hollowed by a priority-100 air cylinder, reaching the patch when shorted and only the ground otherwise.

Each port gets its own run. S-parameters and far fields are then combined with the hybrid weights, normalised to each run's incident wave. Loss tangents are converted to conductivity at the primary band centre. The far field is computed on a 5° × 10° sphere, which gives P_rad, broadside gain and AR. The code writes `s11_sweep.csv` and `openems_diagnostics.json`.

## 6. Configuration

- `[[band]]` sets the targets per band; `weight = 0` means the band is reported only.
- `polarization.openems_rhcp_sense` stays 0 until calibrated. While it is 0, openEMS hand is reported as `unverified` and gain as the larger CP component.
- `[stack]` holds the layer thicknesses and materials; the total height is validated.
- `[outline]` holds the board, bore, tube and the short on/off switch.
- `[feed]` sets single or dual feed, the SMP keep-out (`min_offset_mm`) and the probe.
- `--set section.key=value` overrides any value. Bands are addressed by name, e.g. `band.tx.cp_span_hz=10e6`.

## 7. First openEMS validation sequence

1. **Install and smoke-test** on the lead design. Build openEMS, then install the bindings with `CSXCAD_INSTALL_PATH`/`OPENEMS_INSTALL_PATH` set via `uv pip install <openEMS-Project>/CSXCAD/python <openEMS-Project>/openEMS/python`. A plain `uv sync` removes the bindings again; `uv run` and `uv sync --inexact` keep them.
   ```bash
   uv run bac-antenna simulate -c config/cross_2200.toml -p designs/cross_2200_single_x094.json --geometry-only --output runs/smoke
   uv run bac-antenna simulate -c config/cross_2200.toml -p designs/cross_2200_single_x094.json --output runs/smoke
   ```
2. **Inspect the geometry** in AppCSXCAD (`geometry.xml`). Check the cross board, patch, pads under the top board, probes, tube joining patch and ground, and the bore cut.
3. **Check the mesh** at the pad, the probe, the tube wall and the arm edges.
4. **Check run stability:** energy decay and any port warnings.
5. **Compare the S11 sweep with the cavity model.** Check the broadside resonance position, the monopolar mode near 1.7 GHz (with the short), and the pad series-C behaviour.
6. **Check power balance and efficiency.**
7. **Calibrate the hand.** Model a truncated-corner square patch of known RHCP, then set `openems_rhcp_sense`. The cavity model uses IEEE with e^{jωt}, and its prediction for the same geometry is a second reference.
8. **Check mesh convergence** on one candidate.
9. **Only then run a coarse openEMS batch**, seeded near the cavity optimum by narrowing `[search]`.

## 8. Known limitations and risks

- **The cavity model is approximate.** It assumes an infinite ground plane, a uniform field across the gap, and edge extension from Hammerstad's strip formula. It gives a probe reactance plus an ideal parallel-plate pad capacitance, and it samples far fields at the band centre.
- **The real ground is the 80 × 80 cross.** Expect more back radiation and somewhat lower gain than modelled, unless the spacecraft face behind it is conductive.
- **Tube, spacers and camera are not modelled in the cavity.** Only the tube's PEC wall is included; the spacers and camera are absent.
- **The dual feed uses an ideal hybrid.** Whether a real branch-line or SMD hybrid fits on the underside of the ground board, next to the SMP and the sleeve, is still to be laid out.
- **The air gap needs venting and mechanical support in flight.** Foam (εr ≈ 1.07) is the alternative.
- **Nothing has been qualified** for tolerance, thermal, vibration or EMC.

## 9. Recommended next work

**P0**
- Freeze confirmed (§4j); tag v0.4.0. Layout starts from `config/cross_2200_dual_v2.toml` + `designs/cross_2200_dual_v2.json`: feed offset 12.5 = probe via positions, chamfered square outline, spacecraft hole pattern, metal screws allowed.
- Through-pin confirmed (§4k), pad 2.51. Both bands designed and drawn: one ground board, two top boards (60.7 / 55.7 mm arms, ordered at 1.03×).
- Antenna folder (0.5.0): run the two reference simulations with `dump.efield=true`, copy the runs in, `bac-antenna report antenna.toml`; then the KiCad project from `generated/boards/`.
- PCBWay: one top-board design at 62.5 mm arms, trimmed on the bench; bench correlation against `proto_fr4` (§4j).
- Done in 0.3.x: hand calibrated (RHCP), hybrid imbalance swept, feed offset chosen (12.5), tolerance sweeps (gap, arms, pad), ground-station polarization confirmed.

**P1**
- Model the hybrid and its loss.
- Add spacers and the camera body.
- Run tolerance sweeps: gap height, arm lengths, pad radius.
- Settle the bore size with longer runs.
- Add the monopolar mode to the openEMS pattern check.

**P2**
- Build a coupon: the two-board stack with the tube.
- Measure S11 first, then pattern, gain, AR and hand, with the camera installed.

## 10. Licensing

Software MIT. Hardware design files derived from it under CERN-OHL-S v2. Documentation CC BY-SA 4.0.
