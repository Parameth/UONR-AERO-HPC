import ansys.fluent.core as pyfluent
import configparser
import json
import os
import shutil
from pathlib import Path


def load_config():
    ini = configparser.ConfigParser()
    ini.read(os.path.join(os.path.dirname(__file__), "sim_config.ini"))
    mode = ini.get('config', 'mode', fallback='operations')
    p = 'debug_' if mode == 'debug' else ''
    return {
        'sim_name':             ini[f'{p}simulation']['sim_name'],
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

    solver.setup.reference_values.velocity.set_state(velocity)


def save_results(solver, cfg):
    sim_name = cfg['sim_name']
    out_dir  = Path.cwd() / sim_name
    out_dir.mkdir(exist_ok=True)
    graphics = solver.results.graphics
    monitor  = solver.solution.monitor

    for out_file in Path.cwd().glob("*.out"):
        shutil.move(str(out_file), str(out_dir / out_file.name))

    solver.file.write(file_type="case", file_name=str(out_dir / f"{sim_name}-1k.cas"))
    solver.file.write(file_type="data", file_name=str(out_dir / f"{sim_name}-1k.dat"))

    solver.file.export.ensight_gold(
        cellzones=['domain', 'mrf'],
        cell_func_domain_export=['pressure', 'total-pressure', 'vorticity-mag', 'skin-friction-coef'],
        file_name=str(out_dir / sim_name),
    )

    monitor.residual.plot()
    graphics.picture.save_picture(file_name=str(out_dir / f"{sim_name}-residuals-plot.png"))

    for name in [f[0] for f in cfg['forces']] + ["mfr"]:
        monitor.report_plots[name].plot()
        graphics.picture.save_picture(file_name=str(out_dir / f"{sim_name}-{name}-plot.png"))


def main():
    cfg = load_config()
    solver = run_meshing(cfg)
    try:
        setup_solver(solver, cfg)
        solver.solution.initialization.hybrid_initialize()
        solver.solution.run_calculation.iterate(iter_count=cfg['iterations'])
        save_results(solver, cfg)
    finally:
        solver.exit()

if __name__ == "__main__":
    main()
