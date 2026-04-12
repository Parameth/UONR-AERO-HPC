import ansys.fluent.core as pyfluent
import configparser
import json
import os
import shutil
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull


def load_config():
    ini = configparser.ConfigParser()
    ini.read(os.path.join(os.path.dirname(__file__), "sim_config.ini"))
    mode = ini.get('config', 'mode', fallback='operations')
    p = 'debug_' if mode == 'debug' else ''
    initials = ini[f'{p}simulation']['user_initials']
    sim_date = ini[f'{p}simulation']['sim_date']
    sim_num  = ini[f'{p}simulation']['sim_number']
    sim_name = f"{initials}-{sim_date}-{sim_num}"
    return {
        'sim_name':             sim_name,
        'CAD_file':             ini[f'{p}simulation']['CAD_file'],
        'iterations':           ini.getint(f'{p}solver', 'iterations'),
        'processor_count':      ini.getint(f'{p}solver', 'processor_count'),
        'velocity':             ini.getfloat(f'{p}solver', 'velocity'),
        'zones':                json.loads(ini[f'{p}zones']['list']),
        'forces':               json.loads(ini[f'{p}forces']['list']),
        'surface_mesh_global': {
            'MaxSize':          ini.getint(f'{p}surface_mesh_global', 'max_size'),
            'MinSize':          ini.getint(f'{p}surface_mesh_global', 'min_size'),
        },
        'volume_mesh': {
            'VolumeFill':               ini[f'{p}volume_mesh']['volume_fill'],
            'GrowthRate':               ini.getfloat(f'{p}volume_mesh', 'growth_rate'),
            'TetPolyMaxCellLength':     ini.getint(f'{p}volume_mesh', 'tet_poly_max_cell_length'),
        },
        'surface_mesh_options':     json.loads(ini[f'{p}surface_mesh_options']['list']),
        'boundary_layer_options':   json.loads(ini[f'{p}boundary_layer_options']['list']),
        'refinement_zones':         json.loads(ini[f'{p}refinement_zones']['list']),
        'mrf_zones':                json.loads(ini[f'{p}mrf-zones']['data']),
        'wheels':                   json.loads(ini[f'{p}wheels']['data']),
        'pvpython_path':            ini.get(f'{p}postpro', 'pvpython_path', fallback='pvpython'),
        'run_postpro':              ini.getboolean(f'{p}postpro', 'enabled', fallback=True),
        'tyre_radius':              ini.getfloat(f'{p}vehicle', 'tyre_radius'),
        'wheelbase':                ini.getfloat(f'{p}vehicle', 'wheelbase'),
        'moment_center':            json.loads(ini[f'{p}vehicle']['moment_center']),
    }


# --- Meshing helpers ---

def add_local_sizing(tasks, opts):
    tasks['Add Local Sizing'].Arguments.set_state({
        'AddChild': 'yes',
        'BOIControlName': opts['name'],
        'BOICurvatureNormalAngle': opts['curvature_angle'],
        'BOIExecution': opts['type'],
        'BOIFaceLabelList': opts['apply_to'],
        'BOIMaxSize': opts['MaxSize'],
        'BOIMinSize': opts['MinSize'],
        'BOIZoneorLabel': 'label',
    })
    tasks['Add Local Sizing'].AddChildAndUpdate(DeferUpdate=False)


def add_refinement_box(tasks, zone):
    tasks['Create Local Refinement Regions'].Arguments.set_state({
        'BOIMaxSize': zone['BOIMaxSize'],
        'BoundingBoxObject': {
            'SizeRelativeLength': 'Directly specify coordinates',
            'Xmin': zone['Xmin'], 'Xmax': zone['Xmax'],
            'Ymin': zone['Ymin'], 'Ymax': zone['Ymax'],
            'Zmin': zone['Zmin'], 'Zmax': zone['Zmax'],
        },
        'CreationMethod': 'Box',
        'RefinementRegionsName': zone['name'],
    })
    tasks['Create Local Refinement Regions'].AddChildAndUpdate(DeferUpdate=False)


