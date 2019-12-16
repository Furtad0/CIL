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
from shapely.geometry import box

from validation.score import in_voxel_error
from validation.score import out_of_voxel_error


class TestInVoxelError(object):
    def test_empty_reports_and_empty_transmissions(self):
        tx_gdf = gpd.GeoDataFrame(geometry=[])
        report_in_gdf = gpd.GeoDataFrame(geometry=[])

        normalized_in_voxel_error, a_tx_inside = in_voxel_error(tx_gdf_list=[tx_gdf], report_in_gdf=report_in_gdf)

        assert normalized_in_voxel_error == 0
        assert a_tx_inside == 0

    def test_empty_reports_and_nonempty_transmissions(self):
        b = box(minx=0.0, miny=0.0, maxx=1.0, maxy=1.0)

        tx_gdf = gpd.GeoDataFrame(geometry=[b])
        report_in_gdf = gpd.GeoDataFrame(geometry=[])

        normalized_in_voxel_error, a_tx_inside = in_voxel_error(tx_gdf_list=[tx_gdf], report_in_gdf=report_in_gdf)

        assert normalized_in_voxel_error == 0
        assert a_tx_inside == 0

    def test_nonempty_reports_and_empty_transmissions(self):
        b = box(minx=0.0, miny=0.0, maxx=1.0, maxy=1.0)

        tx_gdf = gpd.GeoDataFrame(geometry=[])
        report_in_gdf = gpd.GeoDataFrame(geometry=[b])
        report_in_gdf["report_on"] = 1.0

        normalized_in_voxel_error, a_tx_inside = in_voxel_error(tx_gdf_list=[tx_gdf], report_in_gdf=report_in_gdf)

        assert normalized_in_voxel_error == 1
        assert a_tx_inside == 0


class TestOutOfVoxelError(object):
    def test_empty_transmissions(self):
        tx_gdf = gpd.GeoDataFrame(geometry=[])
        report_in_gdf = gpd.GeoDataFrame(geometry=[])

        normalized_out_of_voxel_error = out_of_voxel_error(tx_gdf_list=[tx_gdf], report_in_gdf=report_in_gdf)

        assert normalized_out_of_voxel_error == 0

    def test_nonempty_transmissions_and_zero_tx_inside(self):
        b = box(minx=0.0, miny=0.0, maxx=1.0, maxy=1.0)

        tx_gdf = gpd.GeoDataFrame(geometry=[b])
        report_in_gdf = gpd.GeoDataFrame(geometry=[])

        normalized_out_of_voxel_error = out_of_voxel_error(tx_gdf_list=[tx_gdf], report_in_gdf=report_in_gdf)

        assert normalized_out_of_voxel_error == 1

    def test_nonempty_transmissions_and_perfect_overlap(self):
        b = box(minx=0.0, miny=0.0, maxx=1.0, maxy=1.0)

        tx_gdf = gpd.GeoDataFrame(geometry=[b])
        report_in_gdf = gpd.GeoDataFrame(geometry=[b])
        report_in_gdf["report_on"] = 1.0

        normalized_out_of_voxel_error = out_of_voxel_error(tx_gdf_list=[tx_gdf], report_in_gdf=report_in_gdf)

        assert normalized_out_of_voxel_error == 0.0
        
    def test_negative_out_of_voxel_error(self):
        b1 = box(minx=0.0, miny=0.0, maxx=2.0, maxy=1.0)
        b2 = box(minx=0.0, miny=0.0, maxx=1.0, maxy=1.0)
        b3 = box(minx=0.0, miny=0.0, maxx=0.5, maxy=1.0)
        
        tx_gdf_low = gpd.GeoDataFrame(geometry=[b1])
        tx_gdf_mid = gpd.GeoDataFrame(geometry=[b2])
        tx_gdf_high = gpd.GeoDataFrame(geometry=[b3])
        
        report_in_gdf = gpd.GeoDataFrame(geometry=[b2])
        report_in_gdf["report_on"] = 1.0

        normalized_in_voxel_error, a_tx_inside = in_voxel_error(tx_gdf_list=[tx_gdf_low, tx_gdf_mid, tx_gdf_high], report_in_gdf=report_in_gdf)

        assert normalized_in_voxel_error == 0.0
        assert a_tx_inside == 1.0
        
        normalized_out_of_voxel_error = out_of_voxel_error(tx_gdf_list=[tx_gdf_low, tx_gdf_mid, tx_gdf_high], report_in_gdf=report_in_gdf)

        assert normalized_out_of_voxel_error == 0.0

