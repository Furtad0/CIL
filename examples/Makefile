.PHONY: all clean

all: registration_pb2.py cil_pb2.py

clean:
	rm registration_pb2.py
	rm cil_pb2.py

registration_pb2.py: ../proto/registration.proto
	protoc -I ../proto --python_out=./ ../proto/registration.proto

cil_pb2.py: ../proto/cil.proto
	protoc -I ../proto --python_out=./ ../proto/cil.proto