def add_boundary_layer(tasks, opts):
    args = {
        'AddChild': 'yes',
        'BLControlName': opts['name'],
        'FaceScope': {
            'GrowOn': opts['grow_on'],
            'RegionsType': opts['regions_type'],
        },
        'RegionScope': opts['region_scope'],
        'NumberOfLayers': opts['layers'],
        'TransitionRatio': opts['transition_ratio'],
        'OffsetMethodType': opts['offset_method'],
    }
    if 'label_list' in opts:
        args['BlLabelList'] = opts['label_list']
    tasks['Add Boundary Layers'].Arguments.set_state(args)
    tasks['Add Boundary Layers'].AddChildAndUpdate(DeferUpdate=False)


# --- Solver helpers ---

def add_monitor(monitor, name):
    monitor.report_files.create(name)
    monitor.report_files[name](report_defs=name)
    monitor.report_files[name](print=True)
    monitor.report_plots.create(name)
    monitor.report_plots[name](report_defs=name)
    monitor.report_plots[name](print=True)


def add_force_report(solver, monitor, name, force_vec, zones):
    solver.solution.report_definitions.force[name] = {}
    f = solver.solution.report_definitions.force[name]
    f.zones = zones
    f(force_vector=force_vec)
    f(average_over=10)
    f(retain_instantaneous_values=True)
    add_monitor(monitor, name)


# --- Fluent Post helpers ---

def calc_zy_projected_area(filepath: str) -> float:
    """Return ZY projected area from a Fluent ASCII surface export.
    Reads (y, z) node coordinates, computes convex hull area, then
    doubles for half-model symmetry."""
    yz_points = []
    with open(filepath, newline='') as f:
        header_line = f.readline()
        headers     = header_line.split()
        headers_lc  = [h.lower() for h in headers]
        y_idx       = next(i for i, h in enumerate(headers_lc) if 'y' in h and 'coord' in h)
        z_idx       = next(i for i, h in enumerate(headers_lc) if 'z' in h and 'coord' in h)
        for line in f:
            parts = line.split()
            if len(parts) < max(y_idx, z_idx) + 1:
                continue
            yz_points.append((float(parts[y_idx]), float(parts[z_idx])))

    pts  = np.array(yz_points)
    hull = ConvexHull(pts)
    return hull.volume * 2  # scipy: volume = area in 2D; *2 for half-model symmetry


def compute_aero_coefficients(solver, cfg, rho=1.225):
    velocity = cfg['velocity']
    zones    = cfg['zones']
    forces   = [tuple(f) for f in cfg['forces']]
    q        = 0.5 * rho * velocity**2

    all_surfaces = zones + list(cfg['wheels'].keys())

    for s in all_surfaces:
        solver.file.export.ascii(
            file_name         = str(Path.cwd() / f"{s}_area_coords"),
            surface_name_list = [s]
        )

    areas = {
        s: calc_zy_projected_area(str(Path.cwd() / f"{s}_area_coords"))
        for s in all_surfaces
    }

    frontal_areas = [(s, areas[s]) for s in all_surfaces]
    CL_list       = []
    CD_list       = []
    CS_list       = []

    for z in zones:
        area     = areas[z]
        zone_cl  = zone_cd = zone_cs = None

        for force_name, force_vec in forces:
            report_name = f"{force_name}-{z}"
            force_val   = solver.solution.report_definitions.force[report_name].compute()

            if force_vec[2] != 0:    # Z component → Lift
                zone_cl = force_val / (q * area)
            elif force_vec[0] != 0:  # X component → Drag
                zone_cd = force_val / (q * area)
            elif force_vec[1] != 0:  # Y component → Side
                zone_cs = force_val / (q * area)

        CL_list.append((z, zone_cl))
        CD_list.append((z, zone_cd))
        CS_list.append((z, zone_cs))

    return frontal_areas, CL_list, CD_list, CS_list, q


# --- Main stages ---

