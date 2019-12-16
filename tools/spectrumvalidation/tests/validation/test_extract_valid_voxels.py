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

from validation.cil import extract_valid_voxels


class TestExtractValidVoxels(object):
    def test_trim_to_frame_timestamp(self):
        """
        Test that all fields are accurate when truncating based on a frame timestamp
        :return:
        """

        b = box(minx=0.0, miny=0.0, maxx=20.0, maxy=4.0)

        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 10.0, "duty_cycle": 0.5, "report_on": 40.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=[b])

        valid_gdf = extract_valid_voxels(gdf=tx_gdf)

        # trimming to start at 10 seconds should cut 'report_on' in half
        assert valid_gdf.iloc[0]["report_on"] == 20.0

    def test_trim_to_next_message_timestamp(self):
        """
        Test that all fields are accurate when truncating based on a message update
        :return:
        """

        b1 = box(minx=0.0, miny=0.0, maxx=20.0, maxy=4.0)
        b2 = box(minx=21.0, miny=0.0, maxx=40.0, maxy=4.0)
        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 40.0},
                    {"msg_id": 2, "dst_ip": "1.1.1.1", "frame_timestamp": 10.0, "duty_cycle": 0.5, "report_on": 40.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=[b1, b2])

        valid_gdf = extract_valid_voxels(gdf=tx_gdf)

        # trimming to end at 10 seconds should cut 'report_on' in half
        assert valid_gdf.iloc[0]["report_on"] == 20.0

    def test_trim_to_next_message_timestamp_not_voxel(self):
        """
        Test that all fields are accurate when truncating based on a message update
        Ensure that the truncation is based ONLY on the 'next' message timestamp,
        not the 'next' voxel
        :return:
        """

        b1 = box(minx=0.0, miny=0.0, maxx=20.0, maxy=4.0)
        b2 = box(minx=0.0, miny=0.0, maxx=40.0, maxy=4.0)
        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 40.0},
                    {"msg_id": 2, "dst_ip": "1.1.1.1", "frame_timestamp": 10.0, "duty_cycle": 0.5, "report_on": 40.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=[b1, b2])

        valid_gdf = extract_valid_voxels(gdf=tx_gdf)

        # trimming to end at 10 seconds should cut 'report_on' in half
        assert valid_gdf.iloc[0]["report_on"] == 20.0

    def test_trim_to_next_message_lagged_timestamp(self):
        """
        Test voxel coverage when timestamps lag the voxel declarations
        :return:
        """

        b1 = box(minx=0.0, miny=0.0, maxx=5.0,  maxy=4.0)
        b2 = box(minx=1.0, miny=0.0, maxx=6.0,  maxy=4.0)
        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.1,  "duty_cycle": 0.5, "report_on": 10.0},
                    {"msg_id": 2, "dst_ip": "1.1.1.1", "frame_timestamp": 1.1,  "duty_cycle": 0.5, "report_on": 10.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=[b1, b2])

        valid_gdf = extract_valid_voxels(gdf=tx_gdf)

        # check first voxel. It should be truncated at the start by the frame timestamp of 0.1 seconds, and
        # truncated at the end by the next voxel's frame timestamp of 1.1 seconds.
        expected_voxel_0 = box(minx=0.1, miny=0.0, maxx=1.1, maxy=4.0)

        # note that asserting == here instead of .equals results in Fail as the coordinates aren't guaranteed
        # to be in exactly the same order, and hence the check may fail even though all the points are the same
        assert valid_gdf.iloc[0]["geometry"].equals(expected_voxel_0)
        assert valid_gdf.iloc[0]["report_on"] == 2.0

        # check second voxel. It should be truncated at the start by the frame timestamp of 1.1 seconds
        expected_voxel_1 = box(minx=1.1, miny=0.0, maxx=6.0, maxy=4.0)

        # note that asserting == here instead of .equals results in Fail as the coordinates aren't guaranteed
        # to be in exactly the same order, and hence the check may fail even though all the points are the same
        assert valid_gdf.iloc[1]["geometry"].equals(expected_voxel_1)
        assert valid_gdf.iloc[1]["report_on"] == 4.9*4.0*0.5