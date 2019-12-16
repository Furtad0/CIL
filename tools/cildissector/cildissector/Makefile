.PHONY: all clean install uninstall uninstall-all

CIL_VERSION := $(shell git describe)

PROTO_DIR := ../../../proto
BUILD_DIR := ./build/$(CIL_VERSION)
OUTPUT_DIR := $(BUILD_DIR)/output
WIRESHARK_INSTALL_PARENT_DIR := $(HOME)/.config/wireshark/plugins/cil-dissector
WIRESHARK_INSTALL_DIR := $(WIRESHARK_INSTALL_PARENT_DIR)/$(CIL_VERSION)

CXX := g++
CXXFLAGS := -I/usr/include/lua5.2 -I$(BUILD_DIR) -I. -O3 -fPIC

PROTO_SRC := $(wildcard $(PROTO_DIR)/*.proto)
PROTO_CC := $(patsubst $(PROTO_DIR)/%.proto,$(BUILD_DIR)/%.pb.cc,$(PROTO_SRC))
PROTO_OBJ := $(patsubst $(PROTO_DIR)/%.proto,$(BUILD_DIR)/%.pb.o,$(PROTO_SRC))
TARGETS := $(OUTPUT_DIR)/cil_parser.so $(OUTPUT_DIR)/cil-dissector.lua

all: directories $(TARGETS)

directories: $(BUILD_DIR) $(OUTPUT_DIR)

$(BUILD_DIR):
	-mkdir -p $(BUILD_DIR)
	
$(OUTPUT_DIR):
	-mkdir -p $(OUTPUT_DIR)

cil_parser.i : $(PROTO_CC)

cil_parser.cc : $(PROTO_CC)

$(BUILD_DIR)/cil_parser_wrap.cxx: cil_parser.i
	swig -c++ -lua -o $@ $^

$(BUILD_DIR)/cil_parser.o: cil_parser.cc
	$(CXX) $(CXXFLAGS) -c $^ -o $@

$(BUILD_DIR)/cil_parser_wrap.o: $(BUILD_DIR)/cil_parser_wrap.cxx
	$(CXX) $(CXXFLAGS) -c $^ -o $@
	
$(BUILD_DIR)/%.pb.cc: $(PROTO_DIR)/%.proto
	cd $(PROTO_DIR); protoc --cpp_out=$(abspath $(BUILD_DIR)) $*.proto
	
$(BUILD_DIR)/%.pb.o: $(BUILD_DIR)/%.pb.cc
	$(CXX) $(CXXFLAGS) -c $^ -o $@
	
$(OUTPUT_DIR)/cil_parser.so: $(BUILD_DIR)/cil_parser_wrap.o $(BUILD_DIR)/cil_parser.o $(PROTO_OBJ)
	$(CXX) -shared $(CXXFLAGS) -o $@ $^ -lprotobuf 
	
$(OUTPUT_DIR)/cil-dissector.lua: cil-dissector.lua
	sed "s/\[\[@CIL_VERSION@\]\]/$(CIL_VERSION)/g" cil-dissector.lua > $@

install:
	-mkdir -p $(WIRESHARK_INSTALL_DIR)
	cp $(TARGETS) $(WIRESHARK_INSTALL_DIR)
	
uninstall:
	rm -rf $(WIRESHARK_INSTALL_DIR)

uninstall-all:
	rm -rf $(WIRESHARK_INSTALL_PARENT_DIR)

clean:
	rm -rf ./build
