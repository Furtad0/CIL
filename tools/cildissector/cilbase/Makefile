.PHONY: install uninstall

WIRESHARK_INSTALL_DIR := $(HOME)/.config/wireshark/plugins/cil-base

all:

install:
	-mkdir -p $(WIRESHARK_INSTALL_DIR)
	cp cil-base.lua $(WIRESHARK_INSTALL_DIR)
	
uninstall:
	rm -rf $(WIRESHARK_INSTALL_DIR)
