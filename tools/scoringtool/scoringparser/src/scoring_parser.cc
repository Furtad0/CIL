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

#include <sstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <math.h>

#include "scoring_parser.h"
#include "traffic_parser.h"

#include "rapidjson/document.h"
#include "rapidjson/stringbuffer.h"
#include "rapidjson/writer.h"

// Duration of a measurement period, in seconds
#define MP_DURATION 1.0
#define MGEN_DUMMY_MESSAGE_PORT 1000

namespace
{
    // Return a string representation of a value
    template<class T>
    inline std::string to_string(const T& value)
    {
        std::ostringstream ss;
        ss << std::setprecision(16) << value;
        return ss.str();
    }
    
    // Set a flow parameter, checking it has not changed if it already exists
    template<class T>
    inline void Update_Flow_Parameter(unsigned int flow_uid, const std::string& field_name, boost::optional<T>& param, const T& new_value)
    {
        if (param && *param != new_value)
        {
            throw std::runtime_error("Error updating parameter \"" + field_name + "\" in flow " + 
                to_string(flow_uid) + ": changed from \"" + to_string(*param) + "\" to \"" + to_string(new_value) + "\"!");
        }
        else if (!param)
        {
            param = new_value;
        }
    }
}

Scoring_Parser::Scoring_Parser()
{
}

Scoring_Parser::~Scoring_Parser()
{
}

void Scoring_Parser::Parse_Max_Latency_Per_Flow(const char * json_flow_mandates, std::map<unsigned int, Flow_Info>& flow_info)
{
    rapidjson::Document mandates;
    mandates.Parse(json_flow_mandates);

    if (!mandates.IsArray())
    {
        throw std::runtime_error("Array expected for JSON flow mandates!");
    }

    for (rapidjson::SizeType i = 0; i < mandates.Size(); i++) 
    {
        if (!mandates[i].HasMember("scenario_goals") || !mandates[i]["scenario_goals"].IsArray())
        {
            throw std::runtime_error("Mandate does not have \"scenario_goals\" array!");
        }
        
        const rapidjson::Value& scenario_goals = mandates[i]["scenario_goals"];

        for (rapidjson::SizeType j = 0; j < scenario_goals.Size(); j++) 
        {
            const rapidjson::Value& goal = scenario_goals[j];
                
            if (!goal.HasMember("requirements") || !goal["requirements"].IsObject())
            {
                throw std::runtime_error("Goal \"requirements\" are missing or incorrect type!");
            }
            
            const rapidjson::Value& requirements = goal["requirements"];
            
            if (!goal.HasMember("flow_uid") || !goal["flow_uid"].IsUint())
            {
                throw std::runtime_error("Goal \"flow_uid\" is missing or incorrect type!");
            }
            
            unsigned int flow_uid = goal["flow_uid"].GetUint();

            if (requirements.HasMember("file_transfer_deadline_s") && requirements["file_transfer_deadline_s"].IsDouble())
            {
                Update_Flow_Parameter(
                    flow_uid, 
                    "max_latency", 
                    flow_info[flow_uid].max_latency, 
                    requirements["file_transfer_deadline_s"].GetDouble()
                    );
            }
            else if (requirements.HasMember("max_latency_s") && requirements["max_latency_s"].IsDouble())
            {
                Update_Flow_Parameter(
                    flow_uid, 
                    "max_latency", 
                    flow_info[flow_uid].max_latency, 
                    requirements["max_latency_s"].GetDouble()
                    );
            }
            else
            {
                throw std::runtime_error("Expected \"max_latency_s\" or \"file_transfer_deadline_s\" of numerical type!");
            }
        }
    }
}

