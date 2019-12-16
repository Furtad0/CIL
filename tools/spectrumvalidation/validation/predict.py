# MIT License
#
# Copyright (c) 2019 DARPA
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# This file is a part of the CIRN Interaction Language.

import logging

import geopandas as gpd
import numpy as np
import pandas as pd
from pprint import pformat
import pyflux as pf
from shapely.geometry import box

import validation.constants as constants
import validation.util as util

LOGGER = logging.getLogger(__name__)


def map_tx_detections_to_grid(tx_gdf: gpd.GeoDataFrame,
                              start_time: float, time_block_size: float, num_time_blocks: int,
                              start_freq: float, freq_block_size: float, num_freq_blocks: int,
                              grid_compute_step_size_s=30) -> gpd.GeoDataFrame:
    """
    form a regular grid of voxels, overlay the grid on the detected transmissions, and aggregate duty
    cycles appropriately

    :param tx_gdf:
    :param start_time:
    :param time_block_size:
    :param num_time_blocks:
    :param start_freq:
    :param freq_block_size:
    :param num_freq_blocks:
    :param grid_compute_step_size_s: Note that grid_compute_step_size_s/num_time_blocks MUST be an integer
    :return:
    """

    # use the spatial index to speed up finding intersections with the grid
    spatial_index = tx_gdf.sindex

    stop_time = start_time + time_block_size*num_time_blocks
    stop_freq = start_freq + freq_block_size*num_freq_blocks

    grids = []

    # loop over a subset of the whole file in the time dimension to help out with
    # N^2 computational load issues
    for t in np.arange(start_time, stop_time, grid_compute_step_size_s):
        # make a bounding box for fast transmit voxel filtering
        poly = box(minx=t, miny=0, maxx=t+grid_compute_step_size_s, maxy=1e12)

        possible_matches_index = list(spatial_index.intersection(poly.bounds))

        grid_chunk = util.merge_to_grid(in_gdf=tx_gdf.iloc[possible_matches_index],
                                        start_time=t,
                                        stop_time=t+grid_compute_step_size_s,
                                        num_time_blocks=int(grid_compute_step_size_s/time_block_size),
                                        start_freq=start_freq,
                                        stop_freq=stop_freq,
                                        num_freq_blocks=num_freq_blocks)

        grids.append(grid_chunk)

    tx_grid_gdf = gpd.GeoDataFrame(pd.concat(grids, ignore_index=True), geometry="geometry")

    # add some extra columns to help with downstream processing
    tx_grid_gdf["start_freq"] = tx_grid_gdf.geometry.bounds["miny"]

    # pyflux doesn't seem to play nice with sub-integer time index so use integer ms here
    tx_grid_gdf["start_time_ms"] = tx_grid_gdf.geometry.bounds["minx"] * 1000
    # round instead of truncate
    tx_grid_gdf["start_time_ms"] = tx_grid_gdf["start_time_ms"].round(decimals=0)
    tx_grid_gdf = tx_grid_gdf.astype({"start_freq": int,
                                      "start_time_ms": np.int64})

    # astype seems to pull us back into pandas instead of geopandas. Fix it.
    tx_grid_gdf = gpd.GeoDataFrame(tx_grid_gdf, geometry="geometry")

    return tx_grid_gdf


def pivot_grid(in_gdf: gpd.GeoDataFrame, noise_std_dev) -> pd.DataFrame:
    """
    Convert the transmit grid dataframe into a dataframe with
    the starting frequency of each grid square as a column and
    timestamps in ms as the index. Add in gaussian noise to help with
    singular matrix issues when trying to predict future values
    :param in_gdf:
    :return:
    """

    # make a copy so we don't accidentally modify the source
    tx_grid_gdf = in_gdf.copy()

    # turn any NaN duty cycle values to zeros
    tx_grid_gdf = tx_grid_gdf.fillna(value=0)

    # add some noise to the duty cycle values to prevent pyflux from having singular matrix problems later
    noise = np.abs(np.random.normal(size=len(tx_grid_gdf.index), scale=noise_std_dev))
    tx_grid_gdf["duty_cycle"] = tx_grid_gdf["duty_cycle"] + noise

    # # clip duty cycles to be between 0 and 1.0
    # tx_grid_gdf.loc[tx_grid_gdf["duty_cycle"] < 0, "duty_cycle"] = 0.0
    # tx_grid_gdf.loc[tx_grid_gdf["duty_cycle"] > 1, "duty_cycle"] = 1.0

    # switch back to pure pandas
    tx_pivot_df = pd.DataFrame(tx_grid_gdf)
    tx_pivot_df = tx_pivot_df.drop(columns=["geometry"])

    # pyflux wants column values as strings or it blows up
    tx_pivot_df["start_freq_str"] = tx_pivot_df["start_freq"].apply(str)

    # turn start frequency values into columns
    tx_pivot_df = tx_pivot_df.pivot_table(values='duty_cycle', index="start_time_ms", columns='start_freq_str',
                                          aggfunc='first')

    return tx_pivot_df


