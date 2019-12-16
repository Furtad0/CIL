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

#include <string>
#include <map>
#include <fstream>

#include <boost/optional.hpp>

struct Traffic_Event
{
    std::string action;                     // Action field (ON/OFF/LISTEN/SEND/RECV...)
    double time;                            // Timestamp of the event
    boost::optional<double> sent;           // Sent timestamp
    boost::optional<std::string> proto;     // Proto field (UDP/TCP)
    boost::optional<unsigned int> port;     // Port field
    boost::optional<unsigned int> flow;     // Flow field
    boost::optional<unsigned int> seq;      // Sequence field
    boost::optional<unsigned int> frag;     // Fragment field
    boost::optional<unsigned int> tos;      // TOS field
    boost::optional<std::string> dstAddr;   // destination address field
    boost::optional<unsigned int> dstPort;  // destination port field
    boost::optional<std::string> srcAddr;   // source address field
    boost::optional<unsigned int> srcPort;  // source port field
    boost::optional<unsigned int> size;     // message size field
    boost::optional<std::string> gps;       // gps data field
    boost::optional<std::string> type;      // type field (used by RERR)
};

class Traffic_Parser 
{
public:
    Traffic_Parser(const char * drc_filename);
    virtual ~Traffic_Parser();

    bool Next(Traffic_Event& traffic_event);

protected:
    // The following methods may modify the input data for efficiency
    inline double Parse_DRC_Timestamp(char * timestamp);
    inline void Parse_DRC_IP_Port(char * ip_port, std::string& ip, std::string& port);

    std::ifstream m_drc_file;
};
