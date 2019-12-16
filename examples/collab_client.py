#!/usr/bin/env python
# encoding: utf-8
# MIT License
#
# Copyright (c) 2019 DARPA
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# This file is a part of the CIRN Interaction Language.

import logging
import logging.config
import math
import random
import socket
import struct
import sys
import time

import zmq


import registration_pb2 as reg
import cil_pb2 as cil

from argparse import ArgumentParser
from argparse import ArgumentDefaultsHelpFormatter

LOG_LEVELS = {"DEBUG": logging.DEBUG,
              "INFO": logging.INFO,
              "WARNING": logging.WARNING,
              "ERROR": logging.ERROR,
              "CRITICAL": logging.CRITICAL}


def ip_int_to_string(ip_int):
    """
    Convert integer formatted IP to IP string
    """
    return socket.inet_ntoa(struct.pack('!L', ip_int))


def get_time_now():
    """
    Get the current time as a cil Timestamp
    :return:
    """
    ts_float = time.time()
    ts_seconds = math.floor(ts_float)
    ts_picoseconds = math.floor((ts_float-ts_seconds)*1e12)

    ts = cil.TimeStamp()
    ts.seconds = ts_seconds
    ts.picoseconds = ts_picoseconds

    return ts


def parse_args(argv):
    """Command line options."""

    if argv is not None:
        sys.argv.extend(argv)

    # Setup argument parser                                              ArgumentDefaultsHelpFormatter
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("--server-ip", default="127.0.0.1",
                        help="IP address of Collaboration Server")
    parser.add_argument("--server-port", default=5556, type=int,
                        help="Port the server is listening on")
    parser.add_argument("--client-ip", default="127.0.0.1",
                        help="IP address this client is listening on")
    parser.add_argument("--client-port", default=5557, type=int,
                        help="Port the client listens to for messages from the server")
    parser.add_argument("--peer-port", default=5558, type=int,
                        help="Port the client listens to for peer-to-peer messages")
    parser.add_argument("--message-timeout", default=5.0, type=float,
                        help="Timeout for messages sent to the server or peers")
    parser.add_argument("--log-config-filename", default="collab_client_logging.conf",
                        help="Config file for logging module")
    parser.add_argument("--version-major", default=0, type=int)
    parser.add_argument("--version-minor", default=0, type=int)
    parser.add_argument("--version-patch", default=0, type=int)

    # Process arguments
    args = vars(parser.parse_args())
    
    return args


