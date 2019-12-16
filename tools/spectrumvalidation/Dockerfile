FROM python:3.6-stretch

# Create a non-priveledged user to use so tshark doesn't complain
# The user is named ciltool and is in the ciltool group.
# The user has sudo priviledges
# The username is ciltool and the password is ciltool
RUN addgroup ciltool && \
  useradd -d /home/ciltool -ms /bin/bash -g ciltool -G sudo -p ciltool ciltool


# install non-pip installable deps
RUN apt-get -qq update \
  && apt-get install -y \
  debconf-utils \
  libboost-program-options-dev \
  libspatialindex-dev \
  unzip

# now install tshark with appropriate responses for questions not caught by -y
RUN echo "wireshark-common      wireshark-common/install-setuid boolean false" | debconf-set-selections && \
  apt-get -qq update \
  && apt-get -qq install -y \
  tshark \
  && rm -rf /var/lib/apt/lists/*

# download and install version 3.5.1 of protoc, the protobuf compiler.
RUN curl -OL -s https://github.com/google/protobuf/releases/download/v3.5.1/protoc-3.5.1-linux-x86_64.zip && \
  unzip -qq protoc-3.5.1-linux-x86_64.zip -d protoc3 && \
  mv protoc3/bin/* /usr/local/bin/ && \
  mv protoc3/include/* /usr/local/include/ && \
  rm -rf protoc3

# create source directories in container
RUN mkdir -p /src/spec-val/
ADD requirements.txt /src/spec-val/requirements.txt
ADD cil /src/cil

# install pip installable deps
RUN pip install --upgrade pip \
  && pip install -r /src/spec-val/requirements.txt

# I shouldn't HAVE to do this...but here we are.
# pyflux doesn't play nice with standard requirements.txt install
RUN pip install pyflux

# install ciltool
RUN cd /src/cil/tools/ciltool \
  && python setup.py install \
  && rm -rf /src/cil


# Get application source
ADD ./validation /src/spec-val/validation
ADD spec-val /src/spec-val/spec-val
RUN ln -s /src/spec-val/spec-val /usr/local/bin/spec-val

WORKDIR /src/spec-val

# change to the ciltool user
USER ciltool
