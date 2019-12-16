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
import subprocess
import multiprocessing
import json
import glob
import os
import re
from .mandate_reader import MandateReader

def get_script_path():
    return os.path.dirname(os.path.realpath(__file__))
    
def run_scoring_parser(file_info):
    send_path = file_info["send_path"]
    listen_path = file_info["listen_path"]
    start_timestamp = file_info["start_timestamp"]
    mandates = file_info["mandates"]
    
    proc = subprocess.Popen([
            os.path.join(get_script_path(), "scoring_parser"), 
            "--input", send_path,
            "--input", listen_path,
            "--timestamp", ("%.6f" % start_timestamp),
            "--mandates", json.dumps(mandates)
        ], stdout=subprocess.PIPE)

    json_result = proc.communicate()[0]
    
    if proc.returncode != 0:
        raise RuntimeError("Scoring parser exited with return code %d!" % proc.returncode)
        
    send_filename = os.path.basename(send_path)

    return send_filename, json.loads(json_result.decode('ascii'))

class ScoringReader(object):
    
    """
    This class loads traffic DRC files into descriptions of each flow,
    containing measurement period statistics for sent, received, duplicate,
    and late packets.
    """

    def __init__(self, traffic_logs_path, start_timestamp, mandates_path):
        self.traffic_logs_path = traffic_logs_path
        self.start_timestamp = start_timestamp
        self.mandate_reader = MandateReader(mandates_path)
        self.results = {}
        
    def __enter__(self):
        self.mandate_reader.__enter__()
        
        files_to_load = []
        
        for send_path in glob.glob(os.path.join(self.traffic_logs_path, "send_*.drc")):
            send_filename = os.path.basename(send_path)
            listen_filename = "listen_" + send_filename[5:]
            listen_path = os.path.join(self.traffic_logs_path, listen_filename)
            
            if not os.path.isfile(send_path):
                raise RuntimeError(send_path + " is not a file!")
                
            if not os.path.isfile(listen_path):
                raise RuntimeError(listen_path + " is not a file!")
                
            send_node_match = re.search("SENDNODE-(\d+)", send_filename)
            
            if not send_node_match:
                raise RuntimeError("Unexpected DRC filename " + send_filename)
                
            send_node = int(send_node_match.group(1))
            
            node_mandates = self.mandate_reader.read_node(send_node)
            
            files_to_load.append({
                "send_path": send_path,
                "listen_path": listen_path,
                "start_timestamp": self.start_timestamp,
                "mandates": node_mandates
            })

        procs = multiprocessing.Pool()
        for send_filename, json_result in procs.imap_unordered(run_scoring_parser, files_to_load):
            self.results[send_filename] = json_result
        procs.close()
        procs.join()
            
        self.results_iter = iter(sorted(self.results.items()))
        self.flow_iter = iter([])
        self.current_filename = None

        return self
        
    def read(self):
        
        """
        Returns all measurement period statistics for the next flow.
        """
        
        try:
            next_flow_info = next(self.flow_iter)
        except StopIteration:
            try:
                next_result = next(self.results_iter)
                self.current_filename = next_result[0]
                self.flow_iter = iter(next_result[1])
                next_flow_info = next(self.flow_iter)
            except StopIteration:
                return
                
        # Append metadata for send and receive node from the DRC filename
        next_flow_info["sendNode"] = int(
            re.search("SENDNODE-(\d+)", self.current_filename).group(1))
            
        next_flow_info["recvNode"] = int(
            re.search("RECNODE-(\d+)", self.current_filename).group(1))
                
        return next_flow_info
                
    def __exit__(self, err_typ, err_val, trace):
        self.mandate_reader.__exit__(err_typ, err_val, trace)
                
def run(args=None):
    
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--traffic-logs', help="traffic logs path", required=True)
    parser.add_argument('--start-timestamp', help="start timestamp", required=True)
    parser.add_argument('--mandates', help="mandates path", required=True)
    args = parser.parse_args(args)
    
    with ScoringReader(args.traffic_logs, float(args.start_timestamp), args.mandates) as reader:
        while True:
            flow_info = reader.read()
            if flow_info is None:
                break
            print("================================================")
            print("Flow %d" % flow_info["flow"])
            print("================================================")
            print(json.dumps(flow_info, indent=2, sort_keys=True), '\n')
            
if __name__ == '__main__':
    run()
