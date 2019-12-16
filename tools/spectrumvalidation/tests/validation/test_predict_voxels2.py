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

import pytest

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box


from validation.predict import predict_voxels2


class TestPredictVoxels2(object):
    def test_ramp_prediction_no_lag_1_s(self):
        """
        Confirm baseline alg operation with a trivially estimable sequence
        :return:
        """

        time_step_s = 0.2

        # ramp from 0.0 to 0.49 over 50 steps
        source_duty_cycles = [0.0, ]*50
        source_duty_cycles[0:3] = [.001, ]*3
        # build up a sequence that a VAR with 3 lags should be REALLY good at estimating
        for i in range(3, 50):
            source_duty_cycles[i] = sum(source_duty_cycles[i-3:i])/2.0

        # build up the source dataframe, set timestamps as the index, and drop the index name
        source_timestamps_ms = np.array(range(50), dtype=np.float)*time_step_s*1000
        source_timestamps_ms = source_timestamps_ms.astype(np.int64)
        source_df = pd.DataFrame({"10": source_duty_cycles,
                                  "timestamp": source_timestamps_ms})

        source_df = source_df.set_index("timestamp", drop=True,)
        del source_df.index.name

        start_time = 0.0
        stop_time = 5.0
        samples_to_predict = 5
        lags = 3

        result_df = predict_voxels2(tx_pivot_df=source_df,
                                    start_time=start_time,
                                    stop_time=stop_time,
                                    samples_to_predict=samples_to_predict,
                                    lags=lags)

        # pandas convention includes the endpoint. Subtract off a millisecond to avoid this
        expected_df = source_df.loc[stop_time*1000:(stop_time+1.0)*1000-1]

        # pytest doesn't do well with dataframes. Use pandas native check
        pd.testing.assert_frame_equal(expected_df, result_df)

    def test_ramp_prediction_no_lag_5_s(self):
        """
        Confirm baseline alg operation doesn't blow up with a longer estimate
        :return:
        """

        time_step_s = 0.2

        # ramp from 0.0 to 0.49 over 50 steps
        source_duty_cycles = [0.0, ] * 50
        source_duty_cycles[0:3] = [.001, ] * 3
        # build up a sequence that a VAR with 3 lags should be REALLY good at estimating
        for i in range(3, 50):
            source_duty_cycles[i] = sum(source_duty_cycles[i - 3:i]) / 2.0

        # build up the source dataframe, set timestamps as the index, and drop the index name
        source_timestamps_ms = np.array(range(50), dtype=np.float) * time_step_s * 1000
        source_timestamps_ms = source_timestamps_ms.astype(np.int64)
        source_df = pd.DataFrame({
                                     "10": source_duty_cycles,
                                     "timestamp": source_timestamps_ms})

        source_df = source_df.set_index("timestamp", drop=True, )
        del source_df.index.name

        start_time = 0.0
        stop_time = 5.0
        samples_to_predict = 25
        lags = 3

        result_df = predict_voxels2(tx_pivot_df=source_df,
                                    start_time=start_time,
                                    stop_time=stop_time,
                                    samples_to_predict=samples_to_predict,
                                    lags=lags)

        # pandas convention includes the endpoint. Subtract off a millisecond to avoid this
        expected_df = source_df.loc[stop_time * 1000:(stop_time + 5.0) * 1000 - 1]

        # pytest doesn't do well with dataframes. Use pandas native check
        pd.testing.assert_frame_equal(expected_df, result_df)