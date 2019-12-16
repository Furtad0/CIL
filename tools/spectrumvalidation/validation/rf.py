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
import numpy as np
import validation.constants as constants

LOGGER = logging.getLogger(__name__)


def read_rf_file(filename: str):
    """
    Read in all data from the binary formatted observer file
    :param filename:
    :return:
    """
    header_dt = np.dtype([('nfft', np.uint32), ('frame_period', np.float64),
                          ('t0_int_s', np.uint64), ('t0_frac_s', np.float64)])

    with open(filename, "rb") as f:
        header = np.fromfile(f, dtype=header_dt, count=1)

        row_dt = np.dtype([("sync", np.uint32), ("frame_num", np.uint32),
                           ("fft_bins", np.float32, (1, header[0]["nfft"]))])

        rows = np.fromfile(f, dtype=row_dt)

    return header[0], rows


def combine_files(files: list):
    """
    Loop over RF files, read in each file and combine

    :param files: list of file paths
    :return:
    """

    headers = []
    rf_data = None
    fs = constants.FILE_FS

    # read all the RF files
    for filename in files:
        print("processing {}".format(filename))
        header, rows = read_rf_file(filename)
        headers.append(header)
        new_rf_data = np.squeeze(rows["fft_bins"])

        if rf_data is None:
            rf_data = new_rf_data
        else:
            rf_data = np.maximum(rf_data, new_rf_data)

    return headers, rf_data


def adjust_threshold(file_bw, buffer_db, threshold_base):
    """
    Adjust the threshold value to handle the fact that the fft bins cover different
    amounts of bandwidth from scenario to scenario

    :param file_bw: bandwidth covered by the file in Hz
    :param buffer_db: how much above the OOB detection floor to declare a signal as
    an intentional transmission
    : param threshold_base: what to use as the baseline threshold before adjusting for
    bin widths

    :return:
    """
    rf_decimation = int(constants.FILE_FS / file_bw)
    fft_bin_decimation = constants.OBS_INPUT_NFFT / rf_decimation / constants.OBS_OUTPUT_NFFT

    threshold_scale_factor = constants.OBS_INPUT_NFFT / constants.OBS_OOB_NFFT / fft_bin_decimation

    threshold = (threshold_base + 10 * np.log10(constants.FILE_FS)
                 - 20*np.log10(threshold_scale_factor) + buffer_db)

    return threshold


def threshold_and_combine_files(files: list, rf_threshold: float, rf_threshold_tolerance: float):
    """
    Loop over RF files, read in each file, threshold each file, and combine results

    :param files: list of file paths
    :param rf_threshold: level at which to declare a detection
    :param rf_threshold_tolerance: Controls which values will be used for thresholding.
       Thresholds will be computed using rf_threshold - rf_treshold_tolerance, rf_threshold,
       and rf_threshold + rf_threshold_tolerance
    :return: 3 x num_frames x nfft array, where the first dimension corresponds to
       0: lowest threshold, 1: nominal threshold, 2: highest threshold
    """

    headers = []
    thresholded = None
    fs = constants.FILE_FS
    frame_numbers = []

    # read all the RF files
    for filename in files:
        print("processing {}".format(filename))
        header, rows = read_rf_file(filename)
        headers.append(header)

        new_thresholded = np.zeros((3, len(rows["frame_num"]), headers[0]["nfft"]), dtype=np.uint8)

        new_thresholded[0, :, :] = np.squeeze(np.where(rows["fft_bins"] >= rf_threshold-rf_threshold_tolerance, 1, 0))
        new_thresholded[1, :, :] = np.squeeze(np.where(rows["fft_bins"] >= rf_threshold, 1, 0))
        new_thresholded[2, :, :] = np.squeeze(np.where(rows["fft_bins"] >= rf_threshold+rf_threshold_tolerance, 1, 0))

        if thresholded is None:
            thresholded = new_thresholded
        else:
            thresholded = np.maximum(thresholded, new_thresholded)

        frame_numbers = rows["frame_num"]

    thresholded = thresholded.astype('uint8')

    LOGGER.info("dims: %i, %i, %i", 3, frame_numbers[-1]+1, thresholded.shape[2])

    zero_filled = np.zeros((3, frame_numbers[-1]+1, thresholded.shape[2]), dtype=np.uint8)

    for ind, frame_num in enumerate(frame_numbers):
        zero_filled[:, frame_num, :] = thresholded[:, ind, :]

    return headers, zero_filled
