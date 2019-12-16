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

from validation.predict import quantize_predictions


class TestQuantizePredictions(object):
    def test_three_quantization_levels(self):
        """
        Make sure things work as expected when specifying 3 quantization levels
        :return:
        """

        quantization_intervals = [0.0, 0.5, 1.0]

        source = [{"duty_cycle": 0.0},
                  {"duty_cycle": 0.1},
                  {"duty_cycle": 0.2},
                  {"duty_cycle": 0.3},
                  {"duty_cycle": 0.4},
                  {"duty_cycle": 0.5},
                  {"duty_cycle": 0.6},
                  {"duty_cycle": 0.7},
                  {"duty_cycle": 0.8},
                  {"duty_cycle": 0.9},
                  {"duty_cycle": 1.0}]

        prediction_gdf = gpd.GeoDataFrame(source)

        prediction_gdf = quantize_predictions(prediction_gdf=prediction_gdf,
                                              quantization_intervals=quantization_intervals)

        expected = [0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0]

        # make sure quantization works as expected
        # pytest likes lists, less so comparisons of np.array to pandas dataseries
        assert prediction_gdf["duty_cycle"].tolist() == expected

    def test_four_quantization_levels(self):
        """
        Make sure things work as expected when specifying 4 quantization levels
        :return:
        """

        quantization_intervals = [0.0, 0.3, 0.7, 1.0]

        source = [{"duty_cycle": 0.0},
                  {"duty_cycle": 0.1},
                  {"duty_cycle": 0.2},
                  {"duty_cycle": 0.3},
                  {"duty_cycle": 0.4},
                  {"duty_cycle": 0.5},
                  {"duty_cycle": 0.6},
                  {"duty_cycle": 0.7},
                  {"duty_cycle": 0.8},
                  {"duty_cycle": 0.9},
                  {"duty_cycle": 1.0}]

        prediction_gdf = gpd.GeoDataFrame(source)

        prediction_gdf = quantize_predictions(prediction_gdf=prediction_gdf,
                                              quantization_intervals=quantization_intervals)

        expected = [0.0, 0.0, 0.0, 0.3, 0.3, 0.3, 0.3, 0.7, 0.7, 0.7, 1.0]

        # make sure quantization works as expected
        # pytest likes lists, less so comparisons of np.array to pandas dataseries
        assert prediction_gdf["duty_cycle"].tolist() == expected
