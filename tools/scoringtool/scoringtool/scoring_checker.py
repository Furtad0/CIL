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
import os
import glob
import numpy as np
from .mandate_reader import MandateReader
from .environment_reader import EnvironmentReader
from .scoring_reader import ScoringReader

def get_map_node_to_team(match_config_path):
    
    """
    Returns a map of node_id to team_id from a match configuration JSON file
    (batch_input.json or freeplay.json).
    """
    
    node_to_team = {}
    
    with open(match_config_path) as config_file:
        config_json = json.loads(config_file.read())

    for node_info in config_json["NodeData"]:
        node_id = node_info["TrafficNode"]
        image = node_info.get("ImageName")
        is_incumbent = image and ("incumbent" in image or "observer" in image)

        if "team_no" in node_info and not is_incumbent:
            team_id = "Team" + str(node_info["team_no"])
        else:
            team_id = node_info["ImageName"]
            
        node_to_team[node_id] = team_id
        
    return node_to_team

def get_duration(match_config_path):
    
    """
    Returns a match duration from a match configuration JSON file
    (batch_input.json or freeplay.json).
    """
    
    with open(match_config_path) as config_file:
        config_json = json.loads(config_file.read())
        
    return config_json["Duration"]
    
def lookup_prev_stage_start(stage_boundaries, t):
    
    """
    Returns the previous stage start timestamp from a list/set of stage 
    boundaries and current time.
    """
    
    return max([0] + [x for x in stage_boundaries if x <= t])
    
def lookup_next_stage_start(stage_boundaries, t):
    
    """
    Returns the next stage start timestamp from a list/set of stage 
    boundaries and current time.
    """
    
    next_boundaries = [x for x in stage_boundaries if x > t]
    if len(next_boundaries) == 0:
        return None
    else:
        return min(next_boundaries)
        
def running_sum(x):
    
    """
    Returns a list representing the running sum of a list
    """
    
    sum_val = 0
    running_sum = [0] * len(x)
    
    for n in range(len(x)):
        sum_val += x[n]
        running_sum[n] = sum_val 
        
    return running_sum

