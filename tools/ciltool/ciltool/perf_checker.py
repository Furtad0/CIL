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
import json
import logging
import socket
import struct
import os
import math
from scoringtool import ScoringChecker
from google.protobuf.json_format import MessageToJson

from .cil_reader import CilReader

DEFAULT_VALID_WINDOW_START = 0  # January 1970
DEFAULT_VALID_WINDOW_END = (2 ** 32) - 1  # February 2106

def get_node_to_srn_mapping(match_config_filename):
    
    """
    Returns the node-to-srn map from match_conf.json
    """
    
    with open(match_config_filename) as config_file:
        config_json = json.loads(config_file.read())

    if "node_to_srn_mapping" in config_json:
        return config_json["node_to_srn_mapping"]

    else:
        node_to_srn = {}
        for node_info in config_json["NodeData"]:
            node_id = node_info["TrafficNode"]
            srn_num = node_info["srn_number"]
            node_to_srn[node_id] = srn_num
        
        return node_to_srn

class CheckPerfLinkSrc(object):
    """
    This class processes between a source and a destination
    gateway node and validates reported performance from the source
    node is accurate within a certain margin of error.
    """
    
    UNSCORED_END_PERIOD = 15                  # count of MP's at end of match to not consider for scoring
    VALIDATION_WINDOW_SIZE = 5                # look at minimum and maximum actual values within this window to determine validity
    MANDATES_ACHIEVED_ERROR_PERCENT = 50.0    # allow mandate achieved reports to vary from actual by this percentage
    MANDATES_ACHIEVED_ERROR_COUNT = 5         # allow mandate achieved reports to vary from actual by this count (if greater than percentage)
    SCORE_ACHIEVED_ERROR_PERCENT = 50.0       # allow score achieved reports to vary from actual by this percentage
    SCORE_ACHIEVED_ERROR_COUNT = 5            # allow score achieved reports to vary from actual by this count (if greater than percentage)
    PERCENT_ACCURATE_REPORTS_REQUIRED = 75.0  # require at least this percentage of reports to be accurate within the error margins

    class Report(object):
        
        def __init__(self, src, dst):
            self.team_id = None
            self.perf_check_passed = False
            self.sender_ip_address = src
            self.receiver_ip_address = dst
            self.reported_performance = []
            self.mandates_achieved_valid_count = 0
            self.score_achieved_valid_count = 0
            self.total_count = 0
            self.mandates_achieved_passed = True
            self.score_achieved_passed = True
            
    def __init__(self, server, client, common_logs_path, mandates_path, environment_path,
                 gateway_srn, validation_config=None):
        self.log = logging.getLogger(__name__)
        self.report = self.Report(server, client)
        self.last_keepalive = None

        if validation_config is not None:
            self.validation_config = validation_config
        else:
            self.validation_config = {"valid_window_start": DEFAULT_VALID_WINDOW_START,
                                      "valid_window_end": DEFAULT_VALID_WINDOW_END,
                                      "flow_info": False,
                                      "flow_details": False,
                                      "second_aligned": False}
                                        
        # Retrieve the node-to-srn mapping
        if os.path.isfile(os.path.join(common_logs_path, "Inputs", "match_conf.json")):
            match_config_path = os.path.join(common_logs_path, "Inputs", "match_conf.json")
        elif os.path.isfile(os.path.join(common_logs_path, "Inputs", "freeplay.json")):
            match_config_path = os.path.join(common_logs_path, "Inputs", "freeplay.json")

        self.node_to_srn = get_node_to_srn_mapping(match_config_path)
        self.srn_to_node = {v: k for k, v in self.node_to_srn.items()}
            
        self.gateway_srn = int(gateway_srn)
        self.gateway_node = int(self.srn_to_node[gateway_srn]) if self.srn_to_node and gateway_srn in self.srn_to_node else None
        
        if "scoring_context" not in self.validation_config:
            with ScoringChecker(
                common_logs_path=common_logs_path, 
                mandates_path=mandates_path,
                environment_path=environment_path,
                second_aligned=self.validation_config["second_aligned"]) as checker:
                    
                self.validation_config["scoring_context"] = {
                    "scoring_start": checker.start_timestamp,
                    "scoring_duration": checker.duration,
                    "team_mp_scores": checker.team_mp_scores,
                    "team_mp_goals": checker.team_mp_goals,
                    "team_mp_mandates_met": checker.team_mp_mandates_met,
                    "mandates_per_flow": checker.mandates_per_flow,
                    "ensemble_mp_scores": checker.ensemble_mp_scores,
                    "team_threshold_success": checker.team_threshold_success,
                    "team_mp_threshold_values": checker.team_mp_threshold_values,
                    "ensemble_threshold_success": checker.ensemble_threshold_success,
                    "node_to_team": checker.node_to_team
                }
                
        scoring_context = self.validation_config["scoring_context"]
        self.scoring_start = scoring_context["scoring_start"]
        self.scoring_duration = scoring_context["scoring_duration"]
        self.team_mp_scores = scoring_context["team_mp_scores"]
        self.team_mp_goals = scoring_context["team_mp_goals"]
        self.team_mp_mandates_met = scoring_context["team_mp_mandates_met"]
        self.mandates_per_flow = scoring_context["mandates_per_flow"]
        self.ensemble_mp_scores = scoring_context["ensemble_mp_scores"]
        self.team_threshold_success = scoring_context["team_threshold_success"]
        self.team_threshold_values = scoring_context["team_mp_threshold_values"]
        self.ensemble_threshold_success = scoring_context["ensemble_threshold_success"]
                
        self.team_id = scoring_context["node_to_team"][self.gateway_node]
        self.report.team_id = self.team_id
        
    def process(self, message):
        if ('cil_message' not in message
                or message['src_ip'] != self.report.sender_ip_address
                or message['dst_ip'] != self.report.receiver_ip_address):
            self.log.critical('unexpected message')
            return

        # check that this message is within our message validation time window
        # If the message is within the validation time window, set msg_in_timing_window True.
        # False otherwise.
        if(self.validation_config["valid_window_start"] <= message["timestamp"]
                < self.validation_config["valid_window_end"]):
            msg_in_timing_window = True
        else:
            msg_in_timing_window = False
            
        self.process_detailed_performance_message(message, msg_in_timing_window)
            
    def process_detailed_performance_message(self, message, msg_in_timing_window):
        if not message['cil_message'].HasField('detailed_performance'):
            return
            
        # timestamp of the report
        timestamp = self.get_timestamp_value(
            message['cil_message'].timestamp)
            
        # timestamp from the end of the reported measurement period
        perf_time = self.get_timestamp_value(
            message['cil_message'].detailed_performance.timestamp)
            
        mp_num = int(math.floor(perf_time - self.scoring_start))
        mandates_achieved = message['cil_message'].detailed_performance.mandates_achieved
        score_achieved = message['cil_message'].detailed_performance.total_score_achieved
        score_threshold = message['cil_message'].detailed_performance.scoring_point_threshold
        
        # look at the actual data within a window
        validation_window = [
            max(0, mp_num-self.VALIDATION_WINDOW_SIZE),
            min(self.scoring_duration-self.UNSCORED_END_PERIOD, mp_num+self.VALIDATION_WINDOW_SIZE+1)
        ]
        
        if (validation_window[1] <= validation_window[0] or
            mp_num < validation_window[0] or
            mp_num >= validation_window[1]):
            msg_in_timing_window = False
        
        entry = {
            "mp_timestamp": perf_time, 
            "mp_num": mp_num,
            "report": {
                "timestamp": timestamp,
                "mandates_achieved": mandates_achieved,
                "score_achieved": score_achieved,
                "score_threshold": score_threshold,
                "above_threshold": (score_threshold > 0 and score_achieved >= score_threshold)
            },
            "in_timing_window": msg_in_timing_window
        }
        
        if msg_in_timing_window:
            self.process_mandates_achieved_entry(message, mp_num, validation_window, entry)
            self.process_score_achieved_entry(message, mp_num, validation_window, entry)
            self.process_score_threshold_entry(message, mp_num, validation_window, entry)
            
            if self.validation_config["flow_info"]:
                self.process_mandate_performance_entry(message, mp_num, validation_window, entry)
            
            # mark reports valid if both reported and actual scores are above threshold
            # (at any point within the window)
            above_threshold = (entry["report"]["above_threshold"] and
                entry["score_threshold"]["window_any_met"])
            
            mandates_achieved_report_valid = (
                entry["mandates_achieved"]["report_valid"] or 
                above_threshold)
                
            score_achieved_report_valid = (
                entry["score_achieved"]["report_valid"] or 
                above_threshold)
                
            self.report.mandates_achieved_valid_count += (1 if mandates_achieved_report_valid else 0)
            self.report.score_achieved_valid_count += (1 if score_achieved_report_valid else 0)
            self.report.total_count += 1
        
        self.report.reported_performance.append(entry)
        
    def process_mandates_achieved_entry(self, message, mp_num, validation_window, entry):
        
        """
        Update a report entry with mandates achieved validity
        """
        
        mandates_achieved = message['cil_message'].detailed_performance.mandates_achieved
        
        # actual mandates achieved within the window
        actual_window = (
            self.team_mp_mandates_met[self.team_id][validation_window[0]:validation_window[1]])
                
        actual_window_min = min(actual_window)
        actual_window_max = max(actual_window)
        
        # mandates achieved min and max threshold for validity
        min_threshold = (
            max(0, 
                min(int(math.floor((1.0 - self.MANDATES_ACHIEVED_ERROR_PERCENT/100.0) * actual_window_min)), 
                    actual_window_min - self.MANDATES_ACHIEVED_ERROR_COUNT)))
            
        max_threshold = (
            max(int(math.ceil((1.0 + self.MANDATES_ACHIEVED_ERROR_PERCENT/100.0) * actual_window_max)), 
                actual_window_max + self.MANDATES_ACHIEVED_ERROR_COUNT))
                
        # is the mandates achieved report valid?
        report_valid = (
            min_threshold <= mandates_achieved <= max_threshold)
            
        entry["mandates_achieved"] = {
            "actual": self.team_mp_mandates_met[self.team_id][mp_num],
            "reported": mandates_achieved,
            "window_min": actual_window_min,
            "window_max": actual_window_max,
            "min_threshold": min_threshold,
            "max_threshold": max_threshold,
            "report_valid": report_valid
        }
        
    def process_score_achieved_entry(self, message, mp_num, validation_window, entry):
        
        """
        Update a report entry with score achieved validity
        """
        
        score_achieved = message['cil_message'].detailed_performance.total_score_achieved
        
        # actual mp score within the window
        actual_window = (
            self.team_mp_scores[self.team_id][validation_window[0]:validation_window[1]])
                
        actual_window_min = min(actual_window)
        actual_window_max = max(actual_window)
        
        # mp score min and max threshold for validity
        min_threshold = (
            max(0, 
                min(int(math.floor((1.0 - self.SCORE_ACHIEVED_ERROR_PERCENT/100.0) * actual_window_min)), 
                    actual_window_min - self.SCORE_ACHIEVED_ERROR_COUNT)))
            
        max_threshold = (
            max(int(math.ceil((1.0 + self.SCORE_ACHIEVED_ERROR_PERCENT/100.0) * actual_window_max)), 
                actual_window_max + self.SCORE_ACHIEVED_ERROR_COUNT))
                
        # is the score achieved report valid?
        report_valid = (
            min_threshold <= score_achieved <= max_threshold)
            
        entry["score_achieved"] = {
            "actual": self.team_mp_scores[self.team_id][mp_num],
            "reported": score_achieved,
            "window_min": actual_window_min,
            "window_max": actual_window_max,
            "min_threshold": min_threshold,
            "max_threshold": max_threshold,
            "report_valid": report_valid
        }
        
    def process_score_threshold_entry(self, message, mp_num, validation_window, entry):
        
        """
        Update a report entry with score threshold data
        """
        
        # actual above-threshold within the window
        actual_window = (
            self.team_threshold_success[self.team_id][validation_window[0]:validation_window[1]])

        actual_window_any = (max(actual_window) > 0)
        actual_window_all = (min(actual_window) > 0)
        
        actual_value = self.team_threshold_values[self.team_id][mp_num]
        
        entry["score_threshold"] = {
            "threshold": actual_value,
            "met": (self.team_threshold_success[self.team_id][mp_num] > 0),
            "window_any_met": actual_window_any,
            "window_all_met": actual_window_all
        }
        
    def process_mandate_performance_entry(self, message, mp_num, validation_window, entry):
        
        include_flow_details = self.validation_config["flow_details"]
        
        entry["mandate_performance"] = {}        
        
        if include_flow_details:
            entry["mandate_performance"]["flows"] = []
        
        reported_flows = set()
        
        invalid_mandates = 0
        valid_mandates = 0
        duplicate_mandates = 0
        met_mandates_missing = 0
        achieved_mandates_missing = 0
        achieved_or_reported_achieved = 0
        achieved_and_valid = 0
        
        for report in message['cil_message'].detailed_performance.mandates:
            flow_id = report.flow_id
            flow_exists = (flow_id in self.team_mp_goals[self.team_id])
            
            duplicate_report = (flow_id in reported_flows)
            
            reported_flows.add(flow_id)
            
            mandate_performance_entry = {
                "flow_id": flow_id,
                "flow_id_valid": flow_exists,
                "report_missing": False,
                "report_duplicate": duplicate_report,
                "report": {
                    "scalar_performance": report.scalar_performance,
                    "hold_period": report.hold_period,
                    "achieved_duration": report.achieved_duration,
                    "point_value": report.point_value
                }
            }
            
            if report.achieved_duration >= report.hold_period:
                achieved_or_reported_achieved += 1
            
            if flow_exists:
                mandate = self.mandates_per_flow[flow_id]
                actual_scalar_performance = self.team_mp_goals[self.team_id][flow_id]["completion_mp"][mp_num]
                actual_achieved_duration = self.team_mp_goals[self.team_id][flow_id]["met_duration"][mp_num]
                actual_point_value = mandate["point_value"] if "point_value" in mandate else 1
                actual_hold_period = mandate["hold_period"]
                
                mandate_performance_entry["actual"] = {
                    "scalar_performance": actual_scalar_performance,
                    "hold_period": actual_hold_period,
                    "achieved_duration": actual_achieved_duration,
                    "point_value": actual_point_value
                }
                
                # TODO: determine if/how scalar performance can be correctly validated
            
                mandate_performance_entry["hold_period_correct"] = (
                    report.hold_period == actual_hold_period)
                    
                mandate_performance_entry["achieved_duration_correct"] = (
                    abs(report.achieved_duration - actual_achieved_duration) <= self.VALIDATION_WINDOW_SIZE)
                    
                mandate_performance_entry["point_value_correct"] = (
                    report.point_value == actual_point_value)
                    
            mandate_performance_entry["report_valid"] = (
                flow_exists and
                not duplicate_report and
                mandate_performance_entry["hold_period_correct"] and
                mandate_performance_entry["achieved_duration_correct"] and
                mandate_performance_entry["point_value_correct"])
            
            if mandate_performance_entry["report_valid"]:
                valid_mandates += 1
                
                if report.achieved_duration >= report.hold_period:
                    achieved_and_valid += 1
                
            elif duplicate_report:
                duplicate_mandates += 1
            else:
                invalid_mandates += 1
                
            if include_flow_details:
                entry["mandate_performance"]["flows"].append(mandate_performance_entry)
            
        for flow_id in self.team_mp_goals[self.team_id]:
            
            if not flow_id in reported_flows and self.team_mp_goals[self.team_id][flow_id]["met_duration"][mp_num] > 0:
                mandate = self.mandates_per_flow[flow_id]
                actual_scalar_performance = self.team_mp_goals[self.team_id][flow_id]["completion_mp"][mp_num]
                actual_achieved_duration = self.team_mp_goals[self.team_id][flow_id]["met_duration"][mp_num]
                actual_point_value = mandate["point_value"] if "point_value" in mandate else 1
                actual_hold_period = mandate["hold_period"]
                
                mandate_performance_entry = {
                    "flow_id": flow_id,
                    "flow_id_valid": True,
                    "report_missing": True,
                    "actual": {
                        "scalar_performance": actual_scalar_performance,
                        "hold_period": actual_hold_period,
                        "achieved_duration": actual_achieved_duration,
                        "point_value": actual_point_value
                    }
                }
                
                met_mandates_missing += 1
                
                if actual_achieved_duration >= actual_hold_period:
                    achieved_mandates_missing += 1
                
                if include_flow_details:
                    entry["mandate_performance"]["flows"].append(mandate_performance_entry)
        
        entry["mandate_performance"]["num_mandates_valid"] = valid_mandates
        entry["mandate_performance"]["num_mandates_invalid"] = invalid_mandates
        entry["mandate_performance"]["num_duplicate_mandates"] = duplicate_mandates
        entry["mandate_performance"]["num_met_mandates_not_reported"] = met_mandates_missing
        entry["mandate_performance"]["num_achieved_mandates_not_reported"] = achieved_mandates_missing
        entry["mandate_performance"]["num_achieved_mandates_valid"] = achieved_and_valid
        entry["mandate_performance"]["num_achieved_or_reported_achieved"] = achieved_or_reported_achieved
        
    def report_failure(self, test, message):
        if self.report.__getattribute__(test):
            pretty = dict(message)
            pretty['cil_message'] = json.loads(MessageToJson(
                pretty['cil_message'], preserving_proto_field_name=True))
            self.log.debug(test + ' error:\n' +
                           json.dumps(pretty, indent=2, sort_keys=True) + '\n')
        self.report.__setattr__(test, False)

    def get_timestamp_value(self, timestamp):
        if timestamp.picoseconds < 0 or timestamp.picoseconds >= 1e12:
            self.report.picoseconds_valid = False
        return timestamp.seconds + 1e-12 * timestamp.picoseconds

    def validate(self):
        
        report_valid_requirement = int(math.ceil(
            (self.PERCENT_ACCURATE_REPORTS_REQUIRED / 100.0) * self.report.total_count))
        
        self.report.mandates_achieved_passed = (
            self.report.mandates_achieved_valid_count >= report_valid_requirement)
            
        self.report.score_achieved_passed = (
            self.report.score_achieved_valid_count >= report_valid_requirement)
            
        if not self.report.mandates_achieved_passed:
            self.log.warning("Mandates achieved validity requirement failed! %d of %d reports valid, %d required." % 
                (self.report.mandates_achieved_valid_count, self.report.total_count, report_valid_requirement))
                
        if not self.report.score_achieved_passed:
            self.log.warning("Score achieved validity requirement failed! %d of %d reports valid, %d required." % 
                (self.report.score_achieved_valid_count, self.report.total_count, report_valid_requirement))
                
        self.report.perf_check_passed = (
            self.report.mandates_achieved_passed and
            self.report.score_achieved_passed)

        return self.report.perf_check_passed

    def get_report(self):
        self.validate()
        return dict(self.report.__dict__)


