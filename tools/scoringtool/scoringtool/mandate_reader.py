#!/usr/bin/env python
# MIT License
#
# Copyright (c) 2019 Malcolm Stagg
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

from __future__ import print_function
import argparse
import json
import glob
import os
import re

class MandateReader(object):
    
    """
    This class loads mandate JSON files for each node.
    """
    
    def __init__(self, mandates_path):
        self.mandates_path = mandates_path
        self.mandate_files = {}
        
    def __enter__(self):
        mandate_file_list = glob.glob(os.path.join(self.mandates_path, "Node*MandatedOutcomes*.json"))
        
        for mandate_file in mandate_file_list:
            filename = os.path.basename(mandate_file)
            
            node_id_match = re.search("^Node(\d+)", filename)
            if not node_id_match:
                continue

            node_id = int(node_id_match.group(1))
            self.mandate_files[node_id] = mandate_file
            
        self.mandate_iter = iter(sorted(self.mandate_files.items()))
        
        return self
        
    def read(self):
        
        """
        Reads the next node_id, json_mandate pair.
        """
        
        try:
            mandate_info = next(self.mandate_iter)
        except StopIteration:
            return
        
        with open(mandate_info[1]) as json_file:
            json_data = json.loads(json_file.read())

        return mandate_info[0], json_data
                
    def read_node(self, node_id):
        
        """
        Reads the json mandate data for a given node_id.
        """
        
        if node_id in self.mandate_files:
            with open(self.mandate_files[node_id]) as json_file:
                return json.loads(json_file.read())
        else:
            raise RuntimeError("Could not read mandates for node %d!" % node_id)

    @staticmethod
    def enumerate_flows(mandate_data):
        
        """
        Given the mandate data for a node, returns a dict of flow_ids and 
        corresponding mandates.
        """
        
        flow_data = {}
        start_times = {}
        for mandate_entry in mandate_data:
            scenario_goals = mandate_entry["scenario_goals"]
            start_time = mandate_entry["timestamp"]
            for flow_mandate in scenario_goals:
                flow_id = flow_mandate["flow_uid"]
                if flow_id not in flow_data:
                    flow_data[flow_id] = flow_mandate
                    start_times[flow_id] = set([])
                elif flow_data[flow_id] != flow_mandate:
                    raise RuntimeError("Flow " + str(flow_id) + " mandates changed unexpectedly!")
                start_times[flow_id].add(start_time)
                    
        for flow_id in flow_data:
            flow_data[flow_id]["start_times"] = start_times[flow_id]

        return flow_data
        
    @staticmethod
    def get_stage_boundaries(mandate_data):
        
        """
        Given the mandate data for a node, returns a set of stage boundaries.
        """
        
        boundaries = set([])
        for mandate_entry in mandate_data:
            boundaries.add(mandate_entry["timestamp"])
            
        return boundaries
                
    def __exit__(self, err_typ, err_val, trace):
        return
                
def run(args=None):
    
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('path', help="mandates path")
    args = parser.parse_args(args)
    
    with MandateReader(args.path) as reader:
        while True:
            mandate_info = reader.read()
            if mandate_info is None:
                break
            print("================================================")
            print("Node %d Mandated Outcomes" % mandate_info[0])
            print("================================================")
            print(json.dumps(mandate_info[1], indent=2, sort_keys=True), '\n')
            
if __name__ == '__main__':
    run()
