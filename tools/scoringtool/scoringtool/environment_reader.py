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

class EnvironmentReader(object):
    
    """
    This class loads environment JSON files for each node.
    """
    
    def __init__(self, environment_path):
        self.environment_path = environment_path
        self.environment_files = {}
        
    def __enter__(self):
        environment_file_list = glob.glob(os.path.join(self.environment_path, "Node*Environment*.json"))
        
        for environment_file in environment_file_list:
            filename = os.path.basename(environment_file)
            
            node_id_match = re.search("^Node(\d+)", filename)
            if not node_id_match:
                continue

            node_id = int(node_id_match.group(1))
            self.environment_files[node_id] = environment_file
            
        self.environment_iter = iter(sorted(self.environment_files.items()))
        
        return self
        
    def read(self):
        
        """
        Reads the next node_id, json_environment pair.
        """
        
        try:
            environment_info = next(self.environment_iter)
        except StopIteration:
            return
        
        with open(environment_info[1]) as json_file:
            json_data = json.loads(json_file.read())

        return environment_info[0], json_data
                
    def read_node(self, node_id):
        
        """
        Reads the json environment data for a given node_id.
        """
        
        if node_id in self.environment_files:
            with open(self.environment_files[node_id]) as json_file:
                return json.loads(json_file.read())
        else:
            raise RuntimeError("Could not read environment for node %d!" % node_id)

    def __exit__(self, err_typ, err_val, trace):
        return
                
def run(args=None):
    
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('path', help="environment path")
    args = parser.parse_args(args)
    
    with EnvironmentReader(args.path) as reader:
        while True:
            environment_info = reader.read()
            if environment_info is None:
                break
            print("================================================")
            print("Node %d Environment" % environment_info[0])
            print("================================================")
            print(json.dumps(environment_info[1], indent=2, sort_keys=True), '\n')
            
if __name__ == '__main__':
    run()
