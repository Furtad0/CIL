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
#include <iostream>
#include <exception>
#include <string>
#include <boost/program_options.hpp>

#include "traffic_parser.h"
#include "scoring_parser.h"

namespace po = boost::program_options;

int main(int argc, char * argv[])
{
    std::vector<std::string> input_files;
    double start_timestamp;
    std::string json_flow_mandates;

    po::options_description params("Parameters");
    params.add_options()
        ("help,h", "show usage help")
        ("input,i", po::value<std::vector<std::string> >(&input_files)->multitoken()->required(), "input drc traffic file (multiple can be specified)")
        ("timestamp,t", po::value<double>(&start_timestamp)->required(), "match start timestamp")
        ("mandates,m", po::value<std::string>(&json_flow_mandates)->required(), "list of mandates in a json format")
    ;

    try
    {
        po::variables_map vm;
        po::store(boost::program_options::parse_command_line(argc, argv, params), vm);
    
        if (vm.count("help") || argc <= 1) {
            std::cerr << params << std::endl;
            return 1;
        }
        
        po::notify(vm);

        Scoring_Parser scoring_parser;
        
        std::map<unsigned int, Flow_Info> flow_info_map;
        scoring_parser.Parse_Max_Latency_Per_Flow(json_flow_mandates.c_str(), flow_info_map);
        
        for (int n=0; n<input_files.size(); n++) {
            scoring_parser.Parse_Flow_Traffic_Stats(input_files[n].c_str(), start_timestamp, flow_info_map);
        }
        
        std::string json_output = scoring_parser.Get_JSON_Flow_Traffic_Stats(flow_info_map);
            
        std::cout << json_output << std::endl;
    }
    catch (const std::exception& err) 
    {
        std::cerr << "Hit exception: " << err.what() << std::endl;
        return 1;
    }    
    
    return 0;
}
