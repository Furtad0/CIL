.PHONY: install uninstall

WIRESHARK_INSTALL_DIR := $(HOME)/.config/wireshark/plugins/zmtp-dissector

all:

install:
	-mkdir -p $(WIRESHARK_INSTALL_DIR)
	cp zmtp-dissector.lua $(WIRESHARK_INSTALL_DIR)
	
uninstall:
	rm -rf $(WIRESHARK_INSTALL_DIR)