class ScoringChecker(object):
    
    """
    This class calculates team scores per measurement period, ensemble scores
    per measurement period, stage scores, and overall scores, from DRC traffic
    files and mandate files.
    """
    
    DISCRETE_REQUIRED_THRESHOLD = 0.9
    MGEN_DUMMY_MESSAGE_PORT = 1000
    
    def __init__(self, common_logs_path, mandates_path, environment_path,
                 start_timestamp = None, duration = None,
                 start_offset = 0.0, start_margin = 0, end_margin = 0,
                 second_aligned = False):

        self.common_logs_path = common_logs_path     # path to the common logs for a match
        self.mandates_path = mandates_path           # path to the mandate files for a match
        self.environment_path = environment_path     # path to the environment files for a match
        self.start_timestamp = start_timestamp       # start timestamp (None to determine automatically)
        self.duration = duration                     # match duration (None to determine automatically)
        self.start_offset = float(start_offset)      # additive offset for start timestamp
        self.start_margin = int(start_margin)        # unscored period, in MP's, at the start of a match
        self.end_margin = int(end_margin)            # unscored period, in MP's, at the end of a match
        self.second_aligned = second_aligned         # set start timestamp to the nearest second boundary
        self.mandates_per_flow = {}                  # mandate information by flow
        self.node_to_team = {}                       # map from known node IDs to team ID
        self.stage_boundaries  = set([])             # set of stage boundary time offsets
        self.team_mp_scores = None                   # scores per team for each MP
        self.team_mp_mandates_met = None             # mandate met count per team for each MP
        self.ensemble_mp_scores = None               # ensemble scores for each MP
        self.team_threshold_success = None           # threshold achieved (1 or 0) per team for each MP
        self.team_stage_threshold_values = {}        # threshold value per team for each stage
        self.team_mp_threshold_values = None         # threshold value per team for each MP
        self.ensemble_threshold_success = None       # ensemble threshold achieved (1 or 0) for each MP
        self.team_pe_scores = None                   # points earned per team for each MP
        self.team_scores = None                      # cumulative points earned per team for each MP
        self.stage_scores = None                     # ensemble stage score data [DEPRECATED]
        self.stage_objective_count = None            # count of possible objectives per stage for each team
        self.stage_possible_points = None            # count of possible MP points per stage for each team
        
    def __enter__(self):
        # Retrieve the node-to-team mapping
        if os.path.isfile(os.path.join(self.common_logs_path, "Inputs", "batch_input.json")):
            match_config_path = os.path.join(self.common_logs_path, "Inputs", "batch_input.json")
        elif os.path.isfile(os.path.join(self.common_logs_path, "Inputs", "freeplay.json")):
            match_config_path = os.path.join(self.common_logs_path, "Inputs", "freeplay.json")
        else:
            raise RuntimeError("Match config file not found in %s!" % self.common_logs_path)
        
        self.node_to_team = get_map_node_to_team(match_config_path)
        
        # Read match duration if not specified
        if self.duration is None:
            self.duration = get_duration(match_config_path)
        else:
            self.duration = int(self.duration)
        
        # Read start timestamp if not specified    
        if self.start_timestamp is None:
            rf_start_file = os.path.join(self.common_logs_path, "Inputs", "rf_start_time.json")
            
            if not os.path.isfile(rf_start_file):
                raise RuntimeError("rf_start_timestamp.json not found and timestamp was not specified!")
            
            with open(rf_start_file) as timestamp_file:
                self.start_timestamp = json.loads(timestamp_file.read())
        else:
            self.start_timestamp = float(self.start_timestamp)

        if self.second_aligned:
            self.start_timestamp = round(self.start_timestamp)

        self.start_timestamp += self.start_offset

        # Generate a map of mandates per flow
        with MandateReader(self.mandates_path) as mandate_reader:
            while True:
                next_mandates = mandate_reader.read()
                if next_mandates is None:
                    break
                    
                node_id = next_mandates[0]
                mandate_flows = MandateReader.enumerate_flows(next_mandates[1])
                boundaries = MandateReader.get_stage_boundaries(next_mandates[1])

                for flow_id in mandate_flows:
                    mandate_flows[flow_id]["team"] = self.node_to_team[node_id] if node_id in self.node_to_team else None
                    
                self.mandates_per_flow.update(mandate_flows)
                self.stage_boundaries.update(boundaries)
                
        # Read ensemble threshold values per team
        with EnvironmentReader(self.environment_path) as env_reader:
            while True:
                next_env = env_reader.read()
                if next_env is None:
                    break
                    
                node_id = next_env[0]
                
                if node_id not in self.node_to_team:
                    continue
                    
                team_id = self.node_to_team[node_id]
                
                scoring_thresholds = {}
                for env_update in next_env[1]:
                    scoring_thresholds[env_update["timestamp"]] = (
                        env_update["environment"][0]["scoring_point_threshold"])

                if team_id not in self.team_stage_threshold_values:
                    self.team_stage_threshold_values[team_id] = scoring_thresholds
                elif scoring_thresholds != self.team_stage_threshold_values[team_id]:
                    raise RuntimeError("Team %s ensemble thresholds are inconsistent!" % str(team_id))
                
        traffic_logs_path = os.path.join(self.common_logs_path, "traffic_logs")
        if not os.path.isdir(traffic_logs_path):
            raise RuntimeError(traffic_logs_path + " is not a valid directory!")
            
        team_scores = {}
        team_goals = {}
        team_num_met = {}
        
        # Load the traffic DRC files
        with ScoringReader(traffic_logs_path, self.start_timestamp, self.mandates_path) as scoring_reader:
            while True:
                next_flow_info = scoring_reader.read()
                if next_flow_info is None:
                    break

                if next_flow_info["dstPort"] == self.MGEN_DUMMY_MESSAGE_PORT:
                    continue

                flow_id = next_flow_info["flow"]
                send_node = next_flow_info["sendNode"]
                recv_node = next_flow_info["recvNode"]
                
                send_team = self.node_to_team[send_node]
                recv_team = self.node_to_team[recv_node]
                
                if send_team != recv_team:
                    raise RuntimeError("Flow %d endpoints are on different teams!" % flow_id)
                    
                if flow_id not in self.mandates_per_flow:
                    raise RuntimeError("Mandates are unavailable for flow %d!" % flow_id)
                    
                if len(next_flow_info["stats"]) == 0:
                    continue
                    
                if send_team not in team_scores:
                    team_scores[send_team] = [0] * self.duration
                    team_num_met[send_team] = [0] * self.duration
                    team_goals[send_team] = {}
                    
                if flow_id not in team_goals[send_team]:
                    team_goals[send_team][flow_id] = {
                        "achieved_throughput": [0.0] * self.duration, # Actual throughput bps
                        "desired_throughput": [0.0] * self.duration,  # Desired throughput bps
                        "completion_mp": [0.0] * self.duration,       # Completion of required MP data
                        "met_duration": [0] * self.duration,          # Met duration at each MP
                        "send_node": send_node,                       # Send node for the flow
                        "recv_node": recv_node                        # Recv node for the flow
                    }
                    
                current_team_scores = team_scores[send_team]
                current_team_num_met = team_num_met[send_team]
                    
                packet_size = next_flow_info["size"]
                    
                mandate = self.mandates_per_flow[flow_id]
                is_discrete = ("file_transfer_deadline_s" in mandate["requirements"])
                hold_period = mandate["hold_period"]
                point_value = mandate["point_value"] if "point_value" in mandate else 1
                mandate_start_times = mandate["start_times"]
                min_throughput_bps = 0.0
                mandate_currently_met = False
                mandate_met_duration = 0
                
                if not is_discrete:
                    min_throughput_bps = mandate["requirements"]["min_throughput_bps"]
                    
                it = iter(next_flow_info["stats"])
                stats = next(it)
                t = stats["time"]
                while t < self.duration:
                    try:
                        next_stats = next(it)
                        next_t = next_stats["time"]
                    except StopIteration:
                        next_stats = None
                        next_t = self.duration
                        
                    while t < next_t and t < self.duration:
                        if stats is not None:
                            offered_load_bps = stats["sent"] * packet_size * 8.0
                            throughput_bps = stats["received"] * packet_size * 8.0
                        else:
                            offered_load_bps = 0.0
                            throughput_bps = 0.0
                            
                        stage_start = lookup_prev_stage_start(self.stage_boundaries, t)
                        is_flow_in_stage = (stage_start in mandate_start_times)
                        
                        if not is_flow_in_stage:
                            mandate_met_duration = 0
                            mandate_currently_met = False
                            
                        else:    
                            if offered_load_bps > 0.0:
                                if not is_discrete:
                                    # Per FAQ Q39
                                    current_min_throughput_bps = min(offered_load_bps, min_throughput_bps)
                                else:
                                    # Per scoring document 3.2
                                    current_min_throughput_bps = self.DISCRETE_REQUIRED_THRESHOLD * offered_load_bps
                                    
                                if throughput_bps >= current_min_throughput_bps:
                                    mandate_met_duration += 1
                                    mandate_currently_met = True
                                else:
                                    mandate_met_duration = 0
                                    mandate_currently_met = False
                                    
                                goal_completion_mp = throughput_bps / current_min_throughput_bps if current_min_throughput_bps > 0.0 else 0.0
                            else:
                                current_min_throughput_bps = 0.0
                                goal_completion_mp = 1.0 if mandate_currently_met else 0.0
                                
                                # Per scoring document 3.1
                                if mandate_currently_met:
                                    mandate_met_duration += 1
                            
                            # Award points in the SSP_i MP (per FAQ Q46) and
                            # allow for an unscored end period (per FAQ Q45)
                            if (mandate_met_duration >= hold_period and
                                t >= self.start_margin and
                                t < self.duration - self.end_margin):
                                current_team_scores[t] += point_value
                                current_team_num_met[t] += 1
                                
                            # Record "goal" achieved data for each flow
                            if (t >= self.start_margin and
                                t < self.duration - self.end_margin):
                                team_goals[send_team][flow_id]["achieved_throughput"][t] = throughput_bps
                                team_goals[send_team][flow_id]["desired_throughput"][t] = current_min_throughput_bps
                                team_goals[send_team][flow_id]["completion_mp"][t] = goal_completion_mp
                                team_goals[send_team][flow_id]["met_duration"][t] = mandate_met_duration
                        
                        stats = None
                        t += 1

                    stats = next_stats

        self.team_mp_scores = team_scores
        self.team_mp_goals = team_goals
        self.team_mp_mandates_met = team_num_met
        self.ensemble_mp_scores = np.min(
            [self.team_mp_scores[x] for x in self.team_mp_scores], 0).tolist()
        
        self.team_mp_threshold_values, self.team_threshold_success = self._calculate_individual_threshold_success(
            self.team_mp_scores, self.team_stage_threshold_values)
        self.ensemble_threshold_success = np.min(
            [self.team_threshold_success[x] for x in self.team_threshold_success], 0).tolist()
        
        self.team_pe_scores = self._calculate_team_pe_scores(
            self.team_mp_scores, self.ensemble_mp_scores, self.ensemble_threshold_success)
            
        self.team_scores = self._calculate_team_scores(self.team_pe_scores)
            
        self.stage_scores = self._calculate_stage_scores(self.ensemble_mp_scores)
        
        self.stage_objective_count = self._calculate_stage_objective_count()
        self.stage_possible_points = self._calculate_stage_possible_points()
        
        return self
            
    def get_stage_num(self, t):
        
        """
        Return the stage number of a time offset
        """
        
        sorted_boundaries = sorted(self.stage_boundaries)
        stage_start = lookup_prev_stage_start(self.stage_boundaries, t)
        
        if stage_start in sorted_boundaries:
            return sorted_boundaries.index(stage_start)
        else:
            return None
        
    def get_map_team_id_to_numerical(self):

        """
        Returns a map from team ID to the numerical representation
        used in the Phase 3 Scores JSON file format
        """

        sorted_team_ids = []
        for node_id in sorted(self.node_to_team.keys()):
            if self.node_to_team[node_id] not in sorted_team_ids:
                sorted_team_ids.append(self.node_to_team[node_id])

        team_id_to_num = {}
        for num,team in enumerate(sorted_team_ids):
            team_id_to_num[team] = num

        return team_id_to_num

    def _calculate_team_pe_scores(self, team_mp_scores, ensemble_mp_scores, ensemble_threshold_success):
        
        """
        Return points earned per team for each MP.
        """
        
        team_pe_scores = {}
        
        for team_id in team_mp_scores:
            team_pe_scores[team_id] = [0] * len(team_mp_scores[team_id])
            for t,mp_score in enumerate(team_mp_scores[team_id]):
                team_pe_scores[team_id][t] = (mp_score 
                    if ensemble_threshold_success[t] > 0 
                    else ensemble_mp_scores[t])
                
        return team_pe_scores
        
    def _calculate_team_scores(self, team_pe_scores):
        
        """
        Return cumulative points earned per team for each MP
        """
        
        team_scores = {}
        
        for team_id in team_pe_scores:
            team_scores[team_id] = running_sum(team_pe_scores[team_id])
        
        return team_scores
        
    def _calculate_stage_scores(self, mp_scores):
        
        """
        Return a list of stage scores from a list of MP scores.
        DEPRECATED: these stage scores are no longer used with the newest
        scoring procedure.
        """
        
        stage = -1
        stage_scores = []
        boundary_it = iter(sorted(self.stage_boundaries))
        
        try:
            next_boundary = next(boundary_it)
        except StopIteration:
            next_boundary = len(mp_scores)
            
        current_stage_score = 0
        current_stage_interval = 0
        prev_boundary = 0
            
        for t in range(len(mp_scores)):
            if t >= next_boundary:
                stage_scores.append({
                    "index": stage,
                    "score": current_stage_score,
                    "interval": current_stage_interval
                })
                stage += 1
                current_stage_score = 0
                current_stage_interval = 0
                prev_boundary = next_boundary
                
                try:
                    next_boundary = next(boundary_it)
                except StopIteration:
                    next_boundary = len(mp_scores)

            if mp_scores[t] > current_stage_score:
                current_stage_score = mp_scores[t]
                current_stage_interval = t - prev_boundary
            
        stage_scores.append({
            "index": stage,
            "score": current_stage_score,
            "interval": current_stage_interval
        })
        
        return stage_scores
    
    def _calculate_stage_objective_count(self):

        """
        Return a count of objectives per stage, per team
        """
        
        stage_objective_count = {}

        for flow_id in self.mandates_per_flow:
            mandate = self.mandates_per_flow[flow_id]
            team = mandate["team"]
            
            if team is None:
                continue

            if team not in stage_objective_count:
                stage_objective_count[team] = [0] * len(self.stage_boundaries)

            mandate_start_times = mandate["start_times"]

            for start_time in mandate_start_times:
                stage_num = self.get_stage_num(start_time)
                stage_objective_count[team][stage_num] += 1

        return stage_objective_count
        
    def _calculate_stage_possible_points(self):

        """
        Returns total possible points per stage, per team
        """

        stage_point_count = {}

        for flow_id in self.mandates_per_flow:
            mandate = self.mandates_per_flow[flow_id]
            team = mandate["team"]
            
            if team is None:
                continue
            
            if team not in stage_point_count:
                stage_point_count[team] = [0] * len(self.stage_boundaries)

            mandate_start_times = mandate["start_times"]

            for start_time in mandate_start_times:
                stage_num = self.get_stage_num(start_time)
                stage_point_count[team][stage_num] += mandate["point_value"] if "point_value" in mandate else 1

        return stage_point_count
        
    def _calculate_individual_threshold_success(self, team_mp_scores, team_stage_thresholds):
        
        """
        Returns whether each team is achieving the ensemble threshold for each MP
        """
        
        threshold_values = {}
        threshold_success = {}
        
        for team_id in team_mp_scores:
            threshold_values[team_id] = [0] * len(team_mp_scores[team_id])
            threshold_success[team_id] = [0] * len(team_mp_scores[team_id])
            
            if team_id not in team_stage_thresholds:
                raise RuntimeError("No ensemble thresholds are present for team %s" % str(team_id))

            for t,mp_score in enumerate(team_mp_scores[team_id]):
                threshold_start_time = lookup_prev_stage_start(team_stage_thresholds[team_id].keys(), t)
                
                if threshold_start_time not in team_stage_thresholds[team_id].keys():
                    continue
                    
                scoring_point_threshold = team_stage_thresholds[team_id][threshold_start_time]
                
                threshold_values[team_id][t] = scoring_point_threshold
                threshold_success[team_id][t] = 1 if mp_score >= scoring_point_threshold else 0

        return threshold_values, threshold_success
        
    def __exit__(self, err_typ, err_val, trace):
        return
        
