# MIT License
#
# Copyright (c) 2019 Miklos Maroti
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

# Pull base image.
FROM python:3.6-stretch

# Install debconf utils
RUN apt-get -qq update && apt-get -qq install -y \
    debconf-utils \
    unzip \
    libboost-program-options-dev

# now install tshark with appropriate responses for questions not caught by -y
RUN echo "wireshark-common	wireshark-common/install-setuid	boolean	false" | debconf-set-selections && \
  apt-get -qq update && apt-get -qq install -y \
    tshark \
  && rm -rf /var/lib/apt/lists/*

# download and install version 3.5.1 of protoc, the protobuf compiler.
RUN curl -OL -s https://github.com/google/protobuf/releases/download/v3.5.1/protoc-3.5.1-linux-x86_64.zip && \
  unzip -qq protoc-3.5.1-linux-x86_64.zip -d protoc3 && \
  mv protoc3/bin/* /usr/local/bin/ && \
  mv protoc3/include/* /usr/local/include/ && \
  rm -rf protoc3

# Create a non-priveledged user to use so tshark doesn't complain
# The user is named ciltool and is in the ciltool group.
# The user has sudo priviledges
# The username is ciltool and the password is ciltool
RUN addgroup ciltool && \
  useradd -d /home/ciltool -ms /bin/bash -g ciltool -G sudo -p ciltool ciltool

# Define working directory.
WORKDIR /home/ciltool

# copy the current version of the CIL repo into this container
COPY . cil/
RUN chown -R ciltool:ciltool /home/ciltool/cil

# install the Scoring Tool
RUN pip install -e ./cil/tools/scoringtool/

# install the CIL Tool
RUN pip install -e ./cil/tools/ciltool/

# Set the ciltool user active by default
USER ciltool

# Define default command.
CMD ["bash"]
