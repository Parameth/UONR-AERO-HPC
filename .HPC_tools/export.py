import ansys.fluent.core as pyfluent

# --- Export options ---
sim_name = "Wheel-Dev-001-pv"
file_name = "INSERT FILE NAME HERE"  # e.g. "Wheel-Dev-001.cas.h5"

# --- Fluent ---
solver = pyfluent.launch_fluent(mode='solver', precision='double', processor_count=16)

solver.settings.file.read_case_data(file_name = file_name)

solver.settings.file.export.ensight_gold(
    cellzones= ['Cell_Domains'], 
    cell_func_domain_export = ['ANSYS_Variables.txt'], 
    file_name=sim_name
)

solver.exit()