class CheckAllPerf(object):

    """
    This class process CIL messages and checks that each link is accurately
    reporting performance within a certain margin of error. You can filter 
    the checked links by specifying the src and/or dst client addresses.
    """

    def __init__(self, common_logs_path, mandates_path, environment_path,
                 gateway_srn, src=None, dst=None, validation_config=None):
        self.links = dict()
        self.src = src
        self.dst = dst
        self.common_logs_path = common_logs_path 
        self.mandates_path = mandates_path
        self.environment_path = environment_path
        self.gateway_srn = gateway_srn
        self.validation_config = validation_config

    def process(self, message):
        if ('cil_message' in message and
                (self.src is None or self.src == message['src_ip']) and
                (self.dst is None or self.dst == message['dst_ip'])):
            key = (message['src_ip'], message['dst_ip'])
            if key not in self.links:
                self.links[key] = CheckPerfLinkSrc(key[0], key[1], 
                    self.common_logs_path, self.mandates_path, self.environment_path,
                    self.gateway_srn, self.validation_config)
            self.links[key].process(message)
            
    def get_reports(self):
        reports = []
        for key in self.links:
            reports.append(self.links[key].get_report())
        return reports

class PerformancePlotter():
    
    """
    This class generates gnuplot commands to plot reported and actual performance data
    """
    
    def binary_to_ranges(self, binary_data):
        
        """
        Convert a list of binary values to ranges where the value is 1
        """
        
        ranges = []
        last_y = 0
        last_x = 0
        for x,y in enumerate(binary_data):
            if y != last_y:
                if y == 0:
                    ranges.append((last_x,x))
                last_y = y
                last_x = x
        if last_y == 1:
            ranges.append((last_x,len(binary_data)))
            
        return ranges
    
    def plot_actual_vs_reported_score(self, report, team_mp_scores, team_threshold_success, plot_validity):
        
        """
        Plot actual vs reported score achieved and whether the team is above-threshold
        """
        
        plot_cmds = []
        plot_data = []
        plot_str = ""
        threshold_ranges = []
        valid_ranges = []
        invalid_ranges = []
        if report["team_id"] in team_mp_scores:
            plot_cmds.append("'-' using 1:2 title 'Actual Score' with lines lw 2")
            plot_data.append([(x,y) for x,y in enumerate(team_mp_scores[report["team_id"]])])
            
        # Plot ranges where team was above-threshold
        if report["team_id"] in team_threshold_success:
            threshold_ranges = self.binary_to_ranges(team_threshold_success[report["team_id"]])
            
        # Plot ranges where score_achieved was valid
        if plot_validity:
            was_valid = False
            valid_start = -1
            invalid_start = -1
            last_mp_num = -1
            for entry in report["reported_performance"]:
                if "score_achieved" in entry:
                    valid = (entry["score_achieved"]["report_valid"] or
                             (entry["report"]["above_threshold"] and 
                              entry["score_threshold"]["window_any_met"]))
                    last_mp_num = entry["mp_num"]
                    if valid and not was_valid:
                        valid_start = entry["mp_num"]
                        if invalid_start >= 0:
                            invalid_ranges.append((invalid_start, entry["mp_num"]-1))
                    elif not valid and was_valid:
                        invalid_start = entry["mp_num"]
                        valid_ranges.append((valid_start, entry["mp_num"]-1))
                    was_valid = valid
            if was_valid:
                valid_ranges.append((valid_start, last_mp_num))
            elif not was_valid and invalid_start >= 0:
                invalid_ranges.append((invalid_start, last_mp_num))
            
        plot_cmds.append("'-' using 1:2 title 'Reported Score' with lines lw 2")
        plot_data.append([(x["mp_num"],x["report"]["score_achieved"]) for x in report["reported_performance"]])
            
        if len(plot_cmds) > 0:
            plot_str += ("set title '" + str(report["team_id"]) + " Actual vs Reported Scores (" 
                + report["sender_ip_address"] + "-" + report["receiver_ip_address"] + ")'\n")
            plot_str += "show title\n"
            plot_str += "set xlabel 'Time'\n"
            plot_str += "show xlabel\n"
            plot_str += "set ylabel 'Score'\n"
            plot_str += "show ylabel\n"
            plot_str += "set size ratio 0.5\n"
            plot_str += "show size\n"
            plot_str += "set key outside rmargin\n"
            plot_str += "show key\n"
            plot_str += "set style rect fc lt -1 fs transparent solid 0.15 noborder\n"
            for rng in threshold_ranges:
                plot_str += "set obj rect from " + str(rng[0]) + ", graph 0 to " + str(rng[1]) + ", graph 1\n"
            for rng in valid_ranges:
                plot_str += "set obj rect from " + str(rng[0]) + ", graph 0 to " + str(rng[1]) + ", graph 1 fc rgb \"green\"\n"
            for rng in invalid_ranges:
                plot_str += "set obj rect from " + str(rng[0]) + ", graph 0 to " + str(rng[1]) + ", graph 1 fc rgb \"red\"\n"
            plot_str += "plot " + ",".join(plot_cmds) + "\n"
            for arr in plot_data:
                for x,y in arr:
                    plot_str += " " + str(x) + " " + str(y) + "\n"
                plot_str += " e\n"

        return plot_str

    def plot_actual_vs_reported_mandates(self, report, team_mp_mandates_met, team_threshold_success, plot_validity):
        
        """
        Plot actual vs reported mandates achieved and whether the team is above-threshold
        """
        
        plot_cmds = []
        plot_data = []
        plot_str = ""
        threshold_ranges = []
        valid_ranges = []
        invalid_ranges = []
        if report["team_id"] in team_mp_mandates_met:
            plot_cmds.append("'-' using 1:2 title 'Actual Mandates' with lines lw 2")
            plot_data.append([(x,y) for x,y in enumerate(team_mp_mandates_met[report["team_id"]])])
            
        # Plot ranges where team was above-threshold
        if report["team_id"] in team_threshold_success:
            threshold_ranges = self.binary_to_ranges(team_threshold_success[report["team_id"]])
            
        # Plot ranges where mandates_achieved was valid
        if plot_validity:
            was_valid = False
            valid_start = -1
            invalid_start = -1
            last_mp_num = -1
            for entry in report["reported_performance"]:
                if "mandates_achieved" in entry:
                    valid = (entry["mandates_achieved"]["report_valid"] or
                             (entry["report"]["above_threshold"] and 
                              entry["score_threshold"]["window_any_met"]))
                    last_mp_num = entry["mp_num"]
                    if valid and not was_valid:
                        valid_start = entry["mp_num"]
                        if invalid_start >= 0:
                            invalid_ranges.append((invalid_start, entry["mp_num"]-1))
                    elif not valid and was_valid:
                        invalid_start = entry["mp_num"]
                        valid_ranges.append((valid_start, entry["mp_num"]-1))
                    was_valid = valid
            if was_valid:
                valid_ranges.append((valid_start, last_mp_num))
            elif not was_valid and invalid_start >= 0:
                invalid_ranges.append((invalid_start, last_mp_num))
                
        plot_cmds.append("'-' using 1:2 title 'Reported Mandates' with lines lw 2")
        plot_data.append([(x["mp_num"],x["report"]["mandates_achieved"]) for x in report["reported_performance"]])
            
        if len(plot_cmds) > 0:
            plot_str += ("set title '" + str(report["team_id"]) + " Actual vs Reported Mandates (" 
                + report["sender_ip_address"] + "-" + report["receiver_ip_address"] + ")'\n")
            plot_str += "show title\n"
            plot_str += "set xlabel 'Time'\n"
            plot_str += "show xlabel\n"
            plot_str += "set ylabel 'Mandates Achieved'\n"
            plot_str += "show ylabel\n"
            plot_str += "set size ratio 0.5\n"
            plot_str += "show size\n"
            plot_str += "set key outside rmargin\n"
            plot_str += "show key\n"
            plot_str += "set style rect fc lt -1 fs transparent solid 0.15 noborder\n"
            for rng in threshold_ranges:
                plot_str += "set obj rect from " + str(rng[0]) + ", graph 0 to " + str(rng[1]) + ", graph 1\n"
            for rng in valid_ranges:
                plot_str += "set obj rect from " + str(rng[0]) + ", graph 0 to " + str(rng[1]) + ", graph 1 fc rgb \"green\"\n"
            for rng in invalid_ranges:
                plot_str += "set obj rect from " + str(rng[0]) + ", graph 0 to " + str(rng[1]) + ", graph 1 fc rgb \"red\"\n"
            plot_str += "plot " + ",".join(plot_cmds) + "\n"
            for arr in plot_data:
                for x,y in arr:
                    plot_str += " " + str(x) + " " + str(y) + "\n"
                plot_str += " e\n"

        return plot_str