class CollabClient(object):
    """
    Top level object that runs a very simplistic client. This is not likely to be performant
    for any appreciable amount of messaging traffic. This code is an example of how to
    interact with the server and parse peer messages, but use at your own risk if this is
     included in competition code
    """

    def __init__(self,
                 server_host="127.0.0.1", server_port=5556,
                 client_host="127.0.0.1", client_port=5557,
                 peer_port=5558, message_timeout=5.0,
                 log_config_filename="logging.conf",
                 major=0, minor=0, patch=0):

        # set up logging
        logging.config.fileConfig(log_config_filename)
        self.log = logging.getLogger("collab_client")
        
        self.server_host = server_host
        self.server_port = server_port
        self.client_host = client_host
        self.client_port = client_port
        self.peer_port = peer_port
        self.version_major = major
        self.version_minor = minor
        self.version_patch = patch

        # convert IP address from string to packed bytes representation
        self.client_ip_bytes = struct.unpack('!L', socket.inet_aton(self.client_host))[0]

        self.max_keepalive = None

        # being late is expensive so building in a buffer.
        # we multiply our computed initial keepalive timer value by this scale factor
        # to build in some margin in our reply time
        self.keepalive_safety_margin = 0.75 
        self.keepalive_counter = 0

        self.my_nonce = None

        # initialize a message counter
        self.msg_count = 0

        self.peers = {}

        # This sets up a handler for each type of server message I support
        self.server_msg_handlers = {
                                    "inform": self.handle_inform,
                                    "notify": self.handle_notify,
                                   }

        # This sets up a handler for each top level peer message I support
        self.peer_msg_handlers = {"hello": self.handle_hello}

        # This controls how long the client will try to send messages to other endpoints before
        # throwing a warning and giving up
        self.message_timeout = float(message_timeout)

        # declare ZMQ variables
        self.z_context = None
        self.poller = None
        self.listen_socket = None
        self.peer_pull_socket = None
        self.server_socket = None

        self.tick = None

    def setup(self):
        """
        Set up initial zeromq connections.

        The client needs to start up its main listener for incoming messages from the server 
        and a separate socket to handle messages coming from peers. It will also set up a
        poller for both sockets to allow it to service server and peer connections without
        blocking
        """

        self.z_context = zmq.Context()
        self.poller = zmq.Poller()

        # initialize the listening socket for the server
        self.listen_socket = self.z_context.socket(zmq.PULL)
        self.poller.register(self.listen_socket, zmq.POLLIN)

        self.listen_socket.bind("tcp://%s:%s" % (self.client_host, self.client_port))
        self.log.info("Collaboration client listening on host %s and port %i", 
                      self.client_host, self.client_port)

        # initialize the listening socket for peers
        self.peer_pull_socket = self.z_context.socket(zmq.PULL)
        self.poller.register(self.peer_pull_socket, zmq.POLLIN)
        self.peer_pull_socket.bind("tcp://%s:%s" % (self.client_host, self.peer_port))
        self.log.info("Collaboration client listening for peers on host %s and port %i", 
                      self.client_host, self.peer_port)

        self.log.info("Connecting to server on host %s and port %i",
                      self.server_host, self.server_port)

        # initialize the push socket for sending registration and heartbeat messages to
        # the server
        self.server_socket = self.z_context.socket(zmq.PUSH)
        self.poller.register(self.server_socket, zmq.POLLOUT)
        self.server_socket.connect("tcp://%s:%i" % (self.server_host, self.server_port))

        self.log.debug("Connected to server")

    def teardown(self):
        """
        Close out zeroMQ connections and zeroMQ context cleanly
        """

        self.log.debug("Shutting down sockets")

        # unregister from the poller and close the server listening socket
        self.poller.unregister(self.listen_socket)
        self.listen_socket.close()

        # unregister from the poller and close the server push socket
        self.poller.unregister(self.server_socket)
        self.server_socket.close()

        # unregister from the poller and close the peer listening socket
        self.poller.unregister(self.peer_pull_socket)
        self.peer_pull_socket.close()

        # cleanup any resources allocated for each peer
        peer_id_list = list(self.peers.keys())
        for peer_id in peer_id_list:
            self.cleanup_peer(peer_id)

        self.z_context.term()

        self.log.info("shutdown complete")

    def send_with_timeout(self, sock, message, timeout):
        """
        Try to send a message with some timeout to prevent a single endpoint from
        making me wait forever on a response
        """
        tick = time.time()

        tock = time.time()

        success = False

        # check if an endpoint is open and ready to accept a message. If the endpoint
        # is ready, send the message. If we reach the timeout before an endpoint appears to be
        # ready, give up on the message and log an error
        while tock-tick < timeout and success is False:

            self.log.debug("Trying to send message")
            socks = dict(self.poller.poll())   
        
            if sock in socks and socks[sock] == zmq.POLLOUT:
                self.log.debug("Socket ready, sending")
                sock.send(message.SerializeToString())
                success = True
            else:
                self.log.warning("Tried to send message, endpoint is not connected. Retrying")
                time.sleep(1)
                tock = time.time()

        if not success:
            self.log.error("Could not send message after %f seconds", timeout)
        else:
            self.log.debug("Message sent")

        return

    def list_peers(self):
        """
        Generate a list of peers I know about
        """
        peer_addresses = [val["ip_address"] for key, val in self.peers.items()]

        return peer_addresses

    def add_peer(self, ip):
        """
        I've been informed of a new peer. Add it to the list of peers I'm tracking
        """
        self.log.info("adding peer %i", ip)

        ip_string = ip_int_to_string(ip)

        self.log.debug("trying to connect to peer at IP: %s and port %i",
                       ip_string, self.client_port)

        # create a socket for my new peer
        peer_socket = self.z_context.socket(zmq.PUSH)
        peer_socket.connect("tcp://%s:%i" % (ip_string, self.peer_port))

        # add socket to poller
        self.poller.register(peer_socket, zmq.POLLOUT)

        # store off new peer
        self.peers[ip] = {"ip_address": ip,
                          "ip_string": ip_string,
                          "socket": peer_socket}

        peer_addresses = self.list_peers()

        self.log.debug("list of peers: %s", peer_addresses)

        # send a Hello message to the new client
        self.send_hello(self.peers[ip])

        return

    def cleanup_peer(self, ip):
        """
        Releae any resources allocated for the peer associated with the given IP
        """

        # close socket to old peer
        peer_socket = self.peers[ip]["socket"]
        self.poller.unregister(peer_socket)

        peer_socket.setsockopt(zmq.LINGER, 0)
        peer_socket.close()

        self.log.info("Removing peer %s", ip_int_to_string(ip))

        del self.peers[ip]

        return

    def handle_inform(self, message):
        """
        I received an inform message. Set up my keepalive timer and store off the peers
        """
        self.log.info("Received Inform message")

        inform = message.inform

        # store off the nonce and max keepalive timer value the server told me
        self.my_nonce = inform.client_nonce
        self.max_keepalive = inform.keepalive_seconds

        # store off my neighbor contact info
        neighbors = inform.neighbors
        
        self.log.debug("Inform message contents: %s", message)
        for n in neighbors:
            self.log.debug("Checking Neighbor: %i", n)
            if n != self.client_ip_bytes:
                self.log.debug("Adding Neighbor: %i", n)
                self.add_peer(n)

        return

    def handle_notify(self, message):
        """
        The server has given me an update on my peers list. Handle these updates
        """
        self.log.info("Received Notify message")

        neighbors = message.notify.neighbors
        # find new peers

        # check list for new peers. Do initial setup required for any new peers
        for n in neighbors:
            if n not in self.peers and n != self.client_ip_bytes:
                self.add_peer(n)

        # stop tracking peers that have left
        current_peers = list(self.peers.keys())

        for p in current_peers:
            if p not in neighbors:
                self.cleanup_peer(p)
        return

    def handle_hello(self, message):
        """
        I've received a hello message from a peer. Right now this only prints the message
        """
        self.log.info("Received Hello message from peer %i", message.sender_network_id)
        self.log.debug("Hello Full Contents: %s", message)
        return

    def send_register(self):
        """
        Generate a register message and send it to the collaboration server
        """

        self.log.info("sending register message to server")

        # construct message to send to server
        message = reg.TalkToServer()
        message.register.my_ip_address = self.client_ip_bytes

        self.log.debug("register message contents: %s", message)

        # serialize and send message to server
        self.send_with_timeout(sock=self.server_socket, 
                               message=message, 
                               timeout=self.message_timeout)

    def send_keepalive(self):
        """
        Generate a keepalive message and send it to the collaboration server
        """

        self.log.info("sending keepalive")

        # construct message to send to server
        message = reg.TalkToServer()
        message.keepalive.my_nonce = self.my_nonce

        self.log.debug("keepalive message contents: %s", message)

        # serialize and send message to server
        self.send_with_timeout(sock=self.server_socket, 
                               message=message, 
                               timeout=self.message_timeout)

    def send_leave(self):
        """
        Be polite and tell everyone that we are leaving the collaboration network
        """
        self.log.info("sending leave message")

        # construct message to send to server
        message = reg.TalkToServer()
        message.leave.my_nonce = self.my_nonce

        self.log.debug("leave message contents: %s", message)
        
        # serialize and send message to server
        self.send_with_timeout(sock=self.server_socket, 
                               message=message, 
                               timeout=self.message_timeout)

    def send_hello(self, peer):
        """
        Send a hello message to my peer
        """
        self.log.info("sending hello message to peer %s", peer["ip_string"])

        # Create the top level Collaborate message wrapper
        message = cil.CilMessage()

        # add to the supported declaration and performance lists using the extend()
        # method
        message.hello.version.major = self.version_major
        message.hello.version.minor = self.version_minor
        message.hello.version.patch = self.version_patch

        # set my network ID to my IP address (on the collaboration protocol network)
        message.sender_network_id = self.client_ip_bytes

        message.msg_count = self.msg_count
        self.msg_count = self.msg_count + 1
        ts = get_time_now()
        message.timestamp.seconds = ts.seconds
        message.timestamp.picoseconds = ts.picoseconds

        message.network_type.network_type = cil.NetworkType.COMPETITOR
        
        self.log.debug("Hello message contents: %s", message)

        # serialize and send message to peer
        self.send_with_timeout(sock=peer["socket"], 
                               message=message, 
                               timeout=self.message_timeout)

    def manage_keepalives(self):
        """
        Keep track of my keepalive counter and ensure I send a new keepalive message to the
        server with some random counter and a safety margin to make sure the server isn't
        hit by too many keepalive messages simultaneously and also to ensure I'm not late
        """
        tock = time.time()
        elapsed_time = tock - self.tick

        # is it time to send the keepalive?
        if elapsed_time >= self.keepalive_counter:
            self.tick = tock
            
            self.send_keepalive()
                        
            # picking a new keepalive counter at random so the server is
            # less likely to get bogged down by a bunch of requests at once.
            new_count = random.random()*self.max_keepalive
            
            # building in a fudge factor so we'll always be well below the max
            # timeout
            self.keepalive_counter = new_count * self.keepalive_safety_margin
            self.log.debug("starting new keepalive timer of %f seconds",
                           self.keepalive_counter)

        return

    def run(self):
        """
        Run the client's event loop.
        This is not expected to keep up with high update rates, only as an example of how
        to send messages and handle messages sent to me
        """
        self.tick = time.time()

        self.log.info("Sending register message")
        self.send_register()

        while True:

            # manage the keepalive counter. Don't bother until the server
            # tells us what the keepalive max should be
            if self.max_keepalive is not None:
                self.manage_keepalives()

            socks = dict(self.poller.poll())

            # look for a new message from either a peer or the server
            # Polling may not be that efficient, but this is an example of using
            # the code and talking to the server and peers. This is not intended
            # to be a competition ready client.
            if self.listen_socket in socks:

                self.log.debug("processing message from server")

                # get a message off the server listening socket and deserialize it
                raw_message = self.listen_socket.recv()
                message = reg.TellClient.FromString(raw_message)

                self.log.debug("message was %s", message)

                # find and run the appropriate handler
                try:
                    handler = self.server_msg_handlers[message.WhichOneof("payload")]
                    handler(message)

                except KeyError as err:
                    self.log.error("received unsupported message type %s", err)

            # check for new messages from my peers
            elif self.peer_pull_socket in socks:

                self.log.debug("processing message from peer")

                # get a message off the peer listening socket and deserialize it
                raw_message = self.peer_pull_socket.recv()
                message = cil.CilMessage.FromString(raw_message)

                self.log.debug("message was %s", message)

                # find and run the appropriate handler
                try:
                    handler = self.peer_msg_handlers[message.WhichOneof("payload")]
                    handler(message)

                except KeyError as err:
                    self.log.warning("received unhandled message type %s", err)

            else:
                time.sleep(0.5)


def main(argv=None):

    print("Collaboration Client starting, CTRL-C to exit")    

    # parse command line args
    args = parse_args(argv)
        
    collab_client = CollabClient(server_host=args["server_ip"], server_port=args["server_port"],
                                 client_host=args["client_ip"], client_port=args["client_port"],
                                 peer_port=args["peer_port"],
                                 log_config_filename=args["log_config_filename"])

    collab_client.setup()

    try:
        collab_client.run()
    except KeyboardInterrupt:
        print("interrupt received, stopping...")
        
        try:
            collab_client.send_leave()
        except TypeError as err:
            print("error while shutting down:", err)

        collab_client.teardown()


if __name__ == "__main__":

    main()