class ScoringPlotter():
    
    """
    This class generates gnuplot commands to plot calculated scoring data
    """
    
    def __init__(self, team_mp_scores, ensemble_mp_scores):
        self.team_mp_scores = team_mp_scores
        self.ensemble_mp_scores = ensemble_mp_scores
        
    def generateGnuplotOutput(self):
        plot_cmds = []
        plot_data = []
        plot_str = ""
        if self.team_mp_scores is not None:
            for team_id in self.team_mp_scores:
                plot_cmds.append("'-' using 1:2 title '" + str(team_id) + " Score' with lines lw 2")
                plot_data.append(self.team_mp_scores[team_id])
                
        if self.ensemble_mp_scores is not None:
            plot_cmds.append("'-' using 1:2 title 'Ensemble Score' with lines lw 2")
            plot_data.append(self.ensemble_mp_scores)
            
        if len(plot_cmds) > 0:
            plot_str += "set title 'Team Scores'\n"
            plot_str += "show title\n"
            plot_str += "set xlabel 'Time'\n"
            plot_str += "show xlabel\n"
            plot_str += "set ylabel 'Score'\n"
            plot_str += "show ylabel\n"
            plot_str += "set size ratio 0.5\n"
            plot_str += "show size\n"
            plot_str += "set key outside rmargin\n"
            plot_str += "show key\n"
            plot_str += "plot " + ",".join(plot_cmds) + "\n"
            for arr in plot_data:
                for x,y in enumerate(arr):
                    plot_str += " " + str(x) + " " + str(y) + "\n"
                plot_str += " e\n"

        return plot_str

