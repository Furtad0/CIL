.PHONY: all clean install uninstall

CXX := g++
CXXFLAGS := -MMD -MP -I. -I../rapidjson/include -O3
LDFLAGS := -lboost_program_options

CC_OBJS := traffic_parser.o scoring_parser.o main.o
CC_DEPS := $(CC_OBJS:.o=.d)

all : scoring_parser

scoring_parser : $(CC_OBJS)
	$(CXX) $(CXXFLAGS) $(CC_OBJS) $(LDFLAGS) -o $@

$(CC_OBJS) : %.o : %.cc

-include $(CC_DEPS)

clean:
	-rm *.o *.d scoring_parser

install:
	cp scoring_parser /usr/local/bin/sc2_scoring_parser

uninstall:
	rm /usr/local/bin/sc2_scoring_parser