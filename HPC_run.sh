#!/bin/bash
#SBATCH --time=12:00:00
#SBATCH --job-name=FullCar
#SBATCH --partition=defq
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH --mem=160gb
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.out

# --- Email notifications ---
#SBATCH --mail-user=e # Replace with your email address
#SBATCH --mail-type=BEGIN,END,FAIL

FLUENTNODEFILE=$(mktemp)
scontrol show hostnames > $FLUENTNODEFILE
echo "Running on nodes:"
cat $FLUENTNODEFILE
echo "### Starting at: $(date) ###"
module load ansys-uon/2024R1
module load openmpi-uoneasy/4.1.6-GCC-13.2.0
module load python-uoneasy/3.11.5-GCCcore-13.2.0
module load paraview-uoneasy/5.13.2-foss-2023a-UCX-1.15.0 
 
# Define Fluent environment
export AWP_ROOT241='/gpfs01/software/ansys_inc/v241'

python -m venv ansys
source ansys/bin/activate
pip install ansys.fluent.core
pip install opencv-python	
pip install tqdm
pip install scipy
 
source ansys/bin/activate
python HPCRUN.py > log_run 2>&1

pvbatch HPCPOST.py > log_post 2>&1
 
echo "### Ending at: $(date) ###"