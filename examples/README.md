## Python Examples

The following examples have been tested with ZeroMQ version 4.1.4, pyzmq version 15.2.0,
and Google Protocol Buffers 3.2.0.

You must first run generate registration_pb2.py and cil_pb2.py and place these files
in your python path or these examples will not run.

## Example files
*   collab_server.py: Run `collab_server.py --help` for a full listing of command line arguments
    and defaults. With no arguments, the collaboration server will start up and listen to the 
    loopback IP address for connections coming from clients on the same system. The server can
    support multiple clients, but only one client per unique IP address.

*   collab_client.py: Run `collab_client.py --help` for a full listing of command line arguments
    and defaults. With no arguments, the collaboration client will start up and try to communicate
    with a server listening on the loopback address, 127.0.0.1. To test multiple instances of 
    the client on the same system, consider setting --client-ip to the IP address of your wireless
    or ethernet interface instead of 127.0.0.1. 

*   collab_server_logging.conf: This file controls where and with what verbosity the collab 
    server logs things to either the console or to file. See:
    https://docs.python.org/2/library/logging.config.html#logging-config-fileformat

*   collab_client_logging.conf: This file controls where and with what verbosity the collab 
    server logs things to either the console or to file. See:
    https://docs.python.org/2/library/logging.config.html#logging-config-fileformat

