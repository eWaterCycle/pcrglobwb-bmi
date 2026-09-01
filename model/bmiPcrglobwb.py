#! /usr/bin/env python
from __future__ import print_function

from configuration import Configuration
from pcrglobwb import PCRGlobWB
import pcraster as pcr
import numpy as np
from currTimeStep import ModelTime
import sys
import logging
import variable_list
from reporting import Reporting
from imagemean import downsample
from bmi import EBmi
from bmi import BmiGridType
import virtualOS as vos
import datetime


logger = logging.getLogger(__name__)


class BmiPCRGlobWB(EBmi):
    #we use the same epoch as pcrglobwb netcdf reporting
    def days_since_industry_epoch(self, modeltime):
        return (modeltime - datetime.date(1901, 1, 1)).days

    def in_modeltime(self, days_since_industry_epoch):
        return (datetime.datetime(1901, 1, 1) + datetime.timedelta(days=days_since_industry_epoch)).date()

    def calculate_shape(self):
        # return pcr.pcr2numpy(self.model.landmask, 1e20).shape
        return (pcr.clone().nrRows(), pcr.clone().nrCols())

    #BMI initialize (as a single step)
    def initialize(self, fileName):
        self.initialize_config(fileName)
        self.initialize_model()

    #EBMI initialize (first step of two)
    def initialize_config(self, fileName):
        logger.info("PCRGlobWB: initialize_config")

        try:

            self.configuration = Configuration(fileName, relative_ini_meteo_paths = False) #changed to False to avoid problems with relative paths
            pcr.setclone(self.configuration.cloneMap)

            # set start and end time based on configuration
            self.model_time = ModelTime()
            self.model_time.getStartEndTimeSteps(self.configuration.globalOptions['startTime'],
                                             self.configuration.globalOptions['endTime'])

            self.model_time.update(0)

            self.shape = self.calculate_shape()

            logger.info("Shape of maps is %s", str(self.shape))

            self.model = None

            self._ensure_prefactor_store()
            self._read_prefactor()

        except:
            import traceback
            traceback.print_exc()
            raise


    #EBMI initialize (second step of two)
    def initialize_model(self):
        if self.model is not None:
            #already initialized
            return

        try:

            logger.info("PCRGlobWB: initialize_model")

            initial_state = None
            self.model = PCRGlobWB(self.configuration, self.model_time, initial_state)

            self.reporting = Reporting(self.configuration, self.model, self.model_time)

            self._ensure_prefactor_store()
            if self._prefactor_baseline is None:
                self._capture_prefactor_baseline()
                
            self._apply_static_prefactors()

            logger.info("Shape of maps is %s", str(self.shape))

            logger.info("PCRGlobWB Initialized")

        except:
            import traceback
            traceback.print_exc()
            raise

    def _ensure_prefactor_store(self):
        if hasattr(self, "_prefactors"):
            if not hasattr(self, "_prefactor_baseline"):
                self._prefactor_baseline = None
            return

        self._prefactors = {
            "linear_multiplier_for_degreeDayFactor": 1.0,
            "linear_multiplier_for_minSoilDepthFrac": 1.0,
            "log_10_multiplier_for_kSat": 0.0,
            "linear_multiplier_for_storCap": 1.0,
            "log_10_multiplier_for_recessionCoeff": 0.0,
            "multiplier_for_manningsN": 1.0,
            "linear_multiplier_for_cropCoefficient": 1.0,
        }
        self._prefactor_baseline = None

    def _normalize_prefactor_name(self, attribute_name):
        name = str(attribute_name)
        if name.startswith("prefactor."):
            name = name[len("prefactor."):]

        aliases = {
            "multiplier_for_degreeDayFactor": "linear_multiplier_for_degreeDayFactor",
            "multiplier_for_minSoilDepthFrac": "linear_multiplier_for_minSoilDepthFrac",
            "multiplier_for_kSat": "log_10_multiplier_for_kSat",
            "multiplier_for_storCap": "linear_multiplier_for_storCap",
            "multiplier_for_recessionCoeff": "log_10_multiplier_for_recessionCoeff",
            "multiplier_for_cropCoefficient": "linear_multiplier_for_cropCoefficient",
        }
        return aliases.get(name, name)

    @staticmethod
    def _as_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _log_prefactors(self, message):
        logger.info(message)
        for key in sorted(self._prefactors.keys()):
            logger.info("BMI prefactor %s = %s", key, self._prefactors[key])

    def _read_prefactor(self):
        self._ensure_prefactor_store()

        if not hasattr(self, "configuration"):
            self._log_prefactors("No configuration found. BMI prefactors remain at defaults.")
            return
        if not hasattr(self.configuration, "allSections"):
            self._log_prefactors("Configuration has no sections. BMI prefactors remain at defaults.")
            return
        if "prefactorOptions" not in self.configuration.allSections:
            self._log_prefactors("No prefactorOptions section found. BMI prefactors remain at defaults.")
            return

        options = {}
        for key, value in self.configuration.prefactorOptions.items():
            normalized_key = self._normalize_prefactor_name(key)
            if normalized_key in self._prefactors:
                options[normalized_key] = value

        for key, default_value in self._prefactors.items():
            if key not in options:
                continue
            self._prefactors[key] = self._as_float(options[key], default_value)

        self._log_prefactors("BMI prefactors loaded from prefactorOptions.")

    def _capture_prefactor_baseline(self):
        self._ensure_prefactor_store()

        if self.model is None:
            return

        n_layers = self.model.landSurface.numberOfSoilLayers
        baseline = {
            "numberOfSoilLayers": n_layers,
            "manningsN": self.model.routing.manningsN,
            "recessionCoeff": self.model.groundwater.recessionCoeff,
            "cover": {},
        }

        for cover_type in self.model.landSurface.coverTypes:
            land_cover = self.model.landSurface.landCoverObj[cover_type]
            cover = {
                "degreeDayFactor": land_cover.degreeDayFactor,
                "minSoilDepthFrac": land_cover.minSoilDepthFrac,
                "maxSoilDepthFrac": land_cover.maxSoilDepthFrac,
                "arnoBeta": land_cover.arnoBeta,
                "rootZoneWaterStorageMin": land_cover.rootZoneWaterStorageMin,
                "rootZoneWaterStorageRange": land_cover.rootZoneWaterStorageRange,
                "orographyBeta": land_cover.parameters.orographyBeta,
            }

            if n_layers == 2:
                cover["kSatUpp"] = land_cover.parameters.kSatUpp
                cover["kSatLow"] = land_cover.parameters.kSatLow
                cover["storCapUpp"] = land_cover.parameters.storCapUpp
                cover["storCapLow"] = land_cover.parameters.storCapLow
            elif n_layers == 3:
                cover["kSatUpp000005"] = land_cover.parameters.kSatUpp000005
                cover["kSatUpp005030"] = land_cover.parameters.kSatUpp005030
                cover["kSatLow030150"] = land_cover.parameters.kSatLow030150
                cover["storCapUpp000005"] = land_cover.parameters.storCapUpp000005
                cover["storCapUpp005030"] = land_cover.parameters.storCapUpp005030
                cover["storCapLow030150"] = land_cover.parameters.storCapLow030150
            else:
                raise ValueError("Unsupported numberOfSoilLayers: " + str(n_layers))

            baseline["cover"][cover_type] = cover

        self._prefactor_baseline = baseline

    def _apply_static_prefactors(self):
        if self.model is None:
            return

        self._ensure_prefactor_store()

        if self._prefactor_baseline is None:
            self._capture_prefactor_baseline()

        prefactors = self._prefactors
        baseline = self._prefactor_baseline
        n_layers = baseline["numberOfSoilLayers"]

        self.model.routing.manningsN = (
            prefactors["multiplier_for_manningsN"] * baseline["manningsN"]
        )

        recession_coeff = pcr.max(
            0.0,
            (10 ** prefactors["log_10_multiplier_for_recessionCoeff"])
            * baseline["recessionCoeff"],
        )
        self.model.groundwater.recessionCoeff = pcr.min(1.0, recession_coeff)

        for cover_type in self.model.landSurface.coverTypes:
            land_cover = self.model.landSurface.landCoverObj[cover_type]
            cover_baseline = baseline["cover"][cover_type]

            land_cover.degreeDayFactor = pcr.max(
                0.0,
                prefactors["linear_multiplier_for_degreeDayFactor"]
                * cover_baseline["degreeDayFactor"],
            )

            if n_layers == 2:
                land_cover.parameters.kSatUpp = pcr.max(
                    0.0,
                    (10 ** prefactors["log_10_multiplier_for_kSat"])
                    * cover_baseline["kSatUpp"],
                )
                land_cover.parameters.kSatLow = pcr.max(
                    0.0,
                    (10 ** prefactors["log_10_multiplier_for_kSat"])
                    * cover_baseline["kSatLow"],
                )

                land_cover.parameters.storCapUpp = pcr.max(
                    0.0,
                    prefactors["linear_multiplier_for_storCap"]
                    * cover_baseline["storCapUpp"],
                )
                land_cover.parameters.storCapLow = pcr.max(
                    0.0,
                    prefactors["linear_multiplier_for_storCap"]
                    * cover_baseline["storCapLow"],
                )
                land_cover.parameters.rootZoneWaterStorageCap = (
                    land_cover.parameters.storCapUpp + land_cover.parameters.storCapLow
                )
            elif n_layers == 3:
                land_cover.parameters.kSatUpp000005 = pcr.max(
                    0.0,
                    (10 ** prefactors["log_10_multiplier_for_kSat"])
                    * cover_baseline["kSatUpp000005"],
                )
                land_cover.parameters.kSatUpp005030 = pcr.max(
                    0.0,
                    (10 ** prefactors["log_10_multiplier_for_kSat"])
                    * cover_baseline["kSatUpp005030"],
                )
                land_cover.parameters.kSatLow030150 = pcr.max(
                    0.0,
                    (10 ** prefactors["log_10_multiplier_for_kSat"])
                    * cover_baseline["kSatLow030150"],
                )

                land_cover.parameters.storCapUpp000005 = pcr.max(
                    0.0,
                    prefactors["linear_multiplier_for_storCap"]
                    * cover_baseline["storCapUpp000005"],
                )
                land_cover.parameters.storCapUpp005030 = pcr.max(
                    0.0,
                    prefactors["linear_multiplier_for_storCap"]
                    * cover_baseline["storCapUpp005030"],
                )
                land_cover.parameters.storCapLow030150 = pcr.max(
                    0.0,
                    prefactors["linear_multiplier_for_storCap"]
                    * cover_baseline["storCapLow030150"],
                )
                land_cover.parameters.rootZoneWaterStorageCap = (
                    land_cover.parameters.storCapUpp000005
                    + land_cover.parameters.storCapUpp005030
                    + land_cover.parameters.storCapLow030150
                )
            else:
                raise ValueError("Unsupported numberOfSoilLayers: " + str(n_layers))

            if prefactors["linear_multiplier_for_minSoilDepthFrac"] != 1.0:
                land_cover.minSoilDepthFrac = pcr.max(
                    0.0,
                    prefactors["linear_multiplier_for_minSoilDepthFrac"]
                    * cover_baseline["minSoilDepthFrac"],
                )
                land_cover.minSoilDepthFrac = pcr.min(
                    land_cover.minSoilDepthFrac,
                    cover_baseline["maxSoilDepthFrac"],
                )
                land_cover.minSoilDepthFrac = pcr.min(1.0, land_cover.minSoilDepthFrac)

                land_cover.arnoBeta = pcr.max(
                    0.001,
                    (cover_baseline["maxSoilDepthFrac"] - 1.0)
                    / (1.0 - land_cover.minSoilDepthFrac)
                    + cover_baseline["orographyBeta"]
                    - 0.01,
                )
                land_cover.arnoBeta = pcr.cover(
                    pcr.max(0.001, land_cover.arnoBeta),
                    0.001,
                )
                land_cover.rootZoneWaterStorageMin = (
                    land_cover.minSoilDepthFrac
                    * land_cover.parameters.rootZoneWaterStorageCap
                )
                land_cover.rootZoneWaterStorageRange = (
                    land_cover.parameters.rootZoneWaterStorageCap
                    - land_cover.rootZoneWaterStorageMin
                )
            else:
                land_cover.minSoilDepthFrac = cover_baseline["minSoilDepthFrac"]
                land_cover.arnoBeta = cover_baseline["arnoBeta"]
                land_cover.rootZoneWaterStorageMin = cover_baseline[
                    "rootZoneWaterStorageMin"
                ]
                land_cover.rootZoneWaterStorageRange = cover_baseline[
                    "rootZoneWaterStorageRange"
                ]
            
            # Store crop coefficient prefactor on each land cover object for dynamic application
            land_cover.cropCoefficientPrefactor = prefactors["linear_multiplier_for_cropCoefficient"]

        logger.info("BMI static prefactors applied.")



    def update(self):
        timestep = self.model_time.timeStepPCR

        self.model_time.update(timestep + 1)

        self.model.read_forcings()
        self.model.update(report_water_balance=True)
        self.reporting.report()

    #         #numpy = pcr.pcr2numpy(self.model.landSurface.satDegUpp000005, 1e20)
    #         numpy = pcr.pcr2numpy(self.model.landSurface.satDegUpp000005, np.NaN)
    #         print numpy.shape
    #         print numpy


    def update_until(self, time):
        while self.get_current_time() + 0.001 < time:
            self.update()

    def update_frac(self, time_frac):
        raise NotImplementedError

    def finalize(self):
        pass

    def get_component_name(self):
        return "pcrglobwb"

    def get_input_var_names(self):
        return ["top_layer_soil_saturation"]

    def get_output_var_names(self):
        return ["top_layer_soil_saturation"]

    def get_var_type(self, long_var_name):
        return 'float64'

    def get_var_units(self, long_var_name):
        #TODO: this is not a proper unit
        return '1'

    def get_var_rank(self, long_var_name):
        return 0

    # def get_var_size(self, long_var_name):
    #     return np.prod(self.get_grid_shape(long_var_name))

    def get_var_nbytes(self, long_var_name):
        return self.get_var_size(long_var_name) * np.dtype(np.float64).itemsize

    def get_start_time(self):
        return self.days_since_industry_epoch(self.model_time.startTime)

    def get_current_time(self):
        return self.days_since_industry_epoch(self.model_time.currTime)

    def get_end_time(self):
        return self.days_since_industry_epoch(self.model_time.endTime)

    def get_time_step(self):
        return 1

    def get_time_units(self):
        return "Days since 1901-01-01"

    # def get_value(self, long_var_name):
    #     logger.info("getting value for var %s", long_var_name)

    #     if (long_var_name == "top_layer_soil_saturation"):

    #         if self.model is not None and hasattr(self.model.landSurface, 'satDegUpp000005'):

    #             #first make all NanS into 0.0 with cover, then cut out the model using the landmask.
    #             # This should not actually make a difference.
    #             remasked = pcr.ifthen(self.model.landmask, pcr.cover(self.model.landSurface.satDegUpp000005, 0.0))

    #             pcr.report(self.model.landSurface.satDegUpp000005, "value.map")
    #             pcr.report(remasked, "remasked.map")

    #             value = pcr.pcr2numpy(remasked, np.NaN)

    #         else:
    #             logger.info("model has not run yet, returning empty state for top_layer_soil_saturation")
    #             value = pcr.pcr2numpy(pcr.scalar(0.0), np.NaN)

    #         # print "getting var", value
    #         # sys.stdout.flush()

    #         doubles = value.astype(np.float64)

    #         # print "getting var as doubles!!!!", doubles

    #         result = np.flipud(doubles)

    #         # print "getting var as doubles flipped!!!!", result
    #         # sys.stdout.flush()

    #         return result
    #     else:
    #         raise Exception("unknown var name" + long_var_name)

    def get_value_at_indices(self, long_var_name, inds):
        raise NotImplementedError

    #     def get_satDegUpp000005_from_observation(self):
    #
    #         # assumption for observation values
    #         # - this should be replaced by values from the ECV soil moisture value (sattelite data)
    #         # - uncertainty should be included here
    #         # - note that the value should be between 0.0 and 1.0
    #         observed_satDegUpp000005 = pcr.min(1.0,\
    #                                    pcr.max(0.0,\
    #                                    pcr.normal(pcr.boolean(1)) + 1.0))
    #         return observed_satDegUpp000005

    def set_satDegUpp000005(self, src):
        mask = np.isnan(src)
        src[mask] = 1e20
        observed_satDegUpp000005 = pcr.numpy2pcr(pcr.Scalar, src, 1e20)

        pcr.report(observed_satDegUpp000005, "observed.map")

        constrained_satDegUpp000005 = pcr.min(1.0, pcr.max(0.0, observed_satDegUpp000005))

        pcr.report(constrained_satDegUpp000005, "constrained.map")

        pcr.report(self.model.landSurface.satDegUpp000005, "origmap.map")
        diffmap = constrained_satDegUpp000005 - self.model.landSurface.satDegUpp000005
        pcr.report(diffmap, "diffmap.map")

        # ratio between observation and model
        ratio_between_observation_and_model = pcr.ifthenelse(self.model.landSurface.satDegUpp000005 > 0.0,
                                                             constrained_satDegUpp000005 / \
                                                             self.model.landSurface.satDegUpp000005, 0.0)

        # updating upper soil states for all lad cover types
        for coverType in self.model.landSurface.coverTypes:
            # correcting upper soil state (storUpp000005)
            self.model.landSurface.landCoverObj[coverType].storUpp000005 *= ratio_between_observation_and_model

            # if model value = 0.0, storUpp000005 is calculated based on storage capacity (model parameter) and observed saturation degree   
            self.model.landSurface.landCoverObj[coverType].storUpp000005 = pcr.ifthenelse(
                self.model.landSurface.satDegUpp000005 > 0.0, \
                self.model.landSurface.landCoverObj[coverType].storUpp000005, \
                constrained_satDegUpp000005 * self.model.landSurface.parameters.storCapUpp000005)
            # correct for any scaling issues (value < 0 or > 1 do not make sense
            self.model.landSurface.landCoverObj[coverType].storUpp000005 = pcr.min(1.0, pcr.max(0.0,
                                                                                                self.model.landSurface.landCoverObj[
                                                                                                    coverType].storUpp000005))



    def set_value_at_indices(self, long_var_name, inds, src):
        raise NotImplementedError

    def get_grid_spacing(self, long_var_name):

        cellsize = pcr.clone().cellSize()

        return np.array([cellsize, cellsize])

    def get_grid_origin(self, long_var_name):

        north = pcr.clone().north()
        cellSize = pcr.clone().cellSize()
        nrRows = pcr.clone().nrRows()

        south = north - (cellSize * nrRows)

        west = pcr.clone().west()

        return np.array([south, west])

    def get_grid_connectivity(self, long_var_name):
        raise ValueError

    def get_grid_offset(self, long_var_name):
        raise ValueError

    #EBMI functions

    def set_start_time(self, start_time):
        self.model_time.setStartTime(self.in_modeltime(start_time))

    def set_end_time(self, end_time):
        self.model_time.setEndTime(self.in_modeltime(end_time))

    def get_attribute_names(self):
        raise NotImplementedError

    def get_attribute_value(self, attribute_name):
        raise NotImplementedError

    def set_attribute_value(self, attribute_name, attribute_value):
        raise NotImplementedError

    def save_state(self, destination_directory):
        logger.info("saving state to %s", destination_directory)
        self.model.dumpStateDir(destination_directory)

    def load_state(self, source_directory):
        raise NotImplementedError

    ###
    # UPDATES TO BMI FUNCTIONS
    ###

    def get_input_item_count(self) -> int:
        raise NotImplementedError()
    
    def get_output_item_count(self) -> int:
        raise NotImplementedError()

    def get_var_grid(self, var_name: str) -> int:
        return 0                                            #test only one grid per var, so should return first index
        #raise NotImplementedError()
    
    def get_var_itemsize(self, var_name: str) -> int:
        #raise NotImplementedError()
        var_type = self.get_var_type(var_name)
        if var_type == 'float64': #should all be this according to get_var_type
            return 8
        elif var_type == 'float32':
            return 4
        else:
            return 8  # default


        return self.get_var_type(var_name).itemsize

    def get_var_location(self, var_name: str) -> str:
        raise NotImplementedError()
    
    def get_value_ptr(self, var_name: str):
        raise NotImplementedError()
    
    def get_grid_rank(self, grid: int) -> int:
        if grid == 0:
            return 2   #2D grid
        else:
            raise ValueError(f"Invalid grid: {grid}, debug: should be 0?")   #test

    def get_grid_size(self, grid: int) -> int:
        if grid != 0:
            raise ValueError(f"Invalid grid: {grid}, debug: should be 0?")   #test
        return int(np.prod(self.shape))

        #raise NotImplementedError()
    
    def get_grid_shape(self, grid: int, shape: np.ndarray): #https://bmi.csdms.io/en/stable/bmi.grid_funcs.html#get-grid-shape
        if grid != 0:
            raise ValueError(f"Invalid grid: {grid}, debug: should be 0?")   #test
        return self.shape    #ToDo first thing tomorrow, must be self.shape?
        
        # should return(?) [rows,columns] = [ny,nx] but has ->None
        # shape[0] = pcr.clone().nrRows()  #rows = ny
        # shape[1] = pcr.clone().nrCols()  #columns = nx

        # nrows = int(pcr.clone().nrRows()) #make double sure it's int
        # ncols = int(pcr.clone().nrCols())

        # shape[0] = nrows
        # shape[1] = ncols
    def get_grid_x(self, grid: int, x: np.ndarray) -> np.ndarray:
        logging.warning("if you see this, get_grid_x is called")    
        north = pcr.clone().north()
        cellSize = pcr.clone().cellSize()
        nrRows = pcr.clone().nrRows()
        south = north - (cellSize * nrRows)
        spacing=pcr.clone().cellSize()
        return south+spacing*(np.arange(nrRows)+0.5)
        # logging.warning("if you see this swap XY happend")
        # raise NotImplementedError("if you see this swap XY happend") 

    def get_grid_y(self, grid: int, y: np.ndarray) -> np.ndarray:  #https://github.com/eWaterCycle/PCR-GLOBWB_model/blob/bmi_fixes_setters/model/bmiPcrglobwb.py
        west = pcr.clone().west()
        spacing=pcr.clone().cellSize()
        return west+spacing*(np.arange(self.shape[1])+0.5)
        #raise NotImplementedError()

    def get_grid_z(self, grid: int, z: np.ndarray) -> np.ndarray:
        raise NotImplementedError()
    
    def get_grid_type(self, grid: int) -> str:
        return "uniform_rectilinear"
    
    def get_var_size(self, long_var_name):   ##
        grid_id = self.get_var_grid(long_var_name) #should always be 0 for pcrglobwb
        return self.get_grid_size(grid=grid_id)
        #return np.prod(self.get_grid_shape(long_var_name))

    def get_value(self, var_name, dest):      #based on:  https://github.com/eWaterCycle/PCR-GLOBWB_model/blob/bmi_fixes_setters/model/bmiPcrglobwb.py
        logger.info("getting value for var %s", var_name)

        attribute = [n for n in variable_list.netcdf_short_name if variable_list.netcdf_short_name[n] == var_name][0]
        pcrdata = getattr(self.reporting, attribute)

        # if var_name in BmiPCRGlobWB.scalar_variables:
        #     dest[:] = float(pcr.pcr2numpy(pcrdata, np.NaN).flat[0])
        #     return dest
        #     #return var_name
        
        remasked = pcr.ifthen(self.model.landmask, pcr.cover(pcrdata, 0.0))
        pcr.report(pcrdata, "value.map")
        pcr.report(remasked, "remasked.map")

        result = np.flipud(pcr.pcr2numpy(remasked, np.NaN))
        dest[:] = result.flatten()
        return dest
    
    def set_value(self, long_var_name, src):

        if self.model is None:
            logger.info("cannot set value for %s, as model has not run yet.", long_var_name)
            return

        logger.info("setting value for %s", long_var_name)

        # print "got value to set", src

        src = np.reshape(src, self.shape)

        # make sure the raster is the right side up
        src = np.flipud(src)

        # print "flipped", src

        # cast to pcraster precision
        src = src.astype(np.float32)

        # print "as float 32", src

        sys.stdout.flush()

        logger.info("setting value shape %s", src.shape)

        if long_var_name == "near_surface_soil_saturation_degree":
            self.set_satDegUpp000005(src)
        elif long_var_name == "upper_soil_saturation_degree":
            self.set_satDegUpp(src)
        elif long_var_name == "channel_storage":
            self.set_channel_storage(src)
        elif long_var_name == "discharge":
            self.set_discharge(src)

        else:
            raise Exception("unknown var name: " + long_var_name)
        
        
    def set_channel_storage(self,src): #https://github.com/eWaterCycle/PCR-GLOBWB_model/blob/bmi_fixes_setters/model/bmiPcrglobwb.py
        mask = np.isnan(src)
        src[mask] = 1e20
        channel_storage = pcr.numpy2pcr(pcr.Scalar, src, 1e20)

        channel_storage = pcr.ifthen(self.model.meteo.landmask, channel_storage)
        #-----------------------------------------------------------------------

        channel_storage = pcr.max(0., channel_storage)
        channel_storage = pcr.cover( channel_storage, 0.0)
                
        self.model.routing.channelStorage = channel_storage

        self.reporting.channel_storage = pcr.ifthen(self.model.routing.landmask, self.model.routing.channelStorage)

    def set_discharge(self,src): #based on https://github.com/eWaterCycle/PCR-GLOBWB_model/blob/bmi_fixes_setters/model/bmiPcrglobwb.py
        mask = np.isnan(src)
        src[mask] = 1e20
        discharge = pcr.numpy2pcr(pcr.Scalar, src, 1e20)

        discharge = pcr.ifthen(self.model.meteo.landmask, discharge)
        #-----------------------------------------------------------------------

        discharge = pcr.max(0., discharge)
        discharge = pcr.cover( discharge, 0.0)
                
        self.model.routing.discharge = discharge

        self.reporting.discharge = pcr.ifthen(self.model.routing.landmask, self.model.routing.discharge)

    def set_satDegUpp(self, src): #https://github.com/eWaterCycle/PCR-GLOBWB_model/blob/bmi_fixes_setters/model/bmiPcrglobwb.py#L368
        mask = np.isnan(src)
        src[mask] = 1e20
        observed_satDegUpp = pcr.numpy2pcr(pcr.Scalar, src, 1e20)

        pcr.report(observed_satDegUpp, "observed.map")

        constrained_satDegUpp = pcr.min(1.0, pcr.max(0.0, observed_satDegUpp))

        pcr.report(constrained_satDegUpp, "constrained.map")

        pcr.report(self.model.landSurface.satDegUpp, "origmap.map")
        diffmap = constrained_satDegUpp - self.model.landSurface.satDegUpp
        pcr.report(diffmap, "diffmap.map")

        # ratio between observation and model
        ratio_between_observation_and_model = pcr.ifthenelse(self.model.landSurface.satDegUpp > 0.0,
                                                             constrained_satDegUpp / \
                                                             self.model.landSurface.satDegUpp, 0.0)

        # updating upper soil states for all lad cover types
        ls=self.model.landSurface
        for coverType in ls.coverTypes:
            lco=ls.landCoverObj[coverType]
            # correcting upper soil state (storUpp)
            lco.storUpp *= ratio_between_observation_and_model

            # if model value = 0.0, storUpp000005 is calculated based on storage capacity (model parameter) and observed saturation degree   
            lco.storUpp = pcr.ifthenelse(
                ls.satDegUpp > 0.0, 
                lco.storUpp, 
                constrained_satDegUpp * lco.parameters.storCapUpp)
            # correct for any scaling issues (value < 0 or > 1 do not make sense
            lco.storUpp = pcr.min(1.0, pcr.max(0.0, lco.storUpp))
            lco.satDegUpp = vos.getValDivZero(
                  lco.storUpp, 
                  lco.parameters.storCapUpp,\
                  vos.smallNumber,0.)
            lco.satDegUpp = pcr.ifthen(
             lco.landmask, 
             lco.satDegUpp)
            lco.satDegUppTotal=lco.satDegUpp
            lco.storUppTotal=lco.storUpp

        # after updating we need to propagate the changes to the dependend variables
        # proper way to do this would be to implement a state model...(see AMUSE/OMUSE) 

        self.model.landSurface.storUpp=pcr.scalar(0.0)
        self.model.landSurface.satDegUpp=pcr.scalar(0.0)
        self.model.landSurface.storUppTotal=pcr.scalar(0.0)
        self.model.landSurface.satDegUppTotal=pcr.scalar(0.0)
        
        for coverType in ls.coverTypes:
            lco=ls.landCoverObj[coverType]
            land_cover_fraction = lco.fracVegCover
            land_cover_storUpp = lco.storUpp
            land_cover_satDegUpp = lco.satDegUpp
            land_cover_storUppTotal = lco.storUppTotal
            land_cover_satDegUppTotal = lco.satDegUppTotal
            self.model.landSurface.storUpp+= land_cover_fraction * land_cover_storUpp
            self.model.landSurface.satDegUpp+= land_cover_fraction * land_cover_satDegUpp
            self.model.landSurface.storUppTotal+= land_cover_fraction * land_cover_storUppTotal
            self.model.landSurface.satDegUppTotal+= land_cover_fraction * land_cover_satDegUppTotal
            # more needed?

        self.reporting.satDegUpp=self.model.landSurface.satDegUppTotal
        self.reporting.storUpp=self.model.landSurface.storUppTotal


    






    
    def get_grid_node_count(self, grid: int) -> int:
        raise NotImplementedError()

    def get_grid_edge_count(self, grid: int) -> int:
        raise NotImplementedError()
    
    def get_grid_face_count(self, grid: int) -> int:
        raise NotImplementedError()

    def get_grid_edge_nodes(self, grid: int, edge_nodes: np.ndarray) -> np.ndarray:
        raise NotImplementedError()

    def get_grid_face_edges(self, grid: int, face_edges: np.ndarray) -> np.ndarray:
        raise NotImplementedError()

    def get_grid_face_nodes(self, grid: int, face_nodes: np.ndarray) -> np.ndarray:
        raise NotImplementedError()

    def get_grid_nodes_per_face(self, grid: int, nodes_per_face: np.ndarray) -> np.ndarray:
        raise NotImplementedError()



