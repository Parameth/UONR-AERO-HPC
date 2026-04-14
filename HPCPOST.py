import paraview
paraview.options.offscreen = True

from paraview.simple import *
from pathlib import Path
import configparser

# ============================================================
# PATH SETUP
# ============================================================

ScriptDir = Path(__file__).resolve().parent

# ============================================================
# CONFIG
# ============================================================

ini_path = ScriptDir / "sim_config.ini"
if not ini_path.exists():
    raise FileNotFoundError(f"[CONFIG] sim_config.ini not found at {ini_path}")
ini = configparser.ConfigParser()
ini.read(ini_path)
mode = ini.get('config', 'mode', fallback='operations')
p    = 'debug_' if mode == 'debug' else ''
pp   = f'{p}postpro'

initials = ini.get(f'{p}simulation', 'user_initials')
sim_date = ini.get(f'{p}simulation', 'sim_date')
sim_num  = ini.get(f'{p}simulation', 'sim_number')
CASENAME = f"{initials}-{sim_date}-{sim_num}"
FilePath = Path.cwd() / CASENAME / "ensight" / f"{CASENAME}.encas"

print(f"[INIT] Case: {CASENAME}")
print(f"[INIT] Case file: {FilePath}")

IMAGE_WIDTH  = ini.getint(pp, 'image_width')
IMAGE_HEIGHT = ini.getint(pp, 'image_height')
ASPECT_RATIO = IMAGE_WIDTH / IMAGE_HEIGHT

X_START    = ini.getfloat(pp, 'x_start')
X_END      = ini.getfloat(pp, 'x_end')
Y_START    = ini.getfloat(pp, 'y_start')
Y_END      = ini.getfloat(pp, 'y_end')
SLICE_STEP = ini.getfloat(pp, 'slice_step')

XPLANE_YMIN = ini.getfloat(pp, 'xplane_ymin')
XPLANE_YMAX = ini.getfloat(pp, 'xplane_ymax')
XPLANE_ZMIN = ini.getfloat(pp, 'xplane_zmin')
XPLANE_ZMAX = ini.getfloat(pp, 'xplane_zmax')

YPLANE_XMIN = ini.getfloat(pp, 'yplane_xmin')
YPLANE_XMAX = ini.getfloat(pp, 'yplane_xmax')
YPLANE_ZMIN = ini.getfloat(pp, 'yplane_zmin')
YPLANE_ZMAX = ini.getfloat(pp, 'yplane_zmax')

VELOCITY     = ini.getfloat(f'{p}solver', 'velocity')
AIR_DENSITY  = ini.getfloat(pp, 'air_density')
DYN_PRESSURE = 0.5 * AIR_DENSITY * VELOCITY**2

CPT_CMIN    = ini.getfloat(pp, 'cpt_cmin')
CPT_CMAX    = ini.getfloat(pp, 'cpt_cmax')
CP0_CMIN    = ini.getfloat(pp, 'cp0_cmin')
CP0_CMAX    = ini.getfloat(pp, 'cp0_cmax')
VTXMAG_CMIN = ini.getfloat(pp, 'vtxmag_cmin')
VTXMAG_CMAX = ini.getfloat(pp, 'vtxmag_cmax')

# Output folders
PostProFolder = FilePath.parent.parent / "Post-Pro"
PostProFolder.mkdir(exist_ok=True)
BI_Folder = PostProFolder / "Base_Images"
BI_Folder.mkdir(exist_ok=True)

print(f"[INIT] Output folder: {BI_Folder}")

# ============================================================
# UTILITIES
# ============================================================

def SubFolderGen(parent, name):
    p = parent / name
    p.mkdir(exist_ok=True)
    return p


def configure_render_view(view):
    print("[VIEW] Configuring render view...")
    layout = GetLayout()
    layout.SetSize(IMAGE_WIDTH, IMAGE_HEIGHT)
    view.InteractionMode = '2D'
    view.CameraParallelProjection = 1
    view.UseLight = 0
    view.Update()
    print("[VIEW] Render view configured.")


def save_ss(view, filename):
    Render(view)
    SaveScreenshot(
        filename=str(filename),
        viewOrLayout=view,
        ImageResolution=[IMAGE_WIDTH, IMAGE_HEIGHT],
    )

# ============================================================
# CAMERA SETUP
# ============================================================

def setup_xplane_camera(view, x):
    y_half = 0.5 * (XPLANE_YMAX - XPLANE_YMIN)
    z_half = 0.5 * (XPLANE_ZMAX - XPLANE_ZMIN)
    parallel_scale = max(z_half, y_half / ASPECT_RATIO)
    zc = XPLANE_ZMIN + parallel_scale
    view.CameraPosition      = [x + 1.0, 0.0, zc]
    view.CameraFocalPoint    = [x,        0.0, zc]
    view.CameraViewUp        = [0, 0, 1]
    view.CameraParallelScale = parallel_scale
    view.Update()


