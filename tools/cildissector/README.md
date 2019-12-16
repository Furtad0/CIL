WARNING
=======

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the MIT License for more details.

This tool may not be compatible with the `ciltool` checker, so great care
should be taken if they are used on the same machine.

CIL Wireshark Dissector
=======================

This tool is a plugin for Wireshark to allow for a low-level dissection of
CIL messages. It is designed to perform analysis on the PCAP logs generated
by the SC2 Colosseum. 

The current version is intended to be used on Linux only, and may not be
compatible with Windows. It also requires a version of Wireshark new enough
to support Lua plugins. Lua support was added in Wireshark 1.10.0. The default
version for Ubuntu 16.04 and newer should have support, but may not on Ubuntu
14.04 and older.

If your Wireshark installation does not support Lua plugins, you may upgrade
to the newest version as follows (on Ubuntu):

```bash
sudo add-apt-repository ppa:wireshark-dev/stable
sudo apt-get update
sudo apt-get install wireshark
```

The plugin is divided into three components:

- [zmtp-dissector.lua](zmtpdissector/zmtp-dissector.lua) dissects the
  ZeroMQ Message Transport Protocol (ZMTP) which is used to deliver ZMQ
  traffic. This dissector component is a slightly modified form of:
  https://github.com/whitequark/zmtp-wireshark

- [cil-base.lua](cilbase/cil-base.lua) contains general CIL protocol 
  preferences and allows the selection of a specific CIL version, should 
  multiple CIL dissectors be installed simultaneously. It contains no CIL
  version-specific content, so generally it will not need to be upgraded.

- [cil-dissector.lua](cildissector/cil-dissector.lua) is the CIL version-
  specific dissector. Each dissector registers itself with the CIL base
  dissector to allow the user to select a CIL version to use.

Installation
============

## Prerequisites

The following dependencies are required to build and use the CIL dissector:

- A version of Wireshark new enough to support Lua plugins (tested on 2.6.2)
- Lua 5.2:
```bash
sudo apt-get install liblua5.2-dev
```
- Swig 3.0:
```bash
sudo apt-get install swig3.0
```
- Protobuf C++ Compiler and Runtime 3.5.1 (other versions should also work):
```bash
curl -OL -s https://github.com/google/protobuf/releases/download/v3.5.1/protobuf-cpp-3.5.1.zip
unzip -qq protobuf-cpp-3.5.1.zip -d protobuf-cpp
cd protobuf-cpp/protobuf-3.5.1
./configure
make
make check
sudo make install
sudo ldconfig
```

## Step 1: Install the ZMTP Dissector

This step may be skipped if a recent ZMTP Dissector is already installed.

To install, enter the `zmtpdissector` subdirectory and run `make install`:
```bash
cd zmtpdissector
make install
```

To uninstall, enter the `zmtpdissector` subdirectory and run `make uninstall`:
```bash
cd zmtpdissector
make uninstall
```

## Step 2: Install the CIL Base Dissector

This step may be skipped if a recent CIL Base Dissector is already installed.

To install, enter the `cilbase` subdirectory and run `make install`:
```bash
cd cilbase
make install
```

To uninstall, enter the `cilbase` subdirectory and run `make uninstall`:
```bash
cd cilbase
make uninstall
```

## Step 3: Install the CIL Dissector

To install, enter the `cildissector` subdirectory and run `make`. If
successful, run `make install`:
```bash
cd cildissector
make
make install
```

If you wish to remove any existing build files, run `make clean`.

To uninstall the current version, enter the `cildissector` subdirectory
and run `make uninstall`:
```bash
cd cildissector
make uninstall
```

Or if you wish to uninstall all versions, run `make uninstall-all`.

## Install Location

To inspect the current installed versions, look at the directory:
`~/.config/wireshark/plugins/`

This directory should contain at least three subdirectories:
- `zmtp-dissector`
- `cil-base`
- `cil-dissector`

The `cil-dissector` directory contains a subdirectory for each version of the
CIL dissector installed.

To manually uninstall one or more dissectors, they can safely be deleted from
this directory.

## Reloading Plugins

In general, Wireshark Lua plugins can be reloaded by clicking `Analyze` - 
`Reload Lua Plugins`, or pressing Ctrl+Shift+L.

However, please note that each CIL dissector contains a shared library which
will *not* be reloaded by that process. So, if any changes are made to a 
shared library during development, be sure to close and re-launch Wireshark.

Usage
=====

After installation of all three components, the plugin is immediately available
for use in Wireshark. It is set up by default to dissect messages on TCP ports
5556-5558 as CIL messages.

## Enabling/Disabling the CIL Dissector in Wireshark

Installed dissectors can be viewed in `Analyze` - `Enabled Protocols`.

Disabling either `CIL` or `ZMTP` will completely disable all CIL dissection.

Disabling a specific `CIL.<cil_version>.<message_type>` will disable dissection
of that version/message type combination, showing the raw ZMTP data instead.
This will not affect which CIL version is selected for dissection.

## Disabling the CIL Dissector in TShark

Note that having the CIL dissector enabled may change TShark behavior. 
Specifically, packets on the enabled ports (default TCP 5556-5558) will
be treated as CIL messages when possible. This may break compatibility
with other tools which use TShark, including `ciltool`.

You can modify a TShark command line to disable the CIL dissector as follows:

```bash
tshark -r <input file> --disable-protocol cil [options]
```

Or:

```bash
tshark -r <input file> --disable-protocol zmtp [options]
```

## Selecting a Protocol Version

After loading the PCAP file, there are two ways to select a CIL version:

- Find a CIL message, or filter by `cil`
- In the dissection tree, right-click `CIL Protocol` - 
  `Protocol Preferences` - `CIL Version` and select the desired version. 
  Selecting `latest` will use the newest installed version.

Or:

- Click `Edit` - `Preferences` - `Protocols` - `CIL`
- In the dropdown for `CIL Version` select the desired version. Selecting
  `latest` will use the newest installed version.

## Adjusting Ports

Ports (default range TCP 5556-5558) may also be adjusted in the preferences,
should a different port range be needed.

## Filtering by Field or Value

Detailed dissection and filtering of CIL messages is supported through the
standard Wireshark UI. Some examples are below:

- To find all CIL messages: `cil` or `cil.<version>`
- To find all CIL messages to the server: `cil.<version>.talk_to_server`
- To find all CIL messages to a peer: `cil.<version>.cil_message`
- To find all CIL messages with message count 101: 
  `cil.<version>.cil_message.msg_count == 101`
- To find all CIL messages from peer 12345678: 
  `cil.<version>.cil_message.sender_network_id == 12345678`
- To find all CIL spectrum usage messages:
  `cil.<version>.cil_message.spectrum_usage`
- To find all CIL detailed performance messages with at least 5 mandates:
  `cil.<version>.cil_message.detailed_performance.mandate_count >= 5`

All of the message fields and values can be expanded in the dissection tree
to explore the CIL message contents.