def predict_voxels(tx_pivot_df: pd.DataFrame, start_time: float, stop_time: float,
                   samples_to_predict: int, lags: int) -> pd.DataFrame:
    """
    Predict some number of output samples given an input training set
    :param tx_pivot_df:
    :param start_time: start time to limit the training set to, in seconds
    :param stop_time: stop time to limit the training set to, in seconds
    :param samples_to_predict: how many output samples to generate, in terms of the grid time block size
    :param lags: how many lags to use in prediction model
    :return:
    """

    start_time_ms = start_time*1000
    stop_time_ms = stop_time*1000

    # pandas convention is to include the last value in the range, not like what is expected with
    # python. Subtract 1 ms from the end time so we don't get that extra sample
    # generate the model
    # LOGGER.debug("training on dataset sized %i x %i",
    #              tx_pivot_df.loc[start_time_ms:stop_time_ms-1].shape[0],
    #              tx_pivot_df.loc[start_time_ms:stop_time_ms-1].shape[1])
    model = pf.VAR(data=tx_pivot_df.loc[start_time_ms:stop_time_ms-1], lags=lags, integ=0)

    # fit the model to our data
    x = model.fit()

    # generate predictions
    result_df = model.predict(h=samples_to_predict)

    # switch times back to seconds
    result_df["start_time"] = result_df.index / 1000.0

    # "unpivot" back to our original format
    result_df = result_df.melt(id_vars="start_time", var_name="start_freq", value_name='duty_cycle')

    # clip duty cycles to be between 0 and 1.0
    result_df.loc[result_df["duty_cycle"] < 0, "duty_cycle"] = 0.0
    result_df.loc[result_df["duty_cycle"] > 1, "duty_cycle"] = 1.0

    # # convert frequencies back to floats
    # result_df["start_freq"] = result_df["start_freq"].apply(float)

    return result_df


def predict_voxels2(tx_pivot_df: pd.DataFrame, start_time: float, stop_time: float,
                    samples_to_predict: int, lags: int) -> pd.DataFrame:
    """
    Predict some number of output samples given an input training set
    :param tx_pivot_df:
    :param start_time: start time to limit the training set to, in seconds
    :param stop_time: stop time to limit the training set to, in seconds
    :param samples_to_predict: how many output samples to generate, in terms of the grid time block size
    :param lags: how many lags to use in prediction model
    :return:
    """

    start_time_ms = start_time*1000
    stop_time_ms = stop_time*1000

    # pandas convention is to include the last value in the range, not like what is expected with
    # python. Subtract 1 ms from the end time so we don't get that extra sample
    # generate the model
    # LOGGER.debug("training on dataset sized %i x %i",
    #              tx_pivot_df.loc[start_time_ms:stop_time_ms-1].shape[0],
    #              tx_pivot_df.loc[start_time_ms:stop_time_ms-1].shape[1])
    model = pf.VAR(data=tx_pivot_df.loc[start_time_ms:stop_time_ms-1], lags=lags, integ=0)

    # fit the model to our data
    x = model.fit()

    # generate predictions
    result_df = model.predict(h=samples_to_predict)


    return result_df


