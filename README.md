# UONR-AERO-HPC

University of Nottingham Racing Aerodynamics HPC Repository

## Key People
Owner - Parameth Yingchankul [UoN 2023-2026]  
Aero Lead FS27 - Frederick Blake [UoN 2024-2029]

**Current Users:**   
Parameth Yingchankul  
Frederick Blake  
Jack Tandy  

To be used within the team **if** you have access to the HPC @ UoN

## Code:
**ANSYS VERSION: 24R1**  
Python & Bash  

Refer to **requirements.txt**

Version Release: V1.1.0

## Features

- **INI-based configuration** - all simulation parameters (mesh sizes, solver settings, zones, forces, wheel definitions) are loaded from `sim_config.ini`, keeping the script separate from run-specific values
- **Automated watertight meshing** - drives Fluent's Watertight Geometry workflow end-to-end, including geometry import, surface meshing, volume meshing, and surface mesh improvement
- **MRF Wheel Internals** - moving reference frames included for the wheel spokes
- **Local surface sizing** - applies per-label sizing controls (min/max size, curvature angle, execution type) to named CAD labels
- **Refinement box zones** - creates bounding-box refinement regions with configurable coordinates and max cell size
- **Boundary layer generation** - adds named boundary layer controls with configurable first layer height, layer count, offset method, and transition ratio
- **Boundary condition setup** - configures velocity inlet, shear walls, a moving ground plane, and rotating wheels (with per-wheel axis origin, axis direction, and angular velocity)
- **Force & flux monitors** - automatically creates drag/lift/side-force report definitions and residual/flux monitors, both globally across all zones and split per zone
- **Post-processing & export** - saves `.cas` and `.dat` files, and exports residual and force convergence plots as `.png` images named after the simulation
- **Solver hand-off** - switches from meshing session to solver session in a single Fluent process, avoiding intermediate file I/O
- **Safe teardown** - wraps the solver stage in a `try/finally` block to ensure `solver.exit()` is always called

## Usage

- Download the following
- Upload to the HPC
- Use `sim_config.ini` to change the simulation name & CAD file

## Last Updated 06/03/26
