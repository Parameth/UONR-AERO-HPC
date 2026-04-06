---
name: Bug Report
about: Where it broke (DELETE as appropriate) — PIPELINE/MESHING/SOLVER/POSTPRO
title: "[BUG] <short description>"
labels: bug
assignees: Parameth
---

## What happened?

_Describe the issue clearly. What did you expect vs. what actually occurred?_

## Where did it fail?

- [ ] `HPC_run.sh` (SLURM / environment setup)
- [ ] `HPCRUN.py` (main pipeline / meshing / solving)
- [ ] `HPCPOST.py` (ParaView post-processing)
- [ ] `sim_config.ini` (configuration parsing)
- [ ] Other: ___

## Steps to reproduce

1. 
2. 
3. 

## Relevant `sim_config.ini` settings

```ini
# Paste the relevant section(s) here — redact anything sensitive
```

## Error output / log snippet

```
# Paste from logs/<job-name>-<job-id>.out or log_run / log_post
```

## Environment

| Field | Value |
|---|---|
| Script version | e.g. V1.2.0 |
| ANSYS version | e.g. 24R1 |
| HPC partition | e.g. defq |
| Python version | e.g. 3.10 |
| Run mode | `operations` / `debug` |

## Anything else?

_CAD file name, mesh size, processor count, anything unusual about this run._
