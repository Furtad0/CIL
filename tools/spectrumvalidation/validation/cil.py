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
import os
import re

import geopandas as gpd
from google.protobuf.json_format import MessageToDict
import numpy as np
import pandas as pd
from shapely.geometry import box
from shapely.ops import unary_union

import ciltool
from ciltool.cil_reader import CilReader

from validation import constants

COMPETITOR_LABEL = "Team"
INCUMBENT_LABEL = "incumbent"
VALIDATION_LABEL = "v-*"

COLOSSEUM_SRN_TO_IP_OFFSET = 100

# objects must overlap by more than this area to be considered actually overlapping
INTERSECT_AREA_TOLERANCE = 0.1

CIL_COLUMN_TYPES = {"duty_cycle": np.float64,
                    "msg_timestamp": np.float64,
                    "frame_timestamp": np.float64,
                    "msg_id": np.int64,
                    "measured_data": np.bool_,
                    "src_ip": str,
                    "dst_ip": str}

LOGGER = logging.getLogger(__name__)


def parse_pcap_file_name(pcap_file_path: str):
    """

    :param pcap_file_path: Full path to the PCAP file. The expected format of the file name is:
      <event>-<Entity label>-srn<SRN number>-RES<reservation number>-colbr<CIL server SRN number>-YYYYMMDD-hhmmss.pcap

     scrimmage9 - Team01 - srn104 - RES99999 - colbr104 - 20201101-999999.pcap

      Note that event labels must not include the "-" character

    :return: dict containing full path and parsed components
    """

    # store full path and parsed file name components here
    parsed = {"full_path": pcap_file_path}

    # remove any path information to get just the file name

    pcap_file_name = os.path.basename(pcap_file_path)
    pcap_file_name, pcap_extension = os.path.splitext(pcap_file_name)
    file_name_split = pcap_file_name.split("-")

    parsed["event_name"] = file_name_split[0]

    # consume event name from the split string to reduce bookkeeping logic
    # This is not fast but we won't have to do this many times
    file_name_split = file_name_split[1:]

    # since we allow "-" characters in the entity label (Team vs incumbent) we have to find the
    # SRN substring before we can actually parse the entity label
    srn_pos = -1
    for i, chunk in enumerate(file_name_split):
        if re.match('srn', chunk):
            srn_pos = i

    # The SRN number field must come after the entity label. If it is the first element in what is left of
    #  the split file name, throw an error. Otherwise, process.
    if srn_pos > 0:
        parsed["entity_label"] = "-".join(file_name_split[:srn_pos])
    else:
        raise ValueError("SRN substring not found at valid location in filename")

    # mark the type of PCAP file this is: observer, incumbent, competitor
    # Test if this belongs to a competitor
    if re.match(COMPETITOR_LABEL, parsed["entity_label"]):
        parsed["pcap_type"] = "competitor"

    elif re.match(INCUMBENT_LABEL, parsed["entity_label"]):
        parsed["pcap_type"] = "incumbent"

    elif re.match(VALIDATION_LABEL, parsed["entity_label"]):
        parsed["pcap_type"] = "validation_image"

    else:
        parsed["pcap_type"] = "competitor"
        LOGGER.warning("pcap file entity label not recognized, defaulting to competitor")

    # consume up to the SRN position
    file_name_split = file_name_split[srn_pos:]

    # parse the rest of the filename (SRN number, reservation ID, collaboration server number, date and time)
    # get the srn number (already confirmed "srn" substring exists at the start of this chunk)
    parsed["srn_number"] = int(file_name_split[0][3:])

    if re.match('RES', file_name_split[1]):
        parsed["reservation_id"] = file_name_split[1][3:]
    else:
        raise ValueError("Reservation ID substring not found in filename")

    if re.match('colbr', file_name_split[2]):
        parsed["collab_srn_number"] = int(file_name_split[2][5:])
    else:
        raise ValueError("Reservation ID substring not found in filename")

    # retrieve date and time without parsing
    parsed["date_str"] = file_name_split[3]
    parsed["time_str"] = file_name_split[4]

    return parsed


