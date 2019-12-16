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
from typing import List
import geopandas as gpd
import numpy as np
import pandas as pd

GdfList = List[gpd.GeoDataFrame]

LOGGER = logging.getLogger(__name__)


def score_spectrum_usage(tx_gdf_list: GdfList, report_gdf: gpd.GeoDataFrame) -> (float, float):

    # compute the total in-voxel error
    LOGGER.debug("computing score for 'in_voxel_error'")
    e_in_voxel, a_tx_inside = in_voxel_error(tx_gdf_list, report_gdf)

    # compute the total out-of-voxel error
    LOGGER.debug("computing score for 'out_of_voxel_error'")
    e_out_of_voxel = out_of_voxel_error(tx_gdf_list, report_gdf)

    return e_in_voxel, e_out_of_voxel


def in_voxel_error(tx_gdf_list: GdfList, report_in_gdf: gpd.GeoDataFrame):
    """
    Compute the total In-voxel error given the actual transmit voxels and the merged and normalized reported voxels.

    For each reported voxel, find the total area of any intersecting transmitted voxels
    :param tx_gdf_list:
    :param report_in_gdf:
    :return: normalized_in_voxel_error, a_tx_on: float, float
    """

    # loop over the reported voxels and find the total area of any intersecting transmitted voxels

    # make a copy so we don't accidentally change the source
    report_gdf = report_in_gdf.copy()

    # bulletproof all the things
    if len(report_gdf.index > 0):
        num_nonzero_reports = report_gdf[report_gdf["report_on"] > 0].count()["report_on"]
    else:
        num_nonzero_reports = 0

    if len(tx_gdf_list[0].index) > 0:
        num_nonzero_transmissions = tx_gdf_list[0][tx_gdf_list[0].geometry.area > 0].count()["geometry"]
    else:
        num_nonzero_transmissions = 0

    # handle edge case of no nonzero reports
    if num_nonzero_reports == 0:
        # this will pass here, but should get trashed by other rate reporting metrics or the out-of-voxel metric
        normalized_in_voxel_error = 0.0
        a_tx_inside = 0.0

    # handle edge case of reports, but we found no transmissions
    elif num_nonzero_transmissions == 0:
        # a divide by zero. Every report is in 100% error
        normalized_in_voxel_error = 1.0
        a_tx_inside = 0.0

    # handle common case
    else:

        # store off the index to another column so we can group intersections by
        # the reported voxel
        report_gdf["report_id"] = report_gdf.index
        # initialize in_voxel_error to inf so we can do a rolling 'min' operation later
        report_gdf["in_voxel_error"] = np.inf
        # initialize the tx_inside column to zero, so any missing voxels will not count towards errors
        report_gdf["tx_inside"] = 0.0

        intersections_gdf_list = []

        for thresh_ind in range(len(tx_gdf_list)):

            # next intersect all the reported voxels with actual transmissions and
            # compute the areas of those intersections as 'transmit on inside'.
            intersections_gdf = gpd.overlay(report_gdf, tx_gdf_list[thresh_ind], how='intersection')
            intersections_gdf["tx_inside"] = intersections_gdf.geometry.area

            # group by the reported voxel ID and drop all columns except for the 'transmit on inside' area
            intersections_gdf = intersections_gdf.groupby("report_id").agg({"tx_inside": "sum"})

            # for each reported voxel, compute the magnitude of the difference between the 'transmit on inside'
            # area
            # First get a temporary dataframe containing all the values from the tx_inside column
            tx_inside_df = pd.DataFrame(index=report_gdf.index)
            tx_inside_df["tx_inside"] = intersections_gdf["tx_inside"]
            tx_inside_df = tx_inside_df.fillna(np.inf)

            # find the indexes where the current computed error magnitude is less than what's stored in report_gdf
            current_errors_df = abs(tx_inside_df["tx_inside"] - report_gdf["report_on"])
            replace_inds = current_errors_df < report_gdf["in_voxel_error"]

            # store off the best-case errors and associated tx_inside areas
            report_gdf.loc[replace_inds, "in_voxel_error"] = current_errors_df.loc[replace_inds]
            report_gdf.loc[replace_inds, "tx_inside"] = tx_inside_df.loc[replace_inds, "tx_inside"]

        # replace inf values with zeros
        report_gdf["in_voxel_error"].replace(np.inf, 0, inplace=True)
        report_gdf["tx_inside"].replace(np.inf, 0, inplace=True)

        total_in_voxel_error = report_gdf["in_voxel_error"].sum()

        # compute the total 'transmit on inside' area and store off as an optimization
        a_tx_inside = report_gdf["tx_inside"].sum()

        # compute the error denominator term such that zero report area doesn't result in a division by zero
        error_denom = max(a_tx_inside, report_gdf["report_on"].sum())

        # normalize by the error denominator term
        normalized_in_voxel_error = total_in_voxel_error/error_denom

    return normalized_in_voxel_error, a_tx_inside