def run_meshing(cfg):
    meshing = pyfluent.launch_fluent(
        mode='meshing', precision='double', processor_count=cfg['processor_count'],
    )
    workflow = meshing.workflow
    workflow.InitializeWorkflow(WorkflowType='Watertight Geometry')
    tasks = workflow.TaskObject

    tasks['Import Geometry'].Arguments.set_state({
        'FileName': cfg['CAD_file'],
        'ImportCadPreferences': {'MaxFacetLength': 0},
        'LengthUnit': 'mm',
    })
    tasks['Import Geometry'].Execute()

    for opts in cfg['surface_mesh_options']:
        add_local_sizing(tasks, opts)

    tasks['Add Local Sizing'].InsertNextTask(CommandName='CreateLocalRefinementRegions')
    for zone in cfg['refinement_zones']:
        add_refinement_box(tasks, zone)

    sm = cfg['surface_mesh_global']
    tasks['Generate the Surface Mesh'].Arguments.set_state({
        'CFDSurfaceMeshControls': {
            'MaxSize': sm['MaxSize'],
            'MinSize': sm['MinSize'],
            'ScopeProximityTo': 'faces-and-edges',
        },
    })
    tasks['Generate the Surface Mesh'].Execute()

    tasks['Generate the Surface Mesh'].InsertNextTask(CommandName='ImproveSurfaceMesh')
    tasks['Improve Surface Mesh'].Execute()

    tasks['Describe Geometry'].UpdateChildTasks(Arguments={'v1': True}, SetupTypeChanged=False)
    tasks['Describe Geometry'].Arguments.set_state({
        'NonConformal': 'No',
        'SetupType': 'The geometry consists of only fluid regions with no voids',
        'WallToInternal': 'Yes',
    })
    tasks['Describe Geometry'].UpdateChildTasks(Arguments={'v1': True}, SetupTypeChanged=True)
    tasks['Describe Geometry'].Execute()

    tasks['Update Regions'].Arguments.set_state({
        'OldRegionNameList': ['domain', 'mrf'],
        'OldRegionTypeList': ['fluid', 'dead'],
        'RegionNameList':    ['domain', 'mrf'],
        'RegionTypeList':    ['fluid', 'fluid'],
    })
    tasks['Update Boundaries'].Execute()
    tasks['Update Regions'].Execute()

    for opts in cfg['boundary_layer_options']:
        add_boundary_layer(tasks, opts)

    vm = cfg['volume_mesh']
    tasks['Generate the Volume Mesh'].Arguments.set_state({
        'VolumeFill': vm['VolumeFill'],
        'VolumeFillControls': {
            'GrowthRate': vm['GrowthRate'],
            'TetPolyMaxCellLength': vm['TetPolyMaxCellLength'],
        },
    })
    tasks['Generate the Volume Mesh'].Execute()

    tasks['Generate the Volume Mesh'].InsertNextTask(CommandName=r'ImproveVolumeMesh')
    tasks['Improve Volume Mesh'].Execute()

    return meshing.switch_to_solver()