def parse_cil_pcap(filename, collab_server_srn_num=None, collab_gateway_srn_num=None):

    # if either the collaboration server srn number or collaboration gateway srn number wasn't provided for
    # this PCAP file, try to extract both from the PCAP filename, assuming a scrimmage validation naming convention
    if collab_server_srn_num is None or collab_gateway_srn_num is None:
        # extract details from the pcap filename
        file_info = parse_pcap_file_name(filename)
        collab_octet = str(file_info["collab_srn_number"] + COLOSSEUM_SRN_TO_IP_OFFSET)
        srn_octect = str(file_info["srn_number"] + COLOSSEUM_SRN_TO_IP_OFFSET)
    else:
        collab_octet = str(collab_server_srn_num + COLOSSEUM_SRN_TO_IP_OFFSET)
        srn_octect = str(collab_gateway_srn_num + COLOSSEUM_SRN_TO_IP_OFFSET)

    cil_messages = []
    # add an artificial message ID to uniquely reference each message in this file
    msg_id = 0
    with CilReader(filename, read_reg=False) as reader:
        while True:
            message = reader.read()

            if message is None:
                break

            # split up src ip into octets
            src_split = message["src_ip"].split(".")

            # filter out registration messages
            if message["dst_port"] == CilReader.CLIENT_PORT or message["dst_port"] == CilReader.SERVER_PORT:
                pass

            # select only messages sent by the source IP of interest
            elif src_split[2] == collab_octet and src_split[3] == srn_octect:
                # add in the message id
                message["msg_id"] = msg_id
                cil_messages.append(message)
                msg_id = msg_id + 1

    LOGGER.debug("parsed %i total CIL messages", len(cil_messages))
    return cil_messages


def filter_spectrum_usage_messages(cil_messages):
    # filter down to just spectrum usage messages
    msgs = [msg for msg in cil_messages if msg["cil_message"].WhichOneof("payload") == "spectrum_usage"]

    LOGGER.debug("found %i total CIL spectrum_usage messages", len(msgs))
    return msgs


def messages_to_geodataframe(spectrum_messages, match_start_time, scenario_len,
                             scenario_fc, scenario_bw):
    default_min_freq = scenario_fc - scenario_bw / 2
    default_max_freq = scenario_fc + scenario_bw / 2
    default_min_time = match_start_time
    default_max_time = match_start_time + scenario_len

    v_dicts = []
    if len(spectrum_messages) > 0:
        # loop over all messages, and generate an artificial message ID to keep
        # track of the source message of any repeated elements
        for msg in spectrum_messages:
            for v in msg['cil_message'].spectrum_usage.voxels:

                try:
                    v_dict = MessageToDict(v.spectrum_voxel,
                                           preserving_proto_field_name=True)

                    # print(v_dict)

                    msg_timestamp = MessageToDict(msg['cil_message'].timestamp,
                                                  preserving_proto_field_name=True)

                    v_norm = normalize_voxel(v_dict=v_dict,
                                             match_start_time=match_start_time,
                                             msg_timestamp=msg_timestamp,
                                             frame_timestamp=msg['timestamp'],
                                             msg_id=msg["msg_id"],
                                             src_ip=msg["src_ip"],
                                             dst_ip=msg["dst_ip"],
                                             measured_data=v.measured_data,
                                             default_min_freq=default_min_freq,
                                             default_max_freq=default_max_freq,
                                             default_min_time=default_min_time,
                                             default_max_time=default_max_time)

                    v_dicts.append(v_norm)

                # ignore cases where the voxel doesn't have a spectrum_voxel field
                except AttributeError as err:
                    pass
        cil_df = pd.DataFrame(v_dicts)

    else:
        # handle special case of no messages found
        LOGGER.warning("No spectrum usage messages found, initializing empty dataframe")
        cil_df = pd.DataFrame(columns=list(CIL_COLUMN_TYPES.keys()))
        cil_df["voxel"] = None

    cil_df = cil_df.astype(dtype=CIL_COLUMN_TYPES, copy=True)
    cil_gdf = gpd.GeoDataFrame(cil_df, geometry=cil_df["voxel"])
    cil_gdf.drop(columns=["voxel"], inplace=True)

    # Store the area of each voxel that was reported 'on'
    cil_gdf["report_on"] = cil_gdf.geometry.area * cil_gdf["duty_cycle"]

    return cil_gdf