def predict_all_voxels(tx_pivot_df: pd.DataFrame, training_len_s: float, scenario_len_s: float,
                       time_block_size: float, freq_block_size: float,
                       samples_to_predict: int, lags: int, noise_std_dev: float) -> gpd.GeoDataFrame:
    """
    Loop over the whole scenario and make predictions one second in the future
    :param tx_pivot_df:
    :param training_len_s:
    :param scenario_len_s:
    :param time_block_size: size of each grid in the time dimension, in seconds
    :param freq_block_size: size of each grid in the frequency dimension, in hz
    :param samples_to_predict:
    :param lags:
    :param noise_std_dev: unused, but keeping it so the various predict voxel algs have the same signature
    :return:
    """

    predictions = []

    for training_start_time in np.arange(0, scenario_len_s-training_len_s, samples_to_predict*time_block_size):

        LOGGER.debug("Predicting outputs for time %f to %f",
                     training_start_time+training_len_s,
                     training_start_time+training_len_s + samples_to_predict*time_block_size)

        training_stop_time = training_start_time + training_len_s

        prediction_gdf = predict_voxels(tx_pivot_df=tx_pivot_df,
                                        start_time=training_start_time,
                                        stop_time=training_stop_time,
                                        samples_to_predict=samples_to_predict,
                                        lags=lags)

        predictions.append(prediction_gdf)

    # convert back to a geodataframe
    result_df = pd.concat(predictions, ignore_index=True)
    result_df["start_freq"] = result_df["start_freq"].apply(float)
    result_gdf = result_df.set_geometry(np.vectorize(box)(result_df["start_time"],
                                                          result_df["start_freq"],
                                                          result_df["start_time"] + time_block_size,
                                                          result_df["start_freq"] + freq_block_size))

    return result_gdf


def check_for_almost_constant(tx_pivot_df: pd.DataFrame, start_time: float, stop_time: float, noise_std_dev: float):

    sample_std_dev = tx_pivot_df.loc[start_time * 1000: stop_time * 1000 - 1].std()[0]

    if sample_std_dev < 10*noise_std_dev:
        # assume values are constant
        return True
    else:
        return False


def predict_constants(tx_pivot_df: pd.DataFrame, start_time: float, stop_time: float,
                      samples_to_predict: int, delta_t_ms: int) -> pd.DataFrame:
    """
    Predict some number of output samples given an input training set
    :param tx_pivot_df: Should include only a single frequency
    :param start_time: start time to limit the training set to, in seconds
    :param stop_time: stop time to limit the training set to, in seconds
    :param samples_to_predict: how many output samples to generate, in terms of the grid time block size
    :param delta_t_ms: time step in ms
    :return:
    """

    if len(tx_pivot_df.columns) > 1:
        LOGGER.error("Must only include a single column of frequencies when using constant predictor. Found %i",
                     len(tx_pivot_df.columns))
        raise ValueError

    start_time_ms = start_time*1000
    stop_time_ms = stop_time*1000

    mean_val = tx_pivot_df.loc[start_time_ms: stop_time_ms - 1].mean()[0]

    # generate predictions
    timestamps = delta_t_ms*np.arange(1, samples_to_predict+1, dtype=np.int64) + stop_time_ms

    vals = mean_val*np.ones_like(timestamps)

    result_df = pd.DataFrame(index=timestamps, columns={tx_pivot_df.columns[0]: vals})

    return result_df