def setup_solver(solver, cfg):
    bc = solver.setup.boundary_conditions
    velocity = cfg['velocity']
    zones = cfg['zones']
    monitor = solver.solution.monitor

    bc.velocity_inlet["inlet"].momentum.velocity.value = velocity

    bc.wall["walls"].momentum.shear_bc.set_state("Specified Shear")

    ground = bc.wall["ground"]
    ground.momentum.motion_bc.set_state("Moving Wall")
    ground.momentum.vmag.value = velocity
    ground.momentum(wall_translation=[0, 1, 0])

    for wheel_name, whl in cfg['wheels'].items():
        w = bc.wall[wheel_name]
        w.momentum.motion_bc.set_state("Moving Wall")
        w.momentum(rotating=True)
        w.momentum(relative=False)
        w.momentum(omega=whl['omega'])
        w.momentum(rotation_axis_origin=whl['rotation_axis_origin'])
        w.momentum(rotation_axis_direction=whl['rotation_axis_direction'])

    for mrf_name, mrf_data in cfg['mrf_zones'].items():
        mrf = solver.setup.cell_zone_conditions.fluid[mrf_name]
        mrf.reference_frame.frame_motion = True
        mrf.reference_frame(reference_frame_axis_origin=mrf_data['rotation_axis_origin'])
        mrf.reference_frame(mrf_omega=mrf_data['omega'])
        mrf.reference_frame(reference_frame_axis_direction=mrf_data['rotation_axis_direction'])

    solver.solution.report_definitions.flux["mfr"] = {}
    solver.solution.report_definitions.flux["mfr"].boundaries = ["inlet", "outlet"]
    add_monitor(monitor, "mfr")

    forces = [tuple(f) for f in cfg['forces']]

    for force_name, force_vec in forces:
        add_force_report(solver, monitor, force_name, force_vec, zones)

    for z in zones:
        for force_name, force_vec in forces:
            add_force_report(solver, monitor, f"{force_name}-{z}", force_vec, [z])

    solver.solution.report_definitions.moment["aero_balance_moment"] = {}
    rm = solver.solution.report_definitions.moment["aero_balance_moment"]
    rm.zones = zones
    rm(mom_axis=[0, 1, 0])
    rm(mom_center=cfg['moment_center'])
    rm(average_over=10)
    rm(retain_instantaneous_values=True)
    
    solver.setup.reference_values.velocity.set_state(velocity)


def run_fluent_post(solver, cfg):
    frontal_areas, CL_list, CD_list, CS_list, q = compute_aero_coefficients(solver, cfg)

    forces    = [tuple(f) for f in cfg['forces']]
    wheelbase = cfg['wheelbase']

    downforce_name  = next(name for name, vec in forces if vec[2] != 0)
    total_downforce = solver.solution.report_definitions.force[downforce_name].compute()
    moment_coeff    = solver.solution.report_definitions.moment["aero_balance_moment"].compute()
    rear_moment_val = moment_coeff * q  # CM * q (ref area = 1 m², ref length = 1 m)

    front_downforce = rear_moment_val / wheelbase
    rear_downforce  = total_downforce - front_downforce
    aero_balance    = front_downforce / total_downforce if total_downforce != 0 else 0

    return frontal_areas, CL_list, CD_list, CS_list, front_downforce, rear_downforce, aero_balance


def results_file(cfg, frontal_areas, CL_list, CD_list, CS_list, solver, front_downforce, rear_downforce, aero_balance):
    import datetime
    sim_name = cfg['sim_name']
    velocity = cfg['velocity']
    zones    = cfg['zones']
    forces   = [tuple(f) for f in cfg['forces']]
    rho      = 1.225
    q        = 0.5 * rho * velocity**2
    out_dir  = Path.cwd() / sim_name
    out_dir.mkdir(exist_ok=True)

    all_surfaces = zones + list(cfg['wheels'].keys())
    total_area = solver.results.report.projected_surface_area(
        surfaces=all_surfaces, min_feature_size=0.01, proj_plane_norm_comp=[1, 0, 0]
    )

    total_forces = {
        name: solver.solution.report_definitions.force[name].compute()
        for name, _ in forces
    }

    coeff_labels = {0: "CD", 1: "CS", 2: "CL"}
    fmt = lambda v: f"{v:>8.4f}" if v is not None else f"{'N/A':>8}"

    total_rows = "\n".join(
        f"  {name:<14} {total_forces[name]:>10.3f} N    {coeff_labels[next(i for i,v in enumerate(vec) if v != 0)]}: {total_forces[name] / (q * total_area):>8.4f}"
        for name, vec in forces
    )
    zone_rows = "\n".join(
        f"  {z:<12} | {frontal_areas[i][1]:>9.4f} | {fmt(CL_list[i][1])} | {fmt(CD_list[i][1])} | {fmt(CS_list[i][1])}"
        for i, z in enumerate(zones)
    )
    sum_area = sum(frontal_areas[i][1] for i in range(len(zones)))
    sum_cl   = sum(CL_list[i][1] for i in range(len(zones)) if CL_list[i][1] is not None)
    sum_cd   = sum(CD_list[i][1] for i in range(len(zones)) if CD_list[i][1] is not None)
    sum_cs   = sum(CS_list[i][1] for i in range(len(zones)) if CS_list[i][1] is not None)
    zone_total = f"  {'TOTAL':<12} | {sum_area:>9.4f} | {sum_cl:>8.4f} | {sum_cd:>8.4f} | {sum_cs:>8.4f}"

    report = f"""\
=======================================================
  SIMULATION RESULTS: {sim_name}
=======================================================
  Date:        {datetime.date.today().strftime('%d/%m/%Y')}
  Velocity:    {velocity} m/s
  Iterations:  {cfg['iterations']}
  Zones:       {', '.join(zones)}
  Air Density: {rho} kg/m³
  Dyn Press:   {q:.2f} Pa

-------------------------------------------------------
  TOTAL (ALL ZONES)
-------------------------------------------------------
{total_rows}

-------------------------------------------------------
  PER-ZONE BREAKDOWN
-------------------------------------------------------
  {'Zone':<12} | {'Area (m²)':>9} | {'CL':>8} | {'CD':>8} | {'CS':>8}
  {'─' * 52}
{zone_rows}
  {'─' * 52}
{zone_total}

-------------------------------------------------------
  AERO BALANCE
-------------------------------------------------------
  Front Downforce: {front_downforce:>10.3f} N
  Rear Downforce:  {rear_downforce:>10.3f} N
  Aero Balance:    {aero_balance * 100:>9.2f} % front
=======================================================
"""

    (out_dir / f"{sim_name}-results.txt").write_text(report)