def normalize_voxel(v_dict, match_start_time, msg_timestamp, frame_timestamp, measured_data,
                    msg_id, src_ip, dst_ip,
                    default_min_freq, default_max_freq, default_min_time, default_max_time):
    """
    Get all voxels in a consistent format to simplify downstream processing.
    All timestamps are converted to float times relative to the start of the match
    """
    v_norm = {
        "msg_id": msg_id,
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "measured_data": measured_data}

    # get start time and end time dicts from voxel, with defaults in case they aren't there
    time_start = v_dict.get("time_start", {"seconds": default_min_time, "picoseconds": 0})
    time_end = v_dict.get("time_end", {"seconds": default_max_time, "picoseconds": 0})

    # get voxel times into a single float
    time_start = (time_start.get("seconds", default_min_time) - match_start_time +
                  float(time_start.get("picoseconds", 0)) / 1e12)

    time_end = (time_end.get("seconds", default_max_time) - match_start_time +
                float(time_end.get("picoseconds", 0)) / 1e12)

    # also trim time start and time end to be within the min and max times specified
    time_start = max(time_start, default_min_time - match_start_time)
    time_start = min(time_start, default_max_time - match_start_time)
    time_end = min(time_end, default_max_time - match_start_time)
    time_end = max(time_end, default_min_time - match_start_time)

    # get start and stop freqs from voxel with defaults, just in case
    freq_start = v_dict.get("freq_start", default_min_freq)
    freq_end = v_dict.get("freq_end", default_max_freq)
    v_norm["voxel"] = box(minx=time_start, miny=freq_start, maxx=time_end, maxy=freq_end)

    # add frame and message timestamps
    v_norm["frame_timestamp"] = frame_timestamp - match_start_time
    v_norm["msg_timestamp"] = (msg_timestamp.get("seconds", default_min_time) - match_start_time +
                               float(msg_timestamp.get("picoseconds", 0)) / 1e12)

    # get optional parameters. We may not use all of these
    v_norm["duty_cycle"] = v_dict.get("duty_cycle", 1.0)
    #    v_norm["period_time"] = v_dict.get("period_time", np.nan) #ignoring period and slot time for now
    #    v_norm["slot_time"] = v_dict.get("slot_time", np.nan)

    return v_norm


def read_spectrum_messages(pcap_filename: str, match_start_time: float, scenario_len: float, scenario_bw: float,
                           collab_server_srn_num: int = None, collab_gateway_srn_num: int = None):

    # read in cil messages sent by the team under test
    cil_messages = parse_cil_pcap(filename=pcap_filename,
                                  collab_server_srn_num=collab_server_srn_num,
                                  collab_gateway_srn_num=collab_gateway_srn_num)

    # filter down to just spectrum usage messages
    spectrum_messages = filter_spectrum_usage_messages(cil_messages)

    # convert messages into a geodataframe structure
    cil_gdf = messages_to_geodataframe(spectrum_messages=spectrum_messages,
                                       match_start_time=match_start_time,
                                       scenario_len=scenario_len,
                                       scenario_fc=constants.SCENARIO_FC,
                                       scenario_bw=scenario_bw)

    return cil_gdf


def find_prediction_messages(gdf):

    if len(gdf.index) > 0:

        # filter out any message that says it is based on measured data
        not_measured_inds = gdf["measured_data"] != True

        extends_to_future_inds = gdf.geometry.bounds.maxx > gdf["frame_timestamp"]
        return gdf.loc[not_measured_inds & extends_to_future_inds]

    else:
        # input geodataframe is empty: Just return empty
        return gdf


def find_historical_report_messages(gdf):

    if len(gdf.index) > 0:

        # filter out any message that says it is not based on measured data
        measured_inds = gdf["measured_data"] != False

        # filter for any message that includes historical data
        extends_to_past_inds = gdf.geometry.bounds.minx < gdf["frame_timestamp"]

        return gdf.loc[measured_inds & extends_to_past_inds]

    else:
        # input geodataframe is empty: Just return empty
        return gdf


def trim_voxels_to_bounds(row):
    """
    Given a pandas row containing the following columns: "voxels", "min_time",
    "max_time", trim the polygon in "voxels" to be between min time and max time
    """

    # set arbitrarily wide frequency limits, we're only concerned about valid
    # time spans here
    valid_mask = box(row["min_time"], 0, row["max_time"], 1e12)

    return valid_mask.intersection(row["geometry"])


def get_min_time_bound(voxels):
    # voxel.bounds returns (minx, miny, maxx, maxy) tuple. X axis is time.
    # extract the min time bound value for each voxel, store in list,
    # then return the min value of that list

    return min([v.bounds[0] for v in voxels])


