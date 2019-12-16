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

"""
Collection of useful functions, like data type conversions
"""

import geopandas as gpd
import more_itertools as mit
import numpy as np
from scipy.ndimage import label
from scipy.ndimage import find_objects
from shapely.geometry import box
from shapely.geometry import Polygon
import shapely.geometry
from shapely.ops import unary_union
import xarray as xr
import pandas as pd


import validation.constants as constants


def scenario_bw_to_file_bw(scenario_bw):
    bw_ratio = constants.FILE_FS / scenario_bw

    floor_pow_2 = np.floor(np.log2(bw_ratio))

    return constants.FILE_FS / (2 ** floor_pow_2)


def array_to_xarray(data: np.ndarray, t0: float, bw: float, delta_t: float,
                    nfft: int, rf_threshold_tolerance: float, fc: float = constants.SCENARIO_FC):
    """
    Convert a plain numpy array to an xarray, which includes coordinate labels
    Times are the start of the pixel, frequencies are bin centers
    """
    num_times = data.shape[1]

    timestamps = np.arange(num_times)*delta_t + t0
    frequencies = (bw / nfft * np.arange(-float(nfft) / 2.0, float(nfft) / 2.0, 1)) + fc
    threshold_vals = [-rf_threshold_tolerance, 0.0, rf_threshold_tolerance]
    data2 = xr.DataArray(data=data, coords=[('thresh', threshold_vals), ('time', timestamps), ('freq', frequencies)])

    return data2


def xarray_to_geodataframe(data: xr.DataArray, delta_f: float, delta_t: float) -> gpd.GeoDataFrame:
    """
    Convert an xarray, which includes time and frequency coordinates, to a
    geodataframe, which is like a pandas dataframe but includes a geometry column
    :param data:
    :param delta_f:
    :param delta_t:
    :return:
    """

    # get times in terms of offset to the start of the match
    # times in the array are assumed to start at the beginning of the measurement period
    times_lower = np.around(data.time.data, 9)
    times_upper = np.around(times_lower + delta_t, 9)

    # frequencies in the array are assumed to be the center of the frequency bin,
    # so subtract half of the frequency resolution to get to the edge
    freqs_lower = np.around(data.freq.data - delta_f/2.0, 9)
    freqs_upper = np.around(freqs_lower + delta_f, 9)
    #
    # # find indexes to all detected transmissions
    # (time_inds, freq_inds) = np.nonzero(data.data)

    # TODO: look at doing transmission aggregation iteratively with intersection tests
    # and resetting geometry on the intersected rows

    boxes = []

    # step through time and create boxes for any contiguous transmit regions
    for i in range(data.shape[0]):
        freq_inds = np.nonzero(data.data[i, :])[0]
        boxes.append([])
        if len(freq_inds) > 0:
            for group_map in mit.consecutive_groups(freq_inds):
                group = list(group_map)
                miny = freqs_lower[group[0]]
                maxy = freqs_upper[group[-1]]
                new_box = box(minx=times_lower[i], maxx=times_upper[i], miny=miny, maxy=maxy)

                # search if the new box intersects with any existing boxes
                if len(boxes) > 1:
                    hit_inds = np.nonzero(np.array([new_box.intersects(b) for b in boxes[-2]]))[0]

                    if hit_inds.size > 1:
                        reversed_hit_inds = hit_inds[::-1]
                        for ind in reversed_hit_inds[:-1]:
                            # take union of all matching elements from the previous row and remove the
                            # now duplicate entries
                            first_box = boxes[-2][hit_inds[0]]
                            old_box = boxes[-2][ind]
                            boxes[-2][hit_inds[0]] = unary_union([old_box, first_box])
                            del boxes[-2][ind]
                        # add in the union of the new box
                        boxes[-2][hit_inds[0]] = unary_union([boxes[-2][hit_inds[0]], new_box])
                    elif hit_inds.size == 1:
                        # add in the union of the new box
                        boxes[-2][hit_inds[0]] = unary_union([boxes[-2][hit_inds[0]], new_box])
                    # no matches
                    else:
                        boxes[-1].append(new_box)
                else:
                    boxes[-1].append(new_box)

        # if there weren't any boxes added, remove the empty list
        if len(boxes[-1]) == 0:
            del boxes[-1]

    # flatten list
    boxes = [item for sublist in boxes for item in sublist]

    # store in geodataframe
    gdf = gpd.GeoDataFrame(geometry=boxes)
    return gdf


def merge_to_grid(in_gdf: gpd.GeoDataFrame,
                  start_time: float, stop_time: float, num_time_blocks: int,
                  start_freq: float, stop_freq: float, num_freq_blocks: int) -> gpd.GeoDataFrame:
    """

    :param in_gdf:
    :param start_time:
    :param stop_time:
    :param num_time_blocks:
    :param start_freq:
    :param stop_freq:
    :param num_freq_blocks:
    :return:
    """

    grid_delta_t = (stop_time-start_time)/float(num_time_blocks)
    grid_delta_f = (stop_freq-start_freq)/float(num_freq_blocks)

    # get area of one grid box
    grid_area = grid_delta_t*grid_delta_f

    # build coordinate arrays to use for the grid
    grid_times_lower = grid_delta_t*np.arange(num_time_blocks) + start_time
    grid_freqs_lower = grid_delta_f*np.arange(num_freq_blocks) + start_freq

    # build the grid as a geodataframe
    grid_geometry = []
    for i in range(num_time_blocks):
        for j in range(num_freq_blocks):
            b = box(minx=grid_times_lower[i], miny=grid_freqs_lower[j],
                    maxx=grid_times_lower[i]+grid_delta_t, maxy=grid_freqs_lower[j]+grid_delta_f)

            grid_geometry.append(b)

    grid_gdf = gpd.GeoDataFrame(geometry=grid_geometry)

    # label each grid square with a grid id
    gid = np.arange(len(grid_geometry))
    grid_gdf["gid"] = gid

    # common case
    if len(in_gdf.index) > 0:

        # overlay the grid over the input geodataframe to split geometries by the grid
        split_gdf = gpd.overlay(grid_gdf, in_gdf, how="intersection")

        # # now join on the grid to add the grid ID to the split gdf
        # split_gdf = gpd.sjoin(grid_gdf, split_gdf, op="contains", how="right")

        # store off the areas
        split_gdf["area"] = split_gdf.geometry.area

        # sum the areas of all the geometries in split_gdf by grid ID
        split_areas_df = split_gdf.groupby("gid").agg({"area": "sum"})

        # compute the duty cycle of each grid id
        split_areas_df["duty_cycle"] = split_areas_df["area"] / grid_area

        # store duty cycles from split_areas
        grid_gdf = pd.merge(grid_gdf, split_areas_df, how="left", left_on="gid", right_index=True)

        grid_gdf = gpd.GeoDataFrame(grid_gdf, geometry="geometry")

    # handle corner case of an empty input geodataframe
    else:
        # if there were no transmissions at all, everything has zero duty cycle
        grid_gdf["duty_cycle"] = 0.0

    return grid_gdf