def save_results(solver, cfg):
    sim_name    = cfg['sim_name']
    zones       = cfg['zones']
    out_dir     = Path.cwd() / sim_name
    ensight_dir = out_dir / "ensight"
    out_dir.mkdir(exist_ok=True)
    ensight_dir.mkdir(exist_ok=True)

    solver.file.write(file_type="case", file_name=str(out_dir / f"{sim_name}-1k.cas"))
    solver.file.write(file_type="data", file_name=str(out_dir / f"{sim_name}-1k.dat"))

    solver.file.export.ensight_gold(
        cellzones=['domain', 'mrf'],
        cell_func_domain_export=['pressure', 'total-pressure', 'vorticity-mag'],
        file_name=str(out_dir / sim_name),
    )

    for z in zones:
        export_path = str(Path.cwd() / f"{z}_area_coords")
        solver.file.export.ascii(
            file_name          = export_path,
            surface_name_list  = [z],
            cell_func_domain   = ["z-coordinate", "y-coordinate"],
        )


def move_results(solver, cfg):
    sim_name    = cfg['sim_name']
    out_dir     = Path.cwd() / sim_name
    plots_dir   = out_dir / "plots"
    out_dir.mkdir(exist_ok=True)
    plots_dir.mkdir(exist_ok=True)
    graphics = solver.results.graphics
    monitor  = solver.solution.monitor

    for out_file in Path.cwd().glob("*.out"):
        shutil.move(str(out_file), str(out_dir / out_file.name))

    monitor.residual.plot()
    graphics.picture.save_picture(file_name=str(plots_dir / f"{sim_name}-residuals-plot.png"))

    for name in [f[0] for f in cfg['forces']] + ["mfr"]:
        monitor.report_plots[name].plot()
        graphics.picture.save_picture(file_name=str(plots_dir / f"{sim_name}-{name}-plot.png"))


def main():
    cfg = load_config()
    solver = run_meshing(cfg)
    try:
        setup_solver(solver, cfg)
        solver.solution.initialization.hybrid_initialize()
        solver.solution.run_calculation.iterate(iter_count=cfg['iterations'])
        save_results(solver, cfg)
        frontal_areas, CL_list, CD_list, CS_list, front_df, rear_df, aero_bal = run_fluent_post(solver, cfg)
        results_file(cfg, frontal_areas, CL_list, CD_list, CS_list, solver, front_df, rear_df, aero_bal)
        move_results(solver, cfg)
    finally:
        solver.exit()


if __name__ == "__main__":
    main()