def run(args=None):
    import argparse
    import os
    import re
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("filename", help="pcap file")
    parser.add_argument("--common-logs", type=str,
                        help="common logs path", required=True)
    parser.add_argument("--mandates", type=str,
                        help="mandated outcomes path", required=True)
    parser.add_argument("--environment", type=str,
                        help="environment files path", required=True)
    parser.add_argument('-v', metavar='NUM', type=int,
                        help="set logging verbosity", default=1)
    parser.add_argument('--src', metavar='IP',
                        help="filters by source IPv4 address")
    parser.add_argument("--src-srn", type=int, metavar='SRN_NUM',
                        help="srn number of the source's gateway node",
                        default=None)
    parser.add_argument('--src-auto', action='store_true',
                        help="obtain the src filter address and srn number from the filename")
    parser.add_argument('--dst', metavar='IP',
                        help="filters by destination IPv4 address")
    parser.add_argument("--match-start-time", type=int,
                        help="unix epoch time (UTC seconds since 00:00:00 January 1 1970) of the start of the match",
                        default=0)
    parser.add_argument("--match-duration", type=int,
                        help="duration of the match in seconds", default=None)
    parser.add_argument("--second-aligned", action='store_true',
                        help="start timestamp for scoring is aligned to the nearest second boundary of the system clock")
    parser.add_argument("--startup-grace-period", type=int,
                        help="seconds after the start of the match at which to begin evaluating CIL compliance",
                        default=0)
    parser.add_argument('--flow-info', action='store_true',
                        help="include flow information from CIL mandate performance reports in the compliance report")
    parser.add_argument('--flow-details', action='store_true',
                        help="include flow details in the compliance report (may be very verbose, implies --flow-info)")
    parser.add_argument("--gnuplot", type=str,
                        help="generate gnuplot output for \"score_achieved\" or \"mandates_achieved\"", default=None)
    parser.add_argument("--gnuplot-index", type=int,
                        help="index of report to use for gnuplot output", default=0)
    parser.add_argument("--gnuplot-show-validity", action='store_true',
                        help="show valid and invalid regions in gnuplot output")
                        
    args = parser.parse_args(args)
    
    # disable logging if output is going to gnuplot
    if args.gnuplot is not None:
        args.v = 0
        
    if args.flow_details:
        args.flow_info = True
    
    logging.basicConfig(level=logging.CRITICAL if args.v < 1 else
                        logging.INFO if args.v < 2 else logging.DEBUG,
                        stream=sys.stdout)
                        
    if args.src_auto and (not args.src or not args.src_srn):
        match = re.match(
            r'^[-a-zA-Z0-9_]*-srn(\d*)-RES\d*-colbr(\d*)-\d*-\d*\.pcap$',
            os.path.basename(args.filename))
        
        if match:
            args.src = "172.30." + str(100 + int(match.group(2))) + \
                "." + str(100 + int(match.group(1)))
            args.src_srn = int(match.group(1))
            logging.info(
                "Discovered source filter address is {}".format(args.src))
        else:
            logging.critical("Invalid PCAP filename format")

    # validate message timing parameters
    valid_window_start = args.match_start_time + args.startup_grace_period
    if args.match_duration is not None:
        valid_window_end = args.match_start_time + args.match_duration
    else:
        valid_window_end = (2**32)-1 # Will occur in early February 2106. Not a typo.

    if valid_window_end < valid_window_start:
        logging.critical("Bad CIL validation time window: Check that startup grace period is less than match duration")

    # build validation_config dictionary. Notionally this could be used in the future to pass in constants parsed
    # from an external file
    validation_config = {"valid_window_start":valid_window_start,
                         "valid_window_end":valid_window_end,
                         "flow_info": args.flow_info,
                         "flow_details": args.flow_details,
                         "second_aligned": args.second_aligned}

    check_all_perf = CheckAllPerf(args.common_logs, args.mandates, 
                                  args.environment, args.src_srn,
                                  src=args.src, dst=args.dst,
                                  validation_config=validation_config)

    with CilReader(args.filename, read_reg=True) as reader:
        while True:
            message = reader.read()
            if message is None:
                break
            check_all_perf.process(message)

    reports = check_all_perf.get_reports()
    perf_check_passed = len(reports) > 0 and all(report["perf_check_passed"] for report in reports)

    if args.gnuplot is not None:
        
        if "scoring_context" not in validation_config:
            logging.critical("Cannot generate gnuplot output: scoring data not available!")
        else:
            scoring_context = validation_config["scoring_context"]
            
            if args.gnuplot == "score_achieved":
                    
                plotter = PerformancePlotter()
                
                report = reports[args.gnuplot_index]                
                plot_str = plotter.plot_actual_vs_reported_score(
                    report, 
                    scoring_context["team_mp_scores"], 
                    scoring_context["team_threshold_success"],
                    args.gnuplot_show_validity)
                        
                print(plot_str)
                
            elif args.gnuplot == "mandates_achieved":
            
                plotter = PerformancePlotter()
                
                report = reports[args.gnuplot_index]
                plot_str = plotter.plot_actual_vs_reported_mandates(
                    report, 
                    scoring_context["team_mp_mandates_met"], 
                    scoring_context["team_threshold_success"],
                    args.gnuplot_show_validity)
                    
                print(plot_str)
                
            else:
                logging.critical("Invalid gnuplot format: {}".format(args.gnuplot))

    else:
        print(json.dumps(reports,
                         indent=2, sort_keys=True))

    # only exit with successful return code if the CIL checks pass
    if perf_check_passed:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    run()
