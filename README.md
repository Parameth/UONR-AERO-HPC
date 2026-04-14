# UONR-AERO-HPC

University of Nottingham Racing Aerodynamics HPC Repository

## Key People

Owner - Parameth Yingchankul [UoN 2023-2026]  
Aero Lead FS27 - Frederick Blake [UoN 2024-2029]

**Current Users:**  
Parameth Yingchankul  
Frederick Blake  
Jack Tandy  
Jeevan Natt  
Nathan Wood

To be used within the team **if** you have access to the HPC @ UoN

---

## Stack

**ANSYS VERSION: 24R1**  
Python & Bash

Dependencies: see `requirements.txt`
- `ansys-fluent-core` — PyFluent API for meshing & solving
- `opencv-python`, `tqdm`, `scipy` — installed at runtime by `HPC_run.sh`
- ParaView `pvbatch` — post-processing (loaded via HPC module)

**Version:** V1.3.0

---

## Repository Structure

| File | Purpose |
|------|---------|
| `HPC_run.sh` | SLURM job script — loads modules, sets up venv, runs the pipeline |
| `HPCRUN.py` | Main entry point — orchestrates meshing, solving, and post-processing |
| `HPCSOLVE.py` | Fluent solver setup — BCs, force monitors, iterations |
| `HPCPOST.py` | ParaView post-processing — slice sweeps, Cp/vorticity plots |
| `sim_config.ini` | All simulation parameters — edit this to configure a run |
| `requirements.txt` | Python package dependencies |

---

## Configuration (`sim_config.ini`)

All run parameters live in `sim_config.ini`. The active profile is selected by `mode` under `[config]`:

| Mode | Description |
|------|-------------|
| `operations` | Full-resolution production run |
| `debug` | Coarse/fast run for pipeline testing |

### Key sections

| Section | What it controls |
|---------|-----------------|
| `[simulation]` | Simulation name, CAD file (`.pmdb`), mesh file (`.h5`) |
| `[solver]` | Iterations, processor count, freestream velocity (m/s) |
| `[vehicle]` | Vehicle geometry — tyre radius, wheelbase, moment reference centre |
| `[zones]` | Aerodynamic zones used for force reporting (e.g. `chassis`, `fw`, `rw`) |
| `[forces]` | Force monitor definitions (down-force, drag-force, side-force) |
| `[surface_mesh_global]` | Global min/max surface mesh size (mm) |
| `[volume_mesh]` | Volume fill type, growth rate, max tet cell length |
| `[surface_mesh_options]` | Per-component local surface sizing controls |
| `[boundary_layer_options]` | Boundary layer settings per region (first layer height, layer count, transition ratio) |
| `[refinement_zones]` | Body of Influence (BOI) refinement boxes (coordinates in mm) |
| `[postpro]` | ParaView settings — image resolution, slice sweep ranges, Cp/vorticity colour map limits |
| `[mrf-zones]` | MRF rotating zone definitions (omega in rad/s, axis origin/direction) |
| `[wheels]` | Wheel wall rotation settings (omega in rad/s, axis origin/direction) |

Debug profile sections use the same names prefixed with `debug_` (e.g. `[debug_solver]`).

---

## Features

- **INI-based configuration** — all simulation parameters loaded from `sim_config.ini`; supports `operations` and `debug` profiles
- **Automated watertight meshing** — drives Fluent's Watertight Geometry workflow end-to-end (geometry import, surface mesh, volume mesh, surface mesh improvement)
- **MRF wheel internals** — Moving Reference Frames for wheel spoke rotation
- **Local surface sizing** — per-label sizing controls (min/max size, curvature angle, scope)
- **Refinement box zones (BOI)** — bounding-box refinement regions with configurable coordinates and max cell size
- **Boundary layer generation** — named BL controls with configurable first layer height, layer count, offset method, and transition ratio
- **Boundary condition setup** — velocity inlet, shear walls, moving ground plane, and rotating wheel walls (per-wheel axis origin, direction, and omega)
- **Force & flux monitors** — drag/lift/side-force report definitions and residual/flux monitors, globally and split per zone
- **Aero balance** — moment report (`aero_balance_moment`) at configurable moment centre; derives front/rear downforce split and % aero balance
- **ZY projected area via ConvexHull** — frontal area computed from Fluent ASCII surface exports using `scipy.spatial.ConvexHull` (×2 for half-model symmetry); avoids PyFluent API limitations
- **Results report** — per-zone CL/CD/CS breakdown, total forces, dynamic pressure, and aero balance written to `<sim_name>-results.txt`
- **Skin friction export** — `skin-friction-coef` included in EnSight Gold cell function export alongside pressure and vorticity
- **ParaView post-processing** — automated slice sweeps (X and Y planes) exporting Cp_total, Cp_static, and vorticity magnitude as `.png` sequences via `pvbatch`
- **Solver hand-off** — switches from meshing to solver session in a single Fluent process (no intermediate file I/O)
- **Safe teardown** — `try/finally` block ensures `solver.exit()` is always called

---

## Usage

1. Clone/upload the repository files to the HPC
2. Edit `sim_config.ini`:
   - Set `mode = operations` (or `debug` for a quick test run)
   - Set `user_initials`, `sim_date`, `sim_number` under `[simulation]` — run name is assembled as `{initials}-{date}-{num}`
   - Set `CAD_file` under `[simulation]`
   - Set `tyre_radius`, `wheelbase`, `moment_center` under `[vehicle]`
3. Submit the job:
   ```bash
   sbatch HPC_run.sh
   ```
4. Logs are written to `logs/<job-name>-<job-id>.out`
5. Post-processing output is saved under `<sim_name>/<sim_name>_postpro/Base_Images/`

### Output files

| Output | Location |
|--------|---------|
| Fluent case/data | `<sim_name>/<sim_name>.cas`, `.dat` |
| Residual/force plots | `<sim_name>/` (`.png`) |
| EnSight export | `<sim_name>/<sim_name>.encas` |
| Slice images (Cp, vorticity) | `<sim_name>/<sim_name>_postpro/Base_Images/` |
| Run log | `log_run` |
| Post-processing log | `log_post` |

---

## SLURM Settings (`HPC_run.sh`)

| Parameter | Value |
|-----------|-------|
| Time limit | 12 hours |
| Partition | `defq` |
| Nodes | 1 |
| Tasks per node | 16 (match `processor_count` in `sim_config.ini`) |
| Memory | 160 GB |

> Update `--mail-user` in `HPC_run.sh` with your email to receive job notifications.

---

## Last Updated 14/04/26
