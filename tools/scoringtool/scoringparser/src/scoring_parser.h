/*
 * Copyright (C) 2019, Malcolm Stagg
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#pragma once

#include <map>
#include <set>
#include <boost/optional.hpp>

struct Measurement_Period_Stats
{
    Measurement_Period_Stats() :
        sent(0),
        received(0),
        duplicate(0),
        late(0)
    {
    }
    unsigned int sent;       // number of sent messages in the measurement period
    unsigned int received;   // number of received messages in the measurement period, excluding duplicate/late
    unsigned int duplicate;  // number of duplicate messages in the measurement period
    unsigned int late;       // number of late messages in the measurement period, excluding duplicate
};

struct Flow_Info
{
    boost::optional<double> max_latency;   // maximum latency for packets (max_latency_s or file_transfer_deadline_s)
    
    boost::optional<double> on_time;       // "ON" time for the flow
    boost::optional<double> off_time;      // "OFF" time for the flow
    boost::optional<double> listen_time;   // "LISTEN" time for the flow

    boost::optional<std::string> proto;    // proto field (UDP/TCP)
    boost::optional<unsigned int> size;    // size field (bytes)
    boost::optional<unsigned int> tos;     // tos field
    boost::optional<std::string> srcAddr;  // source address field
    boost::optional<unsigned int> srcPort; // source port field
    boost::optional<std::string> dstAddr;  // dest address field
    boost::optional<unsigned int> dstPort; // dest port field

    std::map<int, Measurement_Period_Stats> mp_stats; // statistics per measurement period

    std::set<unsigned int> received_seqs;   // sequence numbers already received
};

class Scoring_Parser 
{
public:
    Scoring_Parser();
    virtual ~Scoring_Parser();
    
    void Parse_Max_Latency_Per_Flow(const char * json_flow_mandates, std::map<unsigned int, Flow_Info>& flow_info);
    void Parse_Flow_Traffic_Stats(const char * drc_file, double start_timestamp, std::map<unsigned int, Flow_Info>& flow_info);
    std::string Get_JSON_Flow_Traffic_Stats(const std::map<unsigned int, Flow_Info>& flow_info);
};
