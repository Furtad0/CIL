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
from shapely.geometry import box
import xarray as xr

from validation.util import xarray_to_geodataframe


class TestXarrayToGeoDataFrame(object):
    def test_simple_conversion(self):
        """
        Test to ensure alternate implementations are correct
        :return:
        """

        delta_t = 0.1
        nfft = 10

        data = np.array([
                [1, 0, 0, 0, 0, 0, 0, 0, 1, 1],
                [0, 0, 0, 0, 0, 0, 0, 0, 1, 1],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
                [0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
                [0, 0, 1, 1, 0, 0, 0, 1, 1, 0],
                [0, 0, 0, 0, 0, 0, 0, 1, 1, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            ],
            dtype=np.uint8)

        num_times = data.shape[0]

        timestamps = np.arange(num_times) * delta_t
        frequencies = (np.arange(0, float(nfft), 1))

        data2 = xr.DataArray(data=data, coords=[('time', timestamps), ('freq', frequencies)])

        result_gdf = xarray_to_geodataframe(data=data2, delta_f=1.0, delta_t=delta_t)

        expected_voxels = [
            box(minx=0, miny=-0.5, maxx=0.1, maxy=0.5),
            box(minx=0, miny= 7.5, maxx=0.2, maxy=9.5),
            box(minx=0.5, miny=1.5, maxx=0.8, maxy=3.5),
            box(minx=0.7, miny=6.5, maxx=0.9, maxy=8.5),
        ]

        expected_gdf = gpd.GeoDataFrame(geometry=expected_voxels)

        print("results")

        print(result_gdf)

        print("expected")

        print(expected_gdf)
        for expected_g, result_g in zip(expected_gdf.geometry, result_gdf.geometry):
            assert expected_g.equals(result_g)
        # # make sure there is only one voxel after merges
        # assert len(merged_gdf.index) == 1
        #
        # # confirm that report_on is correct sum
        # assert merged_gdf.iloc[0]["report_on"] == 60.0