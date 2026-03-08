import ansys.fluent.core as pyfluent
import configparser
import json
import os

# --- Importing helper functions from HPCRUN.py ---
import HPCRUN as run


def load_config(section='Wheel_MRF'):
    ini = configparser.ConfigParser()
    ini.read(os.path.join(os.path.dirname(__file__), "debug_sims_congfig.ini"))
    s = ini[section]
    return {
        'sim_name':           s['sim_name'],
        'CAD_file':           s['cad_file'],
        'iterations':         ini.getint(section, 'iterations'),
        'processor_count':    ini.getint(section, 'processor_count'),
        'velocity':           ini.getfloat(section, 'velocity'),
        'forces':             json.loads(s['forces_list']),
        'surface_mesh_global': {
            'MaxSize':        ini.getfloat(section, 'max_size'),
            'MinSize':        ini.getfloat(section, 'min_size'),
        },
        'volume_mesh': {
            'VolumeFill':           s['volume_fill'],
            'GrowthRate':           ini.getfloat(section, 'growth_rate'),
            'TetPolyMaxCellLength': ini.getint(section, 'tet_poly_max_cell_length'),
        },
        'surface_mesh_options':   json.loads(s['surface_mesh_list']),
        'boundary_layer_options': json.loads(s['boundary_layer_list']),
        'refinement_zones':       json.loads(s['refinement_list']),
        'mrf_zones':              json.loads(s['mrf_zones_data']),
        'wheels':                 json.loads(s['wheels_data']),
    }


def run_meshing(cfg, run):
    meshing = pyfluent.launch_fluent(
        mode='meshing', precision='double', processor_count=cfg['processor_count']
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
        run.add_local_sizing(tasks, opts)

    tasks['Add Local Sizing'].InsertNextTask(CommandName='CreateLocalRefinementRegions')
    for zone in cfg['refinement_zones']:
        run.add_refinement_box(tasks, zone)

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
        run.add_boundary_layer(tasks, opts)

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

def setup_solver(solver, cfg, run):
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
    run.add_monitor(monitor, "mfr")

    forces = [tuple(f) for f in cfg['forces']]

    for force_name, force_vec in forces:
        run.add_force_report(solver, monitor, force_name, force_vec, zones)

    for z in zones:
        for force_name, force_vec in forces:
            run.add_force_report(solver, monitor, f"{force_name}-{z}", force_vec, [z])

    solver.setup.reference_values.velocity.set_state(velocity)


def save_results(solver, cfg, run):
    pass


def main():
    cfg = load_config(section='Wheel_MRF')
    solver = run_meshing(cfg, run)
    try:
        setup_solver(solver, cfg, run)
        solver.solution.initialization.hybrid_initialize()
        solver.solution.run_calculation.iterate(iter_count=cfg['iterations'])
        # save_results(solver, cfg, run)
    finally:
        solver.exit()


if __name__ == "__main__":
    main()