void Scoring_Parser::Parse_Flow_Traffic_Stats(const char * drc_file, double start_timestamp, std::map<unsigned int, Flow_Info>& flow_info)
{
    Traffic_Parser traffic_parser(drc_file);
    Traffic_Event traffic_event;
    
    while (traffic_parser.Next(traffic_event))
    {
        if (traffic_event.action == "ON")
        {
            if (!traffic_event.flow || !traffic_event.srcPort || !traffic_event.dstAddr || !traffic_event.dstPort)
            {
                throw std::runtime_error("Missing field in DRC \"ON\" action!");
            }
            
            unsigned int flow_uid = *traffic_event.flow;
            
            Flow_Info& info = flow_info[flow_uid];
            info.on_time = traffic_event.time;
            
            Update_Flow_Parameter(flow_uid, "srcPort", info.srcPort, *traffic_event.srcPort);
            Update_Flow_Parameter(flow_uid, "dstAddr", info.dstAddr, *traffic_event.dstAddr);
            Update_Flow_Parameter(flow_uid, "dstPort", info.dstPort, *traffic_event.dstPort);
        }
        else if (traffic_event.action == "OFF")
        {
            if (!traffic_event.flow || !traffic_event.srcPort || !traffic_event.dstAddr || !traffic_event.dstPort)
            {
                throw std::runtime_error("Missing field in DRC \"OFF\" action!");
            }
            
            unsigned int flow_uid = *traffic_event.flow;
            
            Flow_Info& info = flow_info[flow_uid];
            info.off_time = traffic_event.time;
            
            Update_Flow_Parameter(flow_uid, "srcPort", info.srcPort, *traffic_event.srcPort);
            Update_Flow_Parameter(flow_uid, "dstAddr", info.dstAddr, *traffic_event.dstAddr);
            Update_Flow_Parameter(flow_uid, "dstPort", info.dstPort, *traffic_event.dstPort);
        }
        else if (traffic_event.action == "LISTEN")
        {
            if (!traffic_event.proto || !traffic_event.port)
            {
                throw std::runtime_error("Missing field in DRC \"LISTEN\" action!");
            }
            
            unsigned int flow_uid = *traffic_event.port;
            
            Flow_Info& info = flow_info[flow_uid];
            info.listen_time = traffic_event.time;
            
            Update_Flow_Parameter(flow_uid, "proto", info.proto, *traffic_event.proto);
            Update_Flow_Parameter(flow_uid, "dstPort", info.dstPort, *traffic_event.port);
        }
        else if (traffic_event.action == "SEND")
        {
            if (!traffic_event.flow || !traffic_event.proto || !traffic_event.seq || !traffic_event.frag ||
                !traffic_event.tos || !traffic_event.srcPort || !traffic_event.dstAddr || !traffic_event.dstPort ||
                !traffic_event.size)
            {
                throw std::runtime_error("Missing field in DRC \"SEND\" action!");
            }
            
            unsigned int flow_uid = *traffic_event.flow;
            
            int mp_num = floor((traffic_event.time - start_timestamp) / MP_DURATION);
            if (mp_num < 0)
            {
                if (*traffic_event.dstPort != MGEN_DUMMY_MESSAGE_PORT) {
                    std::cerr << "SEND measurement period for flow " << flow_uid
                        << " with timestamp " << traffic_event.time
                        << " occurred before start time!" << std::endl;
                }
                continue;
            }
            
            Flow_Info& info = flow_info[flow_uid];
            Measurement_Period_Stats& stats = info.mp_stats[mp_num];
            stats.sent++;
            
            Update_Flow_Parameter(flow_uid, "proto", info.proto, *traffic_event.proto);
            Update_Flow_Parameter(flow_uid, "tos", info.tos, *traffic_event.tos);
            Update_Flow_Parameter(flow_uid, "size", info.size, *traffic_event.size);
            Update_Flow_Parameter(flow_uid, "srcPort", info.srcPort, *traffic_event.srcPort);
            Update_Flow_Parameter(flow_uid, "dstAddr", info.dstAddr, *traffic_event.dstAddr);
            Update_Flow_Parameter(flow_uid, "dstPort", info.dstPort, *traffic_event.dstPort);
        }
        else if (traffic_event.action == "RECV")
        {
            if (!traffic_event.flow || !traffic_event.proto || !traffic_event.seq || !traffic_event.frag || !traffic_event.tos || 
                !traffic_event.srcAddr || !traffic_event.srcPort || !traffic_event.dstAddr || !traffic_event.dstPort ||
                !traffic_event.sent || !traffic_event.size)
            {
                throw std::runtime_error("Missing field in DRC \"RECV\" action!");
            }
            
            unsigned int flow_uid = *traffic_event.flow;
            
            int mp_num = floor((*traffic_event.sent - start_timestamp) / MP_DURATION);
            if (mp_num < 0)
            {
                if (*traffic_event.dstPort != MGEN_DUMMY_MESSAGE_PORT) {
                    std::cerr << "RECV measurement period for flow " << flow_uid
                        << " with sent timestamp " << *traffic_event.sent
                        << " occurred before start time!" << std::endl;
                }
                continue;
            }
            
            Flow_Info& info = flow_info[flow_uid];
            if (!info.max_latency)
            {
                throw std::runtime_error("Max latency is missing for flow " + to_string(flow_uid) + "!");
            }
            
            double latency = traffic_event.time - *traffic_event.sent;
            bool duplicate = !info.received_seqs.insert(*traffic_event.seq).second;
            bool late = (latency > *info.max_latency);
            
            Measurement_Period_Stats& stats = info.mp_stats[mp_num];
            
            if (duplicate)
            {
                stats.duplicate++;
            }
            else if (late)
            {
                stats.late++;
            }
            else
            {
                stats.received++;
            }
            
            Update_Flow_Parameter(flow_uid, "proto", info.proto, *traffic_event.proto);
            Update_Flow_Parameter(flow_uid, "tos", info.tos, *traffic_event.tos);
            Update_Flow_Parameter(flow_uid, "size", info.size, *traffic_event.size);
            Update_Flow_Parameter(flow_uid, "srcAddr", info.srcAddr, *traffic_event.srcAddr);
            Update_Flow_Parameter(flow_uid, "srcPort", info.srcPort, *traffic_event.srcPort);
            Update_Flow_Parameter(flow_uid, "dstAddr", info.dstAddr, *traffic_event.dstAddr);
            Update_Flow_Parameter(flow_uid, "dstPort", info.dstPort, *traffic_event.dstPort);
        }
    }
}

