subdirs := scoringparser/src

.PHONY: all subdirs $(subdirs) clean

targets := scoringtool/scoring_parser

all: subdirs $(targets)

subdirs: $(subdirs)

scoringparser/src:
	$(MAKE) -C scoringparser/src
    
scoringtool/scoring_parser: scoringparser/src
	cp scoringparser/src/scoring_parser scoringtool

clean:
	$(MAKE) -C scoringparser/src clean
	rm -rf dist
	rm -rf scoringtool.egg-info
	rm -rf scoringtool/__pycache__
	rm -rf scoringtool/scoring_parser
