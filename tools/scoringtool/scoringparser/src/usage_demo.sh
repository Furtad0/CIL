#!/bin/bash

base_path='../scrimmage1_data'
traffic_logs="$base_path/common/MATCH-001-RES-017926/traffic_logs"
start_timestamp=`cat $base_path/common/MATCH-001-RES-017926/Inputs/rf_start_time.json`
mandates="$base_path/common/scenarios/7012/Mandated_Outcomes"

for send_file in $traffic_logs/send_*.drc; do
    listen_file=$traffic_logs/`echo ${send_file##*/} | sed -r 's/send_/listen_/g'`
    if [ ! -e $listen_file ]; then
        echo "File not found: $listen_file"
        exit 1
    fi
    recnode=`echo $send_file | sed -r 's/.*RECNODE-([0-9]*)_.*/\1/g'`
    for mandates_file in ${mandates}/Node${recnode}MandatedOutcomes*.json; do break; done
    ./scoring_parser --input $send_file --input $listen_file --timestamp $start_timestamp --mandates "`cat $mandates_file`"
done