def predict_all_voxels2(tx_pivot_df: pd.DataFrame, training_len_s: float, scenario_len_s: float,
                        time_block_size: float, freq_block_size: float,
                        samples_to_predict: int, lags: int, noise_std_dev: float) -> gpd.GeoDataFrame:
    """
    Loop over the whole scenario and make predictions one second in the future
    :param tx_pivot_df:
    :param training_len_s:
    :param scenario_len_s:
    :param time_block_size: size of each grid in the time dimension, in seconds
    :param freq_block_size: size of each grid in the frequency dimension, in hz
    :param samples_to_predict:
    :param lags:
    :return:
    """

    predictions = []

    pivot_freqs = sorted(list(tx_pivot_df.columns.values.astype(np.int64)))

    result_df = tx_pivot_df.copy()
    result_df.loc[:, :] = 0.0

    # build up list of lists containing the nearest neighbors to use for predictions
    neighbors = []
    for i in range(len(pivot_freqs)):
        # handle edge case at start
        if i == 0:
            neighbors.append([str(pivot_freqs[0]), str(pivot_freqs[1])])
        # handle edge case at end
        elif i == len(pivot_freqs) - 1:
            neighbors.append([str(pivot_freqs[i - 1]), str(pivot_freqs[i])])
        else:
            neighbors.append([str(pivot_freqs[i - 1]), str(pivot_freqs[i]), str(pivot_freqs[i + 1])])

    for training_start_time in np.arange(0, scenario_len_s-training_len_s, samples_to_predict*time_block_size):

        LOGGER.debug("Predicting outputs for time %f to %f",
                     training_start_time+training_len_s,
                     training_start_time+training_len_s + samples_to_predict*time_block_size)

        training_stop_time = training_start_time + training_len_s

        for i, freq_strings in enumerate(neighbors):

            if len(tx_pivot_df.loc[training_start_time * 1000: training_stop_time * 1000]) == 0:
                LOGGER.warning(
                    "transmit grid empty for the requested timespan")


            #LOGGER.debug("freq strings: %s", freq_strings)

            try:

                neighbor_result_df = predict_voxels2(tx_pivot_df=tx_pivot_df.loc[:, freq_strings],
                                                     start_time=training_start_time,
                                                     stop_time=training_stop_time,
                                                     samples_to_predict=samples_to_predict,
                                                     lags=lags)
            except np.linalg.LinAlgError as err:
                #LOGGER.warning("data set resulted in singular matrix. Retrying with single frequency")
                if i == 0:
                    freq_string = freq_strings[0]
                else:
                    freq_string = freq_strings[1]

                try:
                    neighbor_result_df = predict_voxels2(tx_pivot_df=tx_pivot_df.loc[:, [freq_string]],
                                                         start_time=training_start_time,
                                                         stop_time=training_stop_time,
                                                         samples_to_predict=samples_to_predict,
                                                         lags=lags)
                except np.linalg.LinAlgError as err:

                    constant_training_set = check_for_almost_constant(tx_pivot_df=tx_pivot_df.loc[:, [freq_string]],
                                                                      start_time=training_start_time,
                                                                      stop_time=training_stop_time,
                                                                      noise_std_dev=noise_std_dev)
                    if constant_training_set:

                        neighbor_result_df = predict_constants(tx_pivot_df=tx_pivot_df.loc[:, [freq_string]],
                                                               start_time=training_start_time,
                                                               stop_time=training_stop_time,
                                                               samples_to_predict=samples_to_predict,
                                                               delta_t_ms=np.round(time_block_size*1000))

                    else:
                        LOGGER.error("singular matrix when trying to predict next values")
                        LOGGER.debug("training vals described: %s",
                                     tx_pivot_df.loc[training_start_time * 1000:training_stop_time * 1000 - 1, [freq_string]].describe())
                        raise err

            try:
                if i == 0:
                    #LOGGER.debug("neighbor result cols %s", neighbor_result_df.columns.values)
                    result_df.loc[neighbor_result_df.index, freq_strings[0]] = neighbor_result_df[freq_strings[0]]
                    # display(neighbor_result_df[freq_strings[0]])
                else:
                    result_df.loc[neighbor_result_df.index, freq_strings[1]] = neighbor_result_df[freq_strings[1]]
                    # display(neighbor_result_df[freq_strings[1]])
            except KeyError as err:
                LOGGER.error("key error: neighbor result index %s, freq string was %s, main index was %s",
                             neighbor_result_df.index, freq_strings[0], result_df.index[int((training_start_time-5)/0.2):int((training_stop_time+5)/0.2)])
                LOGGER.debug("start time: %f training stop time: %f freq strings: %s",
                             training_start_time, training_stop_time, freq_strings)
                LOGGER.debug("first el main index: %s, last el main index: %s, main index len: %i,",
                             result_df.index[0], result_df.index[-1], len(result_df.index))

                raise err

    # switch times back to seconds
    result_df["start_time"] = result_df.index / 1000.0

    # "unpivot" back to our original format
    result_df = result_df.melt(id_vars="start_time", var_name="start_freq", value_name='duty_cycle')

    # clip duty cycles to be between 0 and 1.0
    result_df.loc[result_df["duty_cycle"] < 0, "duty_cycle"] = 0.0
    result_df.loc[result_df["duty_cycle"] > 1, "duty_cycle"] = 1.0

    result_df["start_freq"] = result_df["start_freq"].apply(float)

    # convert back to a geodataframe
    result_gdf = result_df.set_geometry(np.vectorize(box)(result_df["start_time"],
                                                          result_df["start_freq"],
                                                          result_df["start_time"] + time_block_size,
                                                          result_df["start_freq"] + freq_block_size))

    return result_gdf


