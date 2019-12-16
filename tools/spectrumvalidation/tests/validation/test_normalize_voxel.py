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

from validation.cil import normalize_voxel


class TestNormalizeVoxel(object):
    def test_nonzero_picoseconds(self):
        """
        Test merge behavior when voxel A overlaps B but not C, and voxel B overlaps both A and C
        :return:
        """

        v_dict = {
            "time_start": {
                "seconds": 1563327171,
                "picoseconds": int(0.5e12),
            },
            "time_end": {
                "seconds": 1563327171,
                "picoseconds": int(0.75e12),
            },
            "freq_start": 990e6,
            "freq_end": 1010e6,
            "duty_cycle": 0.5,
        }

        match_start_time = 1563327171.25

        msg_timestamp = {
            "seconds": 1563327171,
            "picoseconds": int(0.5e12),
        }

        frame_timestamp = 1563327171.30

        measured_data = False
        msg_id = 1
        src_ip = "1.1.1.1"
        dst_ip = "1.1.1.2"

        v_norm = normalize_voxel(v_dict=v_dict,
                                 match_start_time=match_start_time,
                                 msg_timestamp=msg_timestamp,
                                 frame_timestamp=frame_timestamp,
                                 measured_data=measured_data,
                                 msg_id=msg_id,
                                 src_ip=src_ip,
                                 dst_ip=dst_ip,
                                 default_min_freq=0,
                                 default_max_freq=1e15,
                                 default_min_time=0,
                                 default_max_time=1e18)

        v_expected = {
            "msg_id": msg_id,
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "measured_data": measured_data,
            "voxel": box(minx=0.25, miny=990e6, maxx=0.5, maxy=1010e6),
            "frame_timestamp":0.05,
            "msg_timestamp":0.25,
            "duty_cycle": 0.5,
        }

        assert v_norm["msg_id"] == v_expected["msg_id"]
        assert v_norm["src_ip"] == v_expected["src_ip"]
        assert v_norm["dst_ip"] == v_expected["dst_ip"]
        assert v_norm["measured_data"] == v_expected["measured_data"]
        assert v_norm["voxel"] == v_expected["voxel"]
        assert pytest.approx(v_norm["frame_timestamp"]) == v_expected["frame_timestamp"]
        assert pytest.approx(v_norm["msg_timestamp"]) == v_expected["msg_timestamp"]
        assert pytest.approx(v_norm["duty_cycle"]) == v_expected["duty_cycle"]












