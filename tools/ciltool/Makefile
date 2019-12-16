.PHONY: all clean

proto_dir := ../../proto
sources := $(wildcard $(proto_dir)/*.proto)
targets := $(patsubst $(proto_dir)/%.proto,ciltool/%_pb2.py,$(sources))

all: $(targets)

ciltool/%_pb2.py: $(proto_dir)/%.proto
	cd $(proto_dir); protoc --python_out=$(abspath ciltool) $*.proto

clean:
	rm -f ciltool/*_pb2.py
	rm -f ciltool/*_pb2.pyc
	rm -rf dist
	rm -rf ciltool.egg-info
	rm -rf ciltool/__pycache__