def filter_zeroed_voxels(gdf):
    nonzero_duty_cycle_inds = gdf["duty_cycle"] != 0.0

    nonzero_area_inds = gdf.geometry.area > 0

    return gdf.loc[nonzero_duty_cycle_inds & nonzero_area_inds]


def extract_valid_voxels(gdf: gpd.GeoDataFrame):
    """
    Given a GeoDataFrame gdf containing data from one source team,
    with columns "dst_ip", "geometry",
    process the Shapely objects contained in
    "geometry" and store only the voxels that have not been invalidated
    over their relevant time frames.

    For example, if at time zero, one voxel declares it occupies 100 to 110 Hz and
    time zero to time 10 seconds, and then at time 5 a voxel sent by the same source
    team to the same destination team then declares it occupies 110 Hz to 120 Hz
    and time 5 seconds to time 15 seconds, we would expect to see a resulting
    set of voxels where the first occupies 100 to 110 Hz from time zero to time
    5 seconds and the second occupies 110 Hz to 120 Hz and time 5 to 15 seconds.

    The second voxel will trim off the overlapping portion of the first voxel.

    :param gdf: GeoDataFrame as described above
    :return: A GeoDataFrame with geometry updated to trimmed values
    """

    gdf_out = gdf.copy()

    groups = gdf_out.groupby("dst_ip")
    for dst_ip, group_gdf in groups:

        # get the minimum time associated with each declaration
        # group by the message count. Store the smallest time instance referenced by any voxel in the group to
        # min_time, and store off the smallest frame_timestamp in the group to frame_timestamp
        valid_time_bounds = group_gdf.groupby("msg_id").agg({"geometry": get_min_time_bound,
                                                             "frame_timestamp": "min"})

        valid_time_bounds = valid_time_bounds.rename(columns={'geometry': 'min_time'})

        # Store the max of either the min_time column or the frame_timestamp column back to the min_time column
        valid_time_bounds["min_time"] = valid_time_bounds[["min_time", "frame_timestamp"]].max(axis=1)

        # now store off the timestamp associated with the "next" message to the same destination as the "max"
        # time of the previous message
        valid_time_bounds["max_time"] = np.nan
        valid_time_bounds.iloc[0:-1, valid_time_bounds.columns.get_loc('max_time')] = valid_time_bounds.iloc[1:, ][
            "frame_timestamp"].values
        valid_time_bounds.iloc[-1, valid_time_bounds.columns.get_loc('max_time')] = 10e12

        # drop the frame_timestamp column
        valid_time_bounds.drop(columns=["frame_timestamp"], inplace=True)

        # add the min and max times into the dataframe
        merged = pd.merge(group_gdf, valid_time_bounds, on="msg_id")

        # trim the voxels and store back to the main array
        gdf_out.loc[group_gdf.index, "geometry"] = merged.apply(trim_voxels_to_bounds, axis=1).values

    # Store the updated area of each voxel that was reported 'on'
    gdf_out["report_on"] = gdf_out.geometry.area * gdf_out["duty_cycle"]

    return gdf_out