def run(args=None):
    
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--common-logs', help="common logs path", required=True)
    parser.add_argument('--mandates', help="mandates path", required=True)
    parser.add_argument('--environment', help="environment files path", required=True)
    parser.add_argument('--start-timestamp', help="start timestamp (read from rf_start_time.json if not specified)")
    parser.add_argument('--start-offset', help="additive offset in seconds from the start timestamp", default=0.0)
    parser.add_argument('--start-margin', help="offset of first scored MP from start time", default=0)
    parser.add_argument('--duration', help="match duration (read from match config file if not specified)")
    parser.add_argument('--end-margin', help="offset of last scored MP from end time", default=0)
    parser.add_argument('--mp-scores', help="output mp scores", action='store_true')
    parser.add_argument('--output-format', help="Options: basic, gnuplot, darpa, darpa_goals, darpa_legacy", default="basic")
    parser.add_argument("--second-aligned", action='store_true',
                        help="start timestamp is aligned to the nearest second boundary of the system clock prior to adding any start offset")
    args = parser.parse_args(args)
    
    with ScoringChecker(args.common_logs, args.mandates, args.environment,
                        start_timestamp = args.start_timestamp, 
                        duration = args.duration, 
                        start_offset = args.start_offset, 
                        start_margin = args.start_margin, 
                        end_margin = args.end_margin,
                        second_aligned = args.second_aligned) as checker:
    
        output = {}
    
        match_score = int(np.sum([x["score"] for x in checker.stage_scores]))
        
        if args.output_format == "gnuplot":
            # Output data in a format for gnuplot
            plotter = ScoringPlotter(
                checker.team_mp_scores, 
                checker.ensemble_mp_scores)
                
            gnuplot_output = plotter.generateGnuplotOutput()
            print(gnuplot_output)
    
        elif args.output_format == "darpa":
            # Output data in a format resembling the DARPA Phase 3 Scores JSON file format
            # https://sc2colosseum.freshdesk.com/support/solutions/articles/22000239290-phase-3-scores-json-file-format
            team_id_to_num = checker.get_map_team_id_to_numerical()
            for team_id in checker.team_mp_scores:
                num = team_id_to_num[team_id]
    
                output[str(num)] = {
                    "IndividualMPScore": checker.team_mp_scores[team_id],
                    "IndividualPEScore": checker.team_pe_scores[team_id],
                    "IndividualScore": checker.team_scores[team_id],
                    "IndividualMatchScore": checker.team_scores[team_id][-1],
                    "IndividualThresholdSuccess": checker.team_threshold_success[team_id]
                }
    
            output["EnsembleScore"] = checker.ensemble_mp_scores
            output["EnsembleThresholdSuccess"] = checker.ensemble_threshold_success
            output["FinalMatchScore"] = match_score
            output["ScoreSamplingRate"] = 1000
    
            total_mos = checker.stage_objective_count[checker.node_to_team[1]]
    
            output["StageScores"] = [{
                "Interval": int(x["interval"]),
                "StageIndex": x["index"],
                "StageScore": x["score"],
                "TotalMOs": total_mos[x["index"]]
            } for x in checker.stage_scores if x["index"] >= 0]
    
            print(json.dumps(output, sort_keys=True))
    
        elif args.output_format == "darpa_legacy":
            # Output data in a format resembling the DARPA Phase 3 Scores JSON file format
            # from prior to phase 3 scrimmage 2 (no bonus points accounted for)
            team_id_to_num = checker.get_map_team_id_to_numerical()
            for team_id in checker.team_mp_scores:
                num = team_id_to_num[team_id]
    
                output[str(num)] = {
                    "IndividualScore": checker.team_mp_scores[team_id]
                }
    
            output["EnsembleScore"] = checker.ensemble_mp_scores
            output["FinalMatchScore"] = match_score
            output["ScoreSamplingRate"] = 1000
    
            total_mos = checker.stage_objective_count[checker.node_to_team[1]]
    
            output["StageScores"] = [{
                "Interval": int(x["interval"]),
                "StageIndex": x["index"],
                "StageScore": x["score"],
                "TotalMOs": total_mos[x["index"]]
            } for x in checker.stage_scores if x["index"] >= 0]
    
            print(json.dumps(output, sort_keys=True))
            
        elif args.output_format == "darpa_goals":
            # Output data in a format resembling the DARPA Phase 3 Goals JSON file format
            # https://sc2colosseum.freshdesk.com/support/solutions/articles/22000239289-phase-3-goals-json-file-format
            team_id_to_num = checker.get_map_team_id_to_numerical()
            output["Goals"] = []
            
            for team_id in checker.team_mp_goals:
                for flow_id in checker.team_mp_goals[team_id]:
                    goal = checker.team_mp_goals[team_id][flow_id]
                    mandate = checker.mandates_per_flow[flow_id]
                    hold_period = mandate["hold_period"]
                    output["Goals"].append({
                        "FlowId": flow_id,
                        "TeamId": team_id_to_num[team_id],
                        "SendNode": goal["send_node"],
                        "ReceiveNode": goal["recv_node"],
                        "DesiredThroughput": goal["desired_throughput"],
                        "AchievedThroughput": goal["achieved_throughput"],
                        "GoalCompletionPreViolation": [int(10000*min(1.0, x)) for x in goal["completion_mp"]],
                        "GoalStabilityPreViolation": [int(10000*min(1.0, float(x)/float(hold_period))) for x in goal["met_duration"]],
                        "SteadyTime": hold_period,
                        "PointValue": mandate["point_value"] if "point_value" in mandate else 1
                    })
                    
            output["Goals"].sort(key=lambda x: x["FlowId"])
                
            print(json.dumps(output, sort_keys=True))

        elif args.output_format == "basic":
            if args.mp_scores:
                output["teamMpScores"] = checker.team_mp_scores
                output["teamMpScores"]["ensemble"] = checker.ensemble_mp_scores
            output["stageScores"] = [x["score"] for x in checker.stage_scores]
            output["matchScore"] = match_score
            
            print(json.dumps(output, indent=2, sort_keys=True), '\n')
            
        else:
            raise RuntimeError("Invalid output format: " + args.output_format)
            
if __name__ == '__main__':
    run()
