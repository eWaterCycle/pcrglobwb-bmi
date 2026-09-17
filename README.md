# PCR-GLOBWB — BMI/eWaterCycle adaptation

## Purpose

This version was developed as part of my TU Delft Masters' thesis project to model the Aral Sea.

The original PCR-GLOBWB2 model and its documentation remain the reference for the underlying model methodology. This repository documents the modifications and adaptations made for this version of the model in order for my research and for possible ewatercycle integration.


This is a fork of the original PCR-GLOBWB repository. For the original model, documentation, and source code, please refer to the links below.

- **Original PCR-GLOBWB2 repository:** [`PCR-GLOBWB model on GitHub`](https://github.com/UU-Hydro/PCR-GLOBWB_model)
- **Original PCR-GLOBWB2 documentation:** [`documentation.md`](Original_documentation.md)

For implementation using BMI in ewatercycle:

- **eWatercycle:** [`ewatercycle on GitHub`](https://github.com/eWaterCycle)
- **eWatercycle PCRGLOBWB2 plugin:**  [`eWatercycle PCRGLOBWB2 plugin`](https://github.com/eWaterCycle/ewatercycle-pcrglobwb)

## Modifications

The main modifications made in this fork are:

- Updated the BMI implementation to the current version (2.0) to enable use within the ewatercycle framework
- added set_channel storage & set_satDegUpp (and template to add more model state interaction) using the updated BMI
- added parameter multipliers for calibration.
- Updated the Dockerfile to support containerized execution of PCR-GLOBWB and its required dependencies
- fixed XY swap of coordinates

- Removed unnecessary files



## Miscellaneous

WSL and Docker: Use WSL together with the Docker CLI to build (and run) containers. Docker Desktop for Windows is not recommended, as the original model was developed and tested in a Linux environment and may not work reliably with Docker Desktop for Windows.