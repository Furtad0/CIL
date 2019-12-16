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

from validation.cil import merge_overlaps


class TestMergeOverlaps(object):
    def test_merge_three_voxels_single_overlaps(self):
        """
        Test merge behavior when voxel A overlaps B but not C, and voxel B overlaps both A and C
        :return:
        """

        geometry = [box(minx=0.0,  miny=0.0, maxx=10.0, maxy=4.0),
                    box(minx=5.0,  miny=0.0, maxx=15.0, maxy=4.0),
                    box(minx=10.0, miny=0.0, maxx=20.0, maxy=4.0)
                    ]

        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=geometry)

        merged_gdf = merge_overlaps(gdf=tx_gdf)

        # make sure there is only one voxel after merges
        assert len(merged_gdf.index) == 1

        # confirm that report_on is correct sum
        assert merged_gdf.iloc[0]["report_on"] == 60.0

    def test_merge_three_voxels_double_overlaps(self):
        """
        Test merge behavior when voxel A overlaps B and C
        :return:
        """

        geometry = [box(minx=0.0,  miny=0.0, maxx=20.0, maxy=4.0),
                    box(minx=5.0,  miny=0.0, maxx=25.0, maxy=4.0),
                    box(minx=10.0, miny=0.0, maxx=30.0, maxy=4.0)
                    ]

        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 40.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 40.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 40.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=geometry)

        merged_gdf = merge_overlaps(gdf=tx_gdf)

        # make sure there is only one voxel after merges
        assert len(merged_gdf.index) == 1

        # confirm that report_on is correct sum
        assert merged_gdf.iloc[0]["report_on"] == 120.0

    def test_merge_three_voxels_single_overlaps_multi_groups(self):
        """
        Test merge behavior when voxel A overlaps B but not C, and voxel B overlaps both A and C
        :return:
        """

        geometry = [box(minx=0.0, miny=0.0, maxx=10.0, maxy=4.0),
                    box(minx=5.0, miny=0.0, maxx=15.0, maxy=4.0),
                    box(minx=10.0, miny=0.0, maxx=20.0, maxy=4.0),
                    box(minx=0.0, miny=0.0, maxx=10.0, maxy=4.0),
                    box(minx=5.0, miny=0.0, maxx=15.0, maxy=4.0)
                    ]

        src_data = [
            {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.50, "report_on": 20.0},
            {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.50, "report_on": 20.0},
            {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.50, "report_on": 20.0},
            {"msg_id": 2, "dst_ip": "1.1.1.2", "frame_timestamp": 0.0,  "duty_cycle": 0.25, "report_on": 10.0},
            {"msg_id": 2, "dst_ip": "1.1.1.2", "frame_timestamp": 0.0,  "duty_cycle": 0.25, "report_on": 10.0}
        ]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=geometry)

        merged_gdf = merge_overlaps(gdf=tx_gdf)

        # make sure there is only one voxel after merges for each group
        assert len(merged_gdf.index) == 2

        # confirm that report_on is correct sum
        group1 = merged_gdf.loc[merged_gdf["dst_ip"] == "1.1.1.1"]
        assert group1.iloc[0]["report_on"] == 60.0

        group2 = merged_gdf.loc[merged_gdf["dst_ip"] == "1.1.1.2"]
        assert group2.iloc[0]["report_on"] == 20.0

    def test_merge_three_voxels_single_overlaps_no_shared_border(self):
        """
        Test merge behavior when voxel A overlaps B but not C, and voxel B overlaps both A and C.
        Making this a distinct case by ensuring that A and C no longer share a border
        :return:
        """

        geometry = [box(minx=0.0,  miny=0.0, maxx=10.0, maxy=4.0),
                    box(minx=5.0,  miny=0.0, maxx=15.0, maxy=4.0),
                    box(minx=11.0, miny=0.0, maxx=21.0, maxy=4.0)
                    ]

        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=geometry)

        merged_gdf = merge_overlaps(gdf=tx_gdf)

        # make sure there is only one voxel after merges
        assert len(merged_gdf.index) == 1

        # confirm that report_on is correct sum
        assert merged_gdf.iloc[0]["report_on"] == 60.0

    def test_merge_four_voxels_nonuniform(self):
        """
        Test non-uniform merge behavior when:
        - voxel A overlaps B but not C or D
        - voxel B overlaps A, C and D
        - voxel C overlaps B but not A or D
        :return:
        """

        geometry = [box(minx=0.0,  miny=0.0, maxx=10.0, maxy=4.0),
                    box(minx=5.0,  miny=0.0, maxx=35.0, maxy=4.0),
                    box(minx=11.0, miny=0.0, maxx=21.0, maxy=4.0),
                    box(minx=22.0, miny=0.0, maxx=32.0, maxy=4.0)
                    ]

        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 60.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=geometry)

        merged_gdf = merge_overlaps(gdf=tx_gdf)

        # make sure there is only one voxel after merges
        assert len(merged_gdf.index) == 1

        # confirm that report_on is correct sum
        assert merged_gdf.iloc[0]["report_on"] == 120.0

    def test_merge_two_voxel_groups(self):
        """
        Test non-uniform merge behavior when:
        - voxel A overlaps B but not C or D
        - voxel C overlaps D but not A or B
        :return:
        """

        geometry = [box(minx=0.0,  miny=0.0, maxx=10.0, maxy=4.0),
                    box(minx=5.0,  miny=0.0, maxx=15.0, maxy=4.0),
                    box(minx=25.0, miny=0.0, maxx=45.0, maxy=4.0),
                    box(minx=35.0, miny=0.0, maxx=55.0, maxy=4.0)
                    ]

        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 2, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 40.0},
                    {"msg_id": 2, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 40.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=geometry)

        merged_gdf = merge_overlaps(gdf=tx_gdf)

        # make sure there are two voxels after merges
        assert len(merged_gdf.index) == 2

        # confirm that report_on is correct sum for each voxel
        assert merged_gdf.iloc[0]["report_on"] == 40.0
        assert merged_gdf.iloc[1]["report_on"] == 80.0

    def test_merge_voxels_adjacent_nonoverlaps(self):
        """
        Test merge behavior when voxel A shares a boundary with B but does not overlap
        :return:
        """

        geometry = [box(minx=0.0,  miny=0.0, maxx=10.0, maxy=4.0),
                    box(minx=10.0,  miny=0.0, maxx=20.0, maxy=4.0),
                    ]

        src_data = [{"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0},
                    {"msg_id": 1, "dst_ip": "1.1.1.1", "frame_timestamp": 0.0,  "duty_cycle": 0.5, "report_on": 20.0}]

        tx_gdf = gpd.GeoDataFrame(src_data, geometry=geometry)

        merged_gdf = merge_overlaps(gdf=tx_gdf)

        # make sure there are two voxels after merges
        assert len(merged_gdf.index) == 2

        # confirm that report_on is correct sum
        assert merged_gdf.iloc[0]["report_on"] == 20.0
        assert merged_gdf.iloc[1]["report_on"] == 20.0

