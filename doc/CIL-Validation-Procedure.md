# CIL Validation Procedure

This document details the official procedure for validating CIL Compliance. Suggestions of
improvements are welcome, but DARPA will retain the right to make final decisions on the test
conditions, steps to be followed, and parameter values used. 

## Tools Used
- [CIL Validation tool](https://gitlab.com/darpa-sc2-phase3/CIL/tree/master/tools/ciltool)
- [Scoring validation tool](https://gitlab.com/darpa-sc2-phase3/CIL/tree/master/tools/scoringtool)
- [CIL Spectrum Validation tool](https://gitlab.com/darpa-sc2-phase3/sc2-spectrum-validation/blob/master/spec-val)
- [SC2 Observer](https://gitlab.com/darpa-sc2-phase3/sc2-observer)

## Current Scoring Parameter Values
Here is a snippet from [the scoring validation source code](https://gitlab.com/darpa-sc2-phase3/CIL/blob/master/tools/ciltool/ciltool/perf_checker.py)
to make it clear which values DARPA will be using for validating scoring accuracy beginning in
Scrimmage 3.

```python
    UNSCORED_END_PERIOD = 15                  # count of MP's at end of match to not consider for scoring
    VALIDATION_WINDOW_SIZE = 5                # look at minimum and maximum actual values within this window to determine validity
    MANDATES_ACHIEVED_ERROR_PERCENT = 50.0    # allow mandate achieved reports to vary from actual by this percentage
    MANDATES_ACHIEVED_ERROR_COUNT = 5         # allow mandate achieved reports to vary from actual by this count (if greater than percentage)
    SCORE_ACHIEVED_ERROR_PERCENT = 50.0       # allow score achieved reports to vary from actual by this percentage
    SCORE_ACHIEVED_ERROR_COUNT = 5            # allow score achieved reports to vary from actual by this count (if greater than percentage)
    PERCENT_ACCURATE_REPORTS_REQUIRED = 75.0  # require at least this percentage of reports to be accurate within the error margins
```


## Validation Job Configuration
CIL compliance checks will be executed using batch jobs with each team's submission paired with a 
single passive incumbent and a single staring observer using the Incumbent Protect scenario (9989). 
The template batch file has been updated at 
/share/nas/common/other/scrimmage-utils/cil_validation9989.json

Source code and documentation for the SC2 Observer is online at 
https://gitlab.com/darpa-sc2-phase3/sc2-observer.

Revisions to the SC2 Observer are built as LXC images and posted to the SC2 LZ at 
/share/nas/common/sc2observerX-Y.tar.gz

The recommended baseline radio.conf for the SC2 Observer can be found at 
https://gitlab.com/darpa-sc2-phase3/sc2-observer/blob/master/gr-sc2observer/apps/radio.conf


## Validation Steps 

### 1. Update CIL Tool Image

Update the value of the `EVENT_VERSION` variable and get the latest version of the CIL tools using 
the following:

```bash
export EVENT_TAG=3.5.0  # this should be replaced with the most current CIL tag

docker login registry.gitlab.com
docker pull registry.gitlab.com/darpa-sc2-phase3/cil/cil-tool:${EVENT_TAG}
```

### 2. Update Spectrum Validation Tool Image

Update the value of the `SPEC_VAL_VERSION` variable and get the latest version of the CIL spectrum 
validation tool using the following:

```bash
export SPEC_VAL_VERSION=3.5.0.1  # this should be replaced with the most current Spectrum Validation
tool tag

docker login registry.gitlab.com
docker pull registry.gitlab.com/darpa-sc2-phase3/sc2-spectrum-validation/spec-val-tool:${SPEC_VAL_VERSION}
```

### 3. Run a Batch Job with the Validation Scenario
Execute a validation job on Colosseum with the configuration describe above.



### 4. Download CIL PCAPs
The CIL Validation tool runs checks on the PCAP files from a reservation. Download all `*.pcap` 
files from the Reservation of interest and store to your analysis system at `<common_logs>`.


### 5. Download Mandate Files
The mandated outcome files for each scenario are available on the SC2 NAS at 
`/share/nas/common/scenarios/<scenario num>/Mandated_Outcomes`.

Download all *.json files for the scenario number of interest to a path of your choice on your
analysis system at `<mandates-path>/<scenario num>`.

### 6. Download Traffic Files
Download all *.drc logs from the reservation of interest and store to your analysis system at 
`<common_logs>/traffic_logs`.

### 7. Download RF Log File
Download the pass band RF log file (`pass_band.rf` in the Observer SRN directory by default) from 
the reservation of interest and store to your analysis system at `<common_logs>/observer_logs/`.

### 8. Determine RF Start Time
The RF start time of a reservation can be found in 
`<team_directory>/RESERVATION-<reservation-id>/Inputs/rf_start_time.json`.
Note the value found in this file as RF_START_TIME.

### 9. Validate CIL Messages
For the PCAP file of interest, run

```bash
docker run --rm -it -v <common_logs>:/common_logs registry.gitlab.com/darpa-sc2-phase3/cil/cil-tool:${EVENT_TAG} \
  ciltool cil-checker --src-auto --startup-grace-period=20 --match-duration=630 --match-start-time ${RF_START_TIME}  /common_logs/<pcap filename>
```

### 10. Validate Scoring
For the reservation of interest, run

```bash
docker run --rm -it -v <common_logs>:/common_logs <mandates>:/mandates registry.gitlab.com/darpa-sc2-phase3/cil/cil-tool:${EVENT_TAG} \ 
ciltool perf-checker --src-auto /common_logs/<pcap_filename> --common-logs /common_logs --mandates /mandates --environment /environment \
--second-aligned
```

### 11. Validate Spectrum Usage
The spectrum validation tool outputs a report to a JSON formatted file. The container will require
a writable location for this file. The default user ID in the container is 5001 and the default 
group is 1001. Create some directory `<results>` on your analysis machine and ensure the default 
user in the container can write to that directory. 

For the reservation of interest, run

```bash
docker run --rm -it -v <common_logs>:/common_logs <results>:/results/ \
registry.gitlab.com/darpa-sc2-phase3/sc2-spectrum-validation/spec-val-tool:${SPEC_VAL_VERSION} \
spec-val --rf-file-pattern /common_logs/observer_logs/pass_band.rf --team-id <team_name> \
--scenario-bw 40e6 --scenario-len 630 --pcap-file /common_logs/<pcap_filename> \
--match-start-time ${RF_START_TIME} --prediction-latency 3.0 --prediction-len 10.0
--noise-std-dev 1e-6 --baseline-predict-quantization-intervals 0.0 0.002 0.1 0.2 0.4 0.6 0.8 1.0 --output-filename /results/spec_val_results.json
```

Note: If using PCAP files from normal reservations and not from scrimmage validation runs, the
PCAP files will not be named according to what the script expects. To work around this, use
`--collab-server-srn-num` and  `--collab-gateway-srn-num`. 

The Collaboration Server SRN Number is the SRN number associated with the SRN the Collaboration
Server was running on for that match. You can determine this by looking for the SRN number in the
`*-CollabServer-*.log` file in the directory for the reservation of interest.

The Collaboration Gateway SRN Number is the SRN number associated with the SRN that captured the
PCAP file being analyzed, ie the 'source' SRN number that hosts your network's Collaboration
Gateway. 