class ScaledBmiPCRGlobWB(BmiPCRGlobWB):
    factor = 5

    def set_value(self, long_var_name, scaled_new_value):
        # small value for comparison
        current_value = self.get_value(long_var_name)

        print('current value after scaling', current_value)

        print('value given by user', scaled_new_value)

        diff = scaled_new_value - current_value

        print("diff now", diff)

        # scale to model resolution
        big_diff = np.repeat(np.repeat(diff, self.factor, axis=0), self.factor, axis=1)

        big_current_value = BmiPCRGlobWB.get_value(self, long_var_name)

        new_value = big_current_value + big_diff

        # new_value = np.repeat(np.repeat(src, self.factor, axis=0), self.factor, axis=1)

        BmiPCRGlobWB.set_value(self, long_var_name, new_value)

    def calculate_shape(self):
        original = BmiPCRGlobWB.calculate_shape(self)

        logger.info("original shape !!! =" + str(original))

        return np.array([original[0] // self.factor, original[1] // self.factor])

    def get_value(self, long_var_name):
        big_map = BmiPCRGlobWB.get_value(self, long_var_name)

        print("getting value original shape " + str(big_map.shape))
        print("original size " + str(big_map.size))
        print("nans in original " + str(np.count_nonzero(np.isnan(big_map))))

        result = np.zeros(shape=self.get_grid_shape(long_var_name))

        downsample(big_map, result)

        print("getting value new shape " + str(result.shape))
        print("result size " + str(result.size))
        print("nans count in result " + str(np.count_nonzero(np.isnan(result))))

        print("getting value", result)
        sys.stdout.flush()

        return result

    def get_grid_spacing(self, long_var_name):
        cellsize = pcr.clone().cellSize()

        return np.array([cellsize * self.factor, cellsize * self.factor])
