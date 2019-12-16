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

#include <cstdlib>
#include <stdio.h>
#include <string.h>
#include <stdexcept>

#include "traffic_parser.h"

#define MAX_LINE_LENGTH 4096

Traffic_Parser::Traffic_Parser(const char * drc_filename)
{
    m_drc_file.open(drc_filename);
}

Traffic_Parser::~Traffic_Parser()
{
}

double Traffic_Parser::Parse_DRC_Timestamp(char * timestamp)
{
    char * end_date_time;
    char * date_string = strtok_r(timestamp, "_", &end_date_time);
    char * time_string = strtok_r(NULL, "", &end_date_time);

    if (time_string) 
    {
        char * end_token;
        char * year = strtok_r(date_string, "-", &end_token);
        char * month = strtok_r(NULL, "-", &end_token);
        char * day = strtok_r(NULL, "", &end_token);

        char * hour = strtok_r(time_string, ":", &end_token);
        char * minute = strtok_r(NULL, ":", &end_token);
        char * second = strtok_r(NULL, ".", &end_token);
        char * milliseconds = strtok_r(NULL, "", &end_token);

        if (day && milliseconds) 
        {
            tm time;
            time_t epoch_time;
            double real_time;
            time.tm_year = atoi(year) - 1900;
            time.tm_mon = atoi(month) - 1;
            time.tm_mday = atoi(day);
            time.tm_hour = atoi(hour);
            time.tm_min = atoi(minute);
            time.tm_sec = atoi(second);
            epoch_time = timegm(&time);
            milliseconds[-1] = '.';
            real_time = epoch_time + atof(&milliseconds[-1]);
            return real_time;
        }
    }

    throw std::runtime_error("Cannot parse timestamp!"); 
}

void Traffic_Parser::Parse_DRC_IP_Port(char * ip_port, std::string& ip, std::string& port)
{
    char * ip_port_end_token;
    char * ip_val = strtok_r(ip_port, "/", &ip_port_end_token);
    char * port_val = strtok_r(NULL, "", &ip_port_end_token);

    if (!ip_val || !port_val) 
    {
        throw std::runtime_error("Cannot parse ip/port!"); 
    }

    ip = std::string(ip_val);
    port = std::string(port_val);
}

bool Traffic_Parser::Next(Traffic_Event& traffic_event)
{
    if (!m_drc_file)
    {
        return false;
    }

    char file_line[MAX_LINE_LENGTH];
    m_drc_file.getline(file_line, MAX_LINE_LENGTH); 

    char * end_token;
    char * line_timestamp = strtok_r(file_line," \n", &end_token);

    if (!line_timestamp)
    {
        return false;
    }

    traffic_event = Traffic_Event();
    traffic_event.time = Parse_DRC_Timestamp(line_timestamp);

    char * line_action = strtok_r(NULL, " \n", &end_token);

    if (!line_action)
    {
        throw std::runtime_error("No action present!"); 
    }

    traffic_event.action = std::string(line_action);

    char * next_token = strtok_r(NULL, " \n", &end_token);
    while (next_token) 
    {
        char * inner_end_token;
        char * inner_key = strtok_r(next_token, ">", &inner_end_token);
        char * inner_value = strtok_r(NULL, "", &inner_end_token);

        if (inner_key && inner_value) 
        {
            if (strcmp(inner_key, "dst") == 0)
            {
                std::string ip, port;
                Parse_DRC_IP_Port(inner_value, ip, port);
                traffic_event.dstAddr = ip;
                traffic_event.dstPort = atoi(port.c_str());
            }
            else if (strcmp(inner_key, "src") == 0)
            {
                std::string ip, port;
                Parse_DRC_IP_Port(inner_value, ip, port);
                traffic_event.srcAddr = ip;
                traffic_event.srcPort = atoi(port.c_str());
            }
            else if (strcmp(inner_key, "srcPort") == 0)
            {
                traffic_event.srcPort = atoi(inner_value);
            }
            else if (strcmp(inner_key, "sent") == 0)
            {
                traffic_event.sent = Parse_DRC_Timestamp(inner_value);
            }
            else if (strcmp(inner_key, "proto") == 0)
            {
                traffic_event.proto = inner_value;
            }
            else if (strcmp(inner_key, "port") == 0)
            {
                traffic_event.port = atoi(inner_value);
            }
            else if (strcmp(inner_key, "flow") == 0)
            {
                traffic_event.flow = atoi(inner_value);
            }
            else if (strcmp(inner_key, "seq") == 0)
            {
                traffic_event.seq = atoi(inner_value);
            }
            else if (strcmp(inner_key, "frag") == 0)
            {
                traffic_event.frag = atoi(inner_value);
            }
            else if (strcmp(inner_key, "TOS") == 0)
            {
                traffic_event.tos = atoi(inner_value);
            }
            else if (strcmp(inner_key, "size") == 0)
            {
                traffic_event.size = atoi(inner_value);
            }
            else if (strcmp(inner_key, "gps") == 0)
            {
                traffic_event.gps = std::string(inner_value);
            }
            else if (strcmp(inner_key, "type") == 0)
            {
                traffic_event.type = std::string(inner_value);
            }
            else
            {
                throw std::runtime_error(std::string("unknown field: ") + std::string(inner_key) + " = " + std::string(inner_value));
            }
        }

        next_token = strtok_r(NULL, " \n", &end_token);
    }

    return true;
}