def setup_yplane_camera(view, y):
    z_half = 0.5 * (YPLANE_ZMAX - YPLANE_ZMIN)
    zc     = YPLANE_ZMIN + z_half
    xc     = 0.5 * (YPLANE_XMIN + YPLANE_XMAX)
    x_half = 0.5 * (YPLANE_XMAX - YPLANE_XMIN)
    parallel_scale = max(z_half, x_half / ASPECT_RATIO)
    view.CameraPosition      = [xc, y + 1.0, zc]
    view.CameraFocalPoint    = [xc, y,        zc]
    view.CameraViewUp        = [0, 0, 1]
    view.CameraParallelScale = parallel_scale
    view.Update()

# ============================================================
# COLOR LOCK
# ============================================================

def lock_color(display, field, preset, cmin, cmax, view):
    print(f"[COLOR] Applying colormap '{preset}' to field '{field}' [{cmin}, {cmax}]")
    ColorBy(display, ('POINTS', field))
    display.RescaleTransferFunctionToDataRange(False, False)
    display.MapScalars = 1
    display.DisableLighting = 1
    display.SetScalarBarVisibility(view, True)

    lut = GetColorTransferFunction(field)
    lut.ApplyPreset(preset, True)
    lut.RescaleTransferFunction(cmin, cmax)

    pLUT = GetOpacityTransferFunction(field)
    pLUT.RescaleTransferFunction(cmin, cmax)

    view.Update()

# ============================================================
# SLICE GENERATION
# ============================================================

def generate_slices(data, field, preset, cmin, cmax, name, view):
    print(f"\n[SLICES] Starting '{name}' ...")
    out = SubFolderGen(BI_Folder, name)
    print(f"[SLICES] Output subfolder: {out}")

    # X planes
    print(f"[SLICES] [{name}] Generating X planes...")
    sx = Slice(Input=data)
    sx.SliceType = 'Plane'
    sx.SliceType.Normal = [1, 0, 0]
    dx = Show(sx, view)
    lock_color(dx, field, preset, cmin, cmax, view)

    nX = int(abs(X_START - X_END) / SLICE_STEP) + 1
    print(f"[SLICES] [{name}] X planes: {nX} frames (x={X_START:.2f} to {X_END:.2f})")
    for i in range(nX):
        x = X_START - i * SLICE_STEP
        sx.SliceType.Origin = [x, 0, 0]
        setup_xplane_camera(view, x)
        save_ss(view, out / f"{name}_X_{i:04d}.png")
        if i % 100 == 0:
            print(f"[SLICES] [{name}] X plane {i}/{nX} (x={x:.3f})")

    print(f"[SLICES] [{name}] X planes done.")
    Hide(sx, view)
    Delete(sx)

    # Y planes
    print(f"[SLICES] [{name}] Generating Y planes...")
    sy = Slice(Input=data)
    sy.SliceType = 'Plane'
    sy.SliceType.Normal = [0, 1, 0]
    dy = Show(sy, view)
    lock_color(dy, field, preset, cmin, cmax, view)

    nY = int(abs(Y_START - Y_END) / SLICE_STEP) + 1
    print(f"[SLICES] [{name}] Y planes: {nY} frames (y={Y_START:.2f} to {Y_END:.2f})")
    for i in range(nY):
        y = Y_START - i * SLICE_STEP
        sy.SliceType.Origin = [0, y, 0]
        setup_yplane_camera(view, y)
        save_ss(view, out / f"{name}_Y_{i:04d}.png")
        if i % 100 == 0:
            print(f"[SLICES] [{name}] Y plane {i}/{nY} (y={y:.3f})")

    print(f"[SLICES] [{name}] Y planes done.")
    Hide(sy, view)
    Delete(sy)

    print(f"[SLICES] '{name}' complete.")

# ============================================================
# MAIN EXECUTION
# ============================================================

print("\n[MAIN] Loading case file...")
CaseFile = EnSightReader(CaseFileName=str(FilePath))
CaseFile.PointArrays = ['pressure', 'total_pressure', 'vorticity_mag']
print("[MAIN] Case file loaded.")

print("[MAIN] Applying reflection...")
CaseFile = Reflect(Input=CaseFile, CopyInput=1)
CaseFile.Plane = 'Y'
print("[MAIN] Reflection applied.")

view = GetActiveViewOrCreate('RenderView')
Show(CaseFile, view)
configure_render_view(view)

print("[MAIN] Building calculators...")
CpT = Calculator(Input=CaseFile)
CpT.ResultArrayName = 'CpT'
CpT.Function = f'(total_pressure + pressure)/({DYN_PRESSURE})'
print("[MAIN] CpT calculator ready.")

Cp0 = Calculator(Input=CaseFile)
Cp0.ResultArrayName = 'Cp0'
Cp0.Function = f'(pressure)/({DYN_PRESSURE})'
print("[MAIN] Cp0 calculator ready.")

HideAll()
print("[MAIN] All objects hidden. Starting slice generation...")

generate_slices(CpT,    'CpT',          'Turbo',               CPT_CMIN,    CPT_CMAX,    'CpT',    view)
generate_slices(Cp0,    'Cp0',          'Turbo',               CP0_CMIN,    CP0_CMAX,    'Cp0',    view)
generate_slices(CaseFile, 'vorticity_mag', 'Viridis (matplotlib)', VTXMAG_CMIN, VTXMAG_CMAX, 'VtxMag', view)

HideAll()
print("\n[MAIN] All done.")