def predict_all_voxels3(tx_pivot_df: pd.DataFrame, training_len_s: float, scenario_len_s: float,
                        time_block_size: float, freq_block_size: float,
                        samples_to_predict: int, samples_to_ignore: int, lags: int,
                        noise_std_dev: float) -> gpd.GeoDataFrame:
    """
    Loop over the whole scenario and make predictions one second in the future
    :param tx_pivot_df:
    :param training_len_s:
    :param scenario_len_s:
    :param time_block_size: size of each grid in the time dimension, in seconds
    :param freq_block_size: size of each grid in the frequency dimension, in hz
    :param samples_to_predict:
    :param samples_to_ignore:
    :param lags:
    :return:
    """

    predictions = []

    pivot_freqs = sorted(list(tx_pivot_df.columns.values.astype(np.int64)))

    result_df = tx_pivot_df.copy()
    result_df.loc[:, :] = 0.0

    # build up list of lists containing a single frequency. Yes this is strange but I want to reuse code from
    # the nearest neighbors approach. If this works well I'll fix it later.
    neighbors = []
    for i in range(len(pivot_freqs)):
        neighbors.append([str(pivot_freqs[i])])

    # do sliding window
    training_data_step_size = samples_to_predict*time_block_size
    for training_start_time in np.arange(0,
                                         scenario_len_s-training_len_s,
                                         training_data_step_size):

        LOGGER.debug("Predicting outputs for time %f to %f",
                     training_start_time+training_len_s + samples_to_ignore*time_block_size,
                     training_start_time+training_len_s + (samples_to_ignore + samples_to_predict)*time_block_size)

        training_stop_time = training_start_time + training_len_s

        for i, freq_strings in enumerate(neighbors):

            if len(tx_pivot_df.loc[training_start_time * 1000: training_stop_time * 1000]) == 0:
                LOGGER.warning(
                    "transmit grid empty for the requested timespan")


            #LOGGER.debug("freq strings: %s", freq_strings)

            try:

                neighbor_result_df = predict_voxels2(tx_pivot_df=tx_pivot_df.loc[:, freq_strings],
                                                     start_time=training_start_time,
                                                     stop_time=training_stop_time,
                                                     samples_to_predict=samples_to_ignore + samples_to_predict,
                                                     lags=lags)
            except np.linalg.LinAlgError as err:

                constant_training_set = check_for_almost_constant(tx_pivot_df=tx_pivot_df.loc[:, freq_strings],
                                                                  start_time=training_start_time,
                                                                  stop_time=training_stop_time,
                                                                  noise_std_dev=noise_std_dev)
                if constant_training_set:

                    neighbor_result_df = predict_constants(tx_pivot_df=tx_pivot_df.loc[:, freq_strings],
                                                           start_time=training_start_time,
                                                           stop_time=training_stop_time,
                                                           samples_to_predict=samples_to_ignore + samples_to_predict,
                                                           delta_t_ms=np.round(time_block_size*1000))

                else:
                    LOGGER.error("singular matrix when trying to predict next values")
                    LOGGER.debug("training vals described: %s",
                                 tx_pivot_df.loc[training_start_time * 1000:training_stop_time * 1000 - 1].describe())
                    raise err

            try:
                # now ignore the specified number of samples at the start of the dataframe
                neighbor_result_df.drop(neighbor_result_df.index[:samples_to_ignore], inplace=True)

                # and drop any data occurring after the end of the scenario
                neighbor_result_df.drop(neighbor_result_df.index[neighbor_result_df.index>=scenario_len_s*1000], inplace=True)

                #LOGGER.debug("neighbor result cols %s", neighbor_result_df.columns.values)
                result_df.loc[neighbor_result_df.index, freq_strings[0]] = neighbor_result_df[freq_strings[0]]
                # display(neighbor_result_df[freq_strings[0]])

            except KeyError as err:
                LOGGER.error("key error: neighbor result index %s, freq string was %s, main index was %s",
                             neighbor_result_df.index, freq_strings[0],
                             result_df.index[int((training_start_time-5)/0.2):int((training_stop_time+5)/0.2)])
                LOGGER.debug("start time: %f training stop time: %f freq strings: %s",
                             training_start_time, training_stop_time, freq_strings)
                LOGGER.debug("first el main index: %s, last el main index: %s, main index len: %i,",
                             result_df.index[0], result_df.index[-1], len(result_df.index))

                raise err

    # switch times back to seconds
    result_df["start_time"] = result_df.index / 1000.0

    # "unpivot" back to our original format
    result_df = result_df.melt(id_vars="start_time", var_name="start_freq", value_name='duty_cycle')

    # clip duty cycles to be between 0 and 1.0
    result_df.loc[result_df["duty_cycle"] < 0, "duty_cycle"] = 0.0
    result_df.loc[result_df["duty_cycle"] > 1, "duty_cycle"] = 1.0

    result_df["start_freq"] = result_df["start_freq"].apply(float)

    # convert back to a geodataframe
    result_gdf = result_df.set_geometry(np.vectorize(box)(result_df["start_time"],
                                                          result_df["start_freq"],
                                                          result_df["start_time"] + time_block_size,
                                                          result_df["start_freq"] + freq_block_size))

    return result_gdf