def out_of_voxel_error(tx_gdf_list: GdfList, report_in_gdf: gpd.GeoDataFrame):
    """
    Compute the total area of all transmit voxels occurring outside of a valid reported voxel

    :param tx_gdf_list:
    :param report_in_gdf:
    :return:
    """

    if len(tx_gdf_list[0].index) > 0:
        num_nonzero_transmissions = tx_gdf_list[0][tx_gdf_list[0].geometry.area > 0].count()["geometry"]
    else:
        num_nonzero_transmissions = 0

    # handle corner case of no nonzero transmissions
    if num_nonzero_transmissions == 0:
        normalized_out_of_voxel_error = 0

    # handle common case
    else:
        # compute the total transmit area
        normalized_out_of_voxel_error_list = []
        for tx_gdf in tx_gdf_list:

            a_tx_total = tx_gdf.area.sum()
            _, a_tx_inside = in_voxel_error([tx_gdf], report_in_gdf)

            # get the area transmitted outside of any voxel as the total transmitted area subtracted by the total area
            # transmitted inside valid voxels
            a_tx_outside = a_tx_total - a_tx_inside

            # compute the normalized out-of-voxel error
            normalized_out_of_voxel_error_list.append(a_tx_outside/a_tx_total)

        # return the best case. This should probably be done on a reported voxel-by voxel basis, but that is
        # going to be much more complicated to implement at this time with arguable impact on scores
        normalized_out_of_voxel_error = min(normalized_out_of_voxel_error_list)

    return normalized_out_of_voxel_error


def declare_pass_fail(result_dict):
    """

    :param result_dict:

        result_dict = {
        "team_id": args.team_id,
        "pass": None,
        "metrics": {
            "predicted_use":{
                "in_voxel_error": {
                    "competitor_value": None,
                    "threshold_value": None,
                    "pass": None
                },
                "out_of_voxel_error": {
                    "competitor_value": None,
                    "threshold_value": None,
                    "pass": None
                },
                "pass": None,
            },
            "historical_use":{
                "in_voxel_error": {
                    "competitor_value": None,
                    "threshold_value": None,
                    "pass": None
                },
                "out_of_voxel_error": {
                    "competitor_value": None,
                    "threshold_value": None,
                    "pass": None
                },
                "pass": None,
            }
        }
    }

    :return:
    """

    LOGGER.debug("summarizing score report: %s", result_dict)

    metric_passes = []
    # loop over predicted and historical uses
    for use_case, use_case_metrics in result_dict["metrics"].items():
        use_case_passes = []
        # loop over in_voxel_error and out_of_voxel_error
        for metric_name, metric_values in use_case_metrics.items():
            if metric_name != "pass":
                # pull out competitor value and threshold values
                competitor_value = result_dict["metrics"][use_case][metric_name]["competitor_value"]
                threshold_value = result_dict["metrics"][use_case][metric_name]["threshold_value"]

                # competitors must have errors less than or equal to our defined thresholds
                pass_fail = competitor_value <= threshold_value
                result_dict["metrics"][use_case][metric_name]["pass"] = bool(pass_fail)
                use_case_passes.append(pass_fail)

        # a use case passes if all constituent metrics pass
        use_case_pass = all(use_case_passes)
        result_dict["metrics"][use_case]["pass"] = bool(use_case_pass)
        metric_passes.append(use_case_pass)

    # we get an overall pass if all use cases pass
    result_dict["pass"] = bool(all(metric_passes))

    LOGGER.debug("overall competitor result was %s", result_dict["pass"])

    return result_dict