std::string Scoring_Parser::Get_JSON_Flow_Traffic_Stats(const std::map<unsigned int, Flow_Info>& flow_info)
{
    rapidjson::Document flow_stats_doc;
    flow_stats_doc.SetArray();
    
    rapidjson::Document::AllocatorType& allocator = flow_stats_doc.GetAllocator();
    
    for (std::map<unsigned int, Flow_Info>::const_iterator it = flow_info.begin(); it != flow_info.end(); it++)
    {
        if (!it->second.on_time && !it->second.off_time && !it->second.listen_time && it->second.mp_stats.size() == 0)
        {
            // No traffic events occurred for the flow
            continue;
        }
        
        rapidjson::Value flow_item;
        flow_item.SetObject();
        
        flow_item.AddMember("flow", it->first, allocator);
        
        if (it->second.max_latency)
        {
            flow_item.AddMember("maxLatency", *it->second.max_latency, allocator);
        }
        
        if (it->second.on_time)
        {
            flow_item.AddMember("onTime", *it->second.on_time, allocator);
        }
        
        if (it->second.off_time)
        {
            flow_item.AddMember("offTime", *it->second.off_time, allocator);
        }
        
        if (it->second.listen_time)
        {
            flow_item.AddMember("listenTime", *it->second.listen_time, allocator);
        }
        
        if (it->second.proto)
        {
            flow_item.AddMember("proto", rapidjson::StringRef(it->second.proto->c_str()), allocator);
        }
        
        if (it->second.size)
        {
            flow_item.AddMember("size", *it->second.size, allocator);
        }
        
        if (it->second.tos)
        {
            flow_item.AddMember("tos", *it->second.tos, allocator);
        }
        
        if (it->second.srcAddr)
        {
            flow_item.AddMember("srcAddr", rapidjson::StringRef(it->second.srcAddr->c_str()), allocator);
        }
        
        if (it->second.srcPort)
        {
            flow_item.AddMember("srcPort", *it->second.srcPort, allocator);
        }
        
        if (it->second.dstAddr)
        {
            flow_item.AddMember("dstAddr", rapidjson::StringRef(it->second.dstAddr->c_str()), allocator);
        }
        
        if (it->second.dstPort)
        {
            flow_item.AddMember("dstPort", *it->second.dstPort, allocator);
        }
        
        const std::map<int, Measurement_Period_Stats>& mp_stats = it->second.mp_stats;
        
        rapidjson::Value flow_item_mp_stats;
        flow_item_mp_stats.SetArray();
        
        for (std::map<int, Measurement_Period_Stats>::const_iterator mp_it = mp_stats.begin(); mp_it != mp_stats.end(); mp_it++)
        {
            rapidjson::Value stats_item;
            stats_item.SetObject();
            
            stats_item.AddMember("time", mp_it->first, allocator);
            stats_item.AddMember("sent", mp_it->second.sent, allocator);
            stats_item.AddMember("received", mp_it->second.received, allocator);
            stats_item.AddMember("duplicate", mp_it->second.duplicate, allocator);
            stats_item.AddMember("late", mp_it->second.late, allocator);
            
            flow_item_mp_stats.PushBack(stats_item, allocator);
        }
        
        flow_item.AddMember("stats", flow_item_mp_stats, allocator);
        
        flow_stats_doc.PushBack(flow_item, allocator);
    }
    
    rapidjson::StringBuffer buffer;

    buffer.Clear();

    rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
    flow_stats_doc.Accept(writer);

    return std::string( buffer.GetString() );
}