def quantize_predictions(prediction_gdf: gpd.GeoDataFrame, quantization_intervals: list):
    """
    Quantize the duty cycles in the provided prediction_gdf and return the updated GeoDataFrame

    Examples:
    quantization_intervals = [0.0, 0.5, 1.0]
    For 0.0 <= x < 0.5, duty cycle rounds down to 0.0
    For 0.5 <= x, duty cycle rounds down to 0.5
    For x == 1.0, duty cycle is 1.0

    quantization_intervals = [0.0, 0.3, 0.7, 1.0]
    For 0.0 <= x < 0.3, duty cycle rounds down to 0.0
    For 0.3 <= x < 0.7, duty cycle rounds down to 0.3
    For 0.7 <= x < 1.0, duty cycle rounds down to 0.7
    For x == 1.0, duty cycle is 1.0

    :param prediction_gdf:
    :param quantization_intervals:
    :return:
    """

    upper_bin_inds = np.digitize(prediction_gdf["duty_cycle"], bins=quantization_intervals)
    quantized = [quantization_intervals[i-1] for i in upper_bin_inds]
    prediction_gdf["duty_cycle"] = quantized

    return prediction_gdf


def predict(tx_gdf: gpd.GeoDataFrame, start_time: float, time_block_size: float, num_time_blocks: int,
            start_freq: float, freq_block_size: float, num_freq_blocks: int,
            training_len_s: float, scenario_len_s: float,
            prediction_len_s: float,  prediction_latency_s: float, lags: int, noise_std_dev: float,
            quantization_intervals: list) -> gpd.GeoDataFrame:
    """

    :param tx_gdf:
    :param start_time:
    :param time_block_size: size of each grid in the time dimension, in seconds
    :param num_time_blocks:
    :param start_freq:
    :param freq_block_size: size of each grid in the frequency dimension, in hz
    :param num_freq_blocks:
    :param training_len_s:
    :param scenario_len_s:
    :param prediction_len_s: prediction_len_s/time_block_size should be integer
    :param prediction_latency_s: prediction_latency_s/time_block_size should be integer
    :param lags: how many lags to use in prediction
    :param noise_std_dev: std deviation of noise to be added to transmit detections to help
           prevent singular matrices when trying to predict future samples
    :param quantization_intervals: boundaries to use when quantizing duty cycle predictions
    :return:
    """

    # form a coarse grid for doing predictions
    LOGGER.debug("quantizing transmissions")
    tx_grid_gdf = map_tx_detections_to_grid(tx_gdf=tx_gdf,
                                            start_time=start_time,
                                            time_block_size=time_block_size,
                                            num_time_blocks=num_time_blocks,
                                            start_freq=start_freq,
                                            freq_block_size=freq_block_size,
                                            num_freq_blocks=num_freq_blocks)

    # pivot into a format that our predictor can handle
    tx_pivot_df = pivot_grid(in_gdf=tx_grid_gdf, noise_std_dev=noise_std_dev)

    # run prediction algorithm
    prediction_gdf = predict_all_voxels3(tx_pivot_df=tx_pivot_df,
                                         training_len_s=training_len_s,
                                         scenario_len_s=scenario_len_s,
                                         time_block_size=time_block_size,
                                         freq_block_size=freq_block_size,
                                         samples_to_predict=int(prediction_len_s/time_block_size),
                                         samples_to_ignore=int(prediction_latency_s/time_block_size),
                                         lags=lags,
                                         noise_std_dev=noise_std_dev)

    if quantization_intervals is not None:
        prediction_gdf = quantize_predictions(prediction_gdf=prediction_gdf,
                                              quantization_intervals=quantization_intervals)

        # if quantizing duty cycle, only remove voxels with duty cycle exactly zero
        trim_threshold = 0.0

    else:
        # otherwise remove voxels with duty cycle pretty close to zero
        trim_threshold = 0.000001

    # trim voxels with near zero duty cycle
    prediction_gdf = prediction_gdf.loc[prediction_gdf["duty_cycle"] > trim_threshold]

    # store 'report_on'
    # Store the area of each voxel that was reported 'on'
    prediction_gdf["report_on"] = prediction_gdf.geometry.area * prediction_gdf["duty_cycle"]

    return prediction_gdf