def merge_overlaps(gdf: gpd.GeoDataFrame):
    """
    Given a GeoDataFrame gdf containing data from one source team,
    with columns "dst_ip", "geometry",
    process the Shapely objects contained in
    "geometry" and combine overlapping voxels into a single voxel,
    with the other parameters for that voxel combined in some meaningful
    way.

    :param gdf: GeoDataFrame as described above
    :return: A GeoDataFrame with geometry updated to trimmed values
    """

    gdf_out = gdf.copy()
    # add a flag to indicate whether a voxel has already been processed
    gdf_out["processed"] = "unprocessed"
    
    # add a field for the index of the "kept" voxel corresponding to each
    # discarded voxel
    gdf_out["voxel_index"] = gdf_out.index

    groups = gdf_out.groupby("dst_ip")
    for dst_ip, group_gdf in groups:

        # make a spatial index to speed up intersection search
        spatial_index = group_gdf.sindex

        # loop over voxels and search for all intersections
        for current_idx in group_gdf.index:
            current_row = gdf_out.loc[current_idx]

            if current_row["processed"] == "unprocessed":
                possible_matches_index = list(spatial_index.intersection(current_row.geometry.bounds))
                possible_matches = group_gdf.iloc[possible_matches_index]

                # get the possible matches from the original data structure using the group's index
                if len(possible_matches.index > 0):
                    possible_matches = gdf_out.loc[possible_matches.index]

                # find the index of each merged voxel for any discarded voxels
                possible_matches = gdf_out.loc[possible_matches["voxel_index"].unique()]

                # computing the area of intersection, as the intersects function includes those polygons that share
                # a boundary but doesn't overlap in the traditional sense.
                # Using a tolerance value instead of just comparing against zero to guard against potential
                # numeric precision issues
                precise_matches = possible_matches[
                    possible_matches.intersection(current_row.geometry).area > INTERSECT_AREA_TOLERANCE]

                # now compute what the aggregate voxel shape and duty cycle should be
                union_voxel = unary_union(precise_matches.geometry)

                # set the 'processed' flag on all the intersected rows
                gdf_out.loc[precise_matches.index, "processed"] = "discard"
                # but keep the current row
                gdf_out.loc[current_idx, "processed"] = "keep"
                
                # store the index of the kept voxel for each discarded voxel
                gdf_out.loc[precise_matches.index, "voxel_index"] = current_idx

                # also store the new index for all the components of each discarded voxel
                gdf_out.loc[gdf_out["voxel_index"].isin(precise_matches.index), "voxel_index"] = current_idx

                # store the union geometry and total reported area 'on'
                gdf_out.loc[current_idx, "geometry"] = union_voxel
                gdf_out.loc[current_idx, "report_on"] = sum(precise_matches["report_on"])

    # only keep the voxels with a "keep" flag
    gdf_out = gdf_out.loc[gdf_out["processed"] == "keep"]
    # drop the 'processed' column as we don't need it anymore, drop the 'duty_cycle' column,
    # as it is no longer meaningful for our set of metrics, also drop the added temporary 
    # 'voxel_index' field
    gdf_out = gdf_out.drop(columns=["processed", "duty_cycle", "voxel_index"])
    return gdf_out


def extract_prediction_messages(cil_gdf, scenario_len):
    """
    Find the spectrum usage messages that reference the future and clean them up
    for downstream processing
    :param cil_gdf:
    :return:
    """

    LOGGER.debug("finding prediction messages out of %i total messages", len(cil_gdf.index))
    future_cil_gdf = find_prediction_messages(cil_gdf)

    # trim to only messages after match start
    LOGGER.debug("trimming messages in the past out of %i total messages", len(future_cil_gdf.index))
    future_cil_gdf = future_cil_gdf.loc[future_cil_gdf["frame_timestamp"] > 0]

    # trim to only messages before match end
    LOGGER.debug("trimming messages after end of the match out of %i total messages", len(future_cil_gdf.index))
    future_cil_gdf = future_cil_gdf.loc[future_cil_gdf["frame_timestamp"] < scenario_len]

    # handle prediction updates
    LOGGER.debug("extracting valid voxels")
    future_cil_gdf = extract_valid_voxels(future_cil_gdf)

    # remove any voxels with zero area or duty cycle
    LOGGER.debug("removing zeroed voxels")
    future_cil_gdf = filter_zeroed_voxels(future_cil_gdf)

    # merge any overlapping voxels
    LOGGER.debug("merging any voxel overlaps")
    future_cil_gdf = merge_overlaps(future_cil_gdf)

    return future_cil_gdf


def extract_historical_messages(cil_gdf, scenario_len):
    """
    Find the spectrum usage messages that reference the future and clean them up
    for downstream processing
    :param cil_gdf:
    :return:
    """

    LOGGER.debug("finding historical messages out of %i total messages", len(cil_gdf.index))
    past_cil_gdf = find_historical_report_messages(cil_gdf)

    # trim to only messages after match start
    LOGGER.debug("trimming messages from before the start of the match out of %i total messages",
                 len(past_cil_gdf.index))
    past_cil_gdf = past_cil_gdf.loc[past_cil_gdf["frame_timestamp"] > 0]

    # trim to only messages before match end
    LOGGER.debug("trimming messages after end of the match out of %i total messages", len(past_cil_gdf.index))
    past_cil_gdf = past_cil_gdf.loc[past_cil_gdf["frame_timestamp"] < scenario_len]

    # remove any voxels with zero area or duty cycle
    LOGGER.debug("removing zeroed voxels")
    past_cil_gdf = filter_zeroed_voxels(past_cil_gdf)

    # merge any overlapping voxels
    LOGGER.debug("merging any voxel overlaps")
    past_cil_gdf = merge_overlaps(past_cil_gdf)

    return past_cil_gdf
