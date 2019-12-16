-- MIT License
--
-- Copyright (c) 2019 Malcolm Stagg
--
-- Permission is hereby granted, free of charge, to any person obtaining a copy
-- of this software and associated documentation files (the "Software"), to deal
-- in the Software without restriction, including without limitation the rights
-- to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
-- copies of the Software, and to permit persons to whom the Software is
-- furnished to do so, subject to the following conditions:
--
-- The above copyright notice and this permission notice shall be included in all
-- copies or substantial portions of the Software.
--
-- THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
-- IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
-- FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
-- AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
-- LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
-- OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
-- SOFTWARE.
--
-- This file is a part of the CIRN Interaction Language.

local DEFAULT_SERVER_PORT = 5556
local DEFAULT_CLIENT_PORT = 5557
local DEFAULT_PEER_PORT = 5558

local zmtp_path = persconffile_path("plugins/zmtp-dissector/")
package.path = package.path .. ";" .. zmtp_path .. "?.lua"

local status, cil_proto = pcall(Proto, "cil", "CIL Protocol")

if not status or cil_proto == nil then
    -- message("CIL Base Protocol already exists... Using the existing dissector.")
    return
end

if not pcall(require, "zmtp-dissector") then
    report_failure("ZMTP protocol was not found. To use the CIL dissector, please install the ZMTP dissector!")
    return
end

-- Add a global variable for registered versions, since DissectorTable is not enumerable
_G["_CIL_VERSION_LIST_"] = {}

local zmtp_proto = Dissector.get("zmtp")
local f_data = Field.new("zmtp.frame.data")

local dissector_table = DissectorTable.new("cil.version", "Registered CIL Versions", ftypes.STRING)

local cil_version_table = {}
local current_cil_version = ""

local current_ports = {}
current_ports.SERVER = nil
current_ports.CLIENT = nil
current_ports.PEER = nil

local function update_protocol_used()
    local new_cil_version = cil_version_table[cil_proto.prefs.version][2]
    
    if new_cil_version == "latest" then
        -- find the latest protocol version
        local max_version_string = ""
        for k,v in pairs(cil_version_table) do
            local version_string = v[2]
            if k > 1 and version_string > max_version_string then
                max_version_string = v[2]
            end
        end
        
        new_cil_version = max_version_string
    end
    
    -- info("CIL version "..new_cil_version.." was selected")
    
    current_cil_version = new_cil_version
end

--
-- Register protocol with the specified TCP ports
--
local function update_ports_used()
    tcp_table = DissectorTable.get("tcp.port")

    if current_ports.SERVER ~= nil then
        tcp_table:remove(current_ports.SERVER,cil_proto)
    end
    
    if current_ports.CLIENT ~= nil then
        tcp_table:remove(current_ports.CLIENT,cil_proto)
    end
    
    if current_ports.PEER ~= nil then
        tcp_table:remove(current_ports.PEER,cil_proto)
    end

    tcp_table:add(cil_proto.prefs.server_port,cil_proto)
    tcp_table:add(cil_proto.prefs.client_port,cil_proto)
    tcp_table:add(cil_proto.prefs.peer_port,cil_proto)

    current_ports.SERVER = cil_proto.prefs.server_port
    current_ports.CLIENT = cil_proto.prefs.client_port
    current_ports.PEER = cil_proto.prefs.peer_port
end

local function setup_preference_table()
    cil_version_table = {}
    cil_version_table[1] = { 1, "latest", 1 }
    for k,v in pairs(_G["_CIL_VERSION_LIST_"]) do
        table.insert(cil_version_table, {k+1, v, k+1})
    end
    
    cil_proto.prefs.version = Pref.enum(
        "CIL Version",
        1,
        "Select a specific CIL version to use, or latest to use the most recent",
        cil_version_table,
        false
    )
    
    cil_proto.prefs.server_port = Pref.uint(
        "Server Port",
        DEFAULT_SERVER_PORT,
        "Select a port use for filtering messages sent to a server"
    )
    
    cil_proto.prefs.client_port = Pref.uint(
        "Client Port",
        DEFAULT_CLIENT_PORT,
        "Select a port use for filtering messages sent to a client"
    )
    
    cil_proto.prefs.peer_port = Pref.uint(
        "Peer Port",
        DEFAULT_PEER_PORT,
        "Select a port use for filtering messages sent to a peer"
    )
    
    update_protocol_used()
    update_ports_used()
end

function cil_proto.init()
    pcall(setup_preference_table)
end

function cil_proto.prefs_changed()
    update_protocol_used()
    update_ports_used()
end

function cil_proto.dissector(buffer,pinfo,tree)
    zmtp_proto:call(buffer,pinfo,tree)
    
    if f_data() then
        local cil_tree = tree:add(cil_proto,buffer)
    
        if pinfo.dst_port == current_ports.SERVER then
            dissector_table:try(current_cil_version..".server",buffer,pinfo,tree)
        elseif pinfo.dst_port == current_ports.CLIENT then
            dissector_table:try(current_cil_version..".client",buffer,pinfo,tree)
        elseif pinfo.dst_port == current_ports.PEER then
            dissector_table:try(current_cil_version..".peer",buffer,pinfo,tree)
        end
    end
end
