import ansys.fluent.core as pyfluent

# --- Solve options ---
iterations = 1000
sim_name = "Wheel-Dev-001"
file_name = "INSERT FILE NAME HERE"  # e.g. "Wheel-Dev-001.cas"

# --- Solver ---
solver = pyfluent.launch_fluent(mode='solver', precision='double', processor_count=16)

solver.file.read_case("path/to/case_file.cas")
solver.solution.initialization.hybrid_initialize()
solver.solution.run_calculation.iterate(iter_count=iterations)

solver.file.write(file_type="case", file_name=f"{sim_name}.cas")
solver.file.write(file_type="data", file_name=f"{sim_name}.dat")

solver.exit()