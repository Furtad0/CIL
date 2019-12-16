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

local CIL_VERSION = "[[@CIL_VERSION@]]"

local CIL_PROTO_NAME = "cil."..CIL_VERSION
local CIL_PROTO_DESC = "CIL "..CIL_VERSION.." Protocol"

local CIL_SERVER_PROTO_NAME = CIL_PROTO_NAME..".talk_to_server"
local CIL_CLIENT_PROTO_NAME = CIL_PROTO_NAME..".tell_client"
local CIL_PEER_PROTO_NAME = CIL_PROTO_NAME..".cil_message"

local CIL_SERVER_PROTO_DESC = "CIL "..CIL_VERSION.." TalkToServer"
local CIL_CLIENT_PROTO_DESC = "CIL "..CIL_VERSION.." TellClient"
local CIL_PEER_PROTO_DESC = "CIL "..CIL_VERSION.." CilMessage"

-- Load the shared library which wraps the CIL protobufs
local self_path = persconffile_path("plugins/cil-dissector/"..CIL_VERSION.."/")
local cil_base_path = persconffile_path("plugins/cil-base/")
package.cpath = package.cpath .. ";" .. self_path .. "?.so"
package.path = package.path .. ";" .. cil_base_path .. "?.lua"

if not pcall(require, "cil-base") then
    report_failure("CIL base protocol was not found. To use the "..CIL_PROTO_DESC.." dissector, please install the CIL base dissector!")
    return
end

local cil_parser = require("cil_parser")

cil_proto = Proto(CIL_PROTO_NAME, CIL_PROTO_DESC)
cil_server_proto = Proto(CIL_SERVER_PROTO_NAME,CIL_SERVER_PROTO_DESC)
cil_client_proto = Proto(CIL_CLIENT_PROTO_NAME,CIL_CLIENT_PROTO_DESC)
cil_peer_proto = Proto(CIL_PEER_PROTO_NAME,CIL_PEER_PROTO_DESC)

local f_data = Field.new("zmtp.frame.data")

local protocol_info = {}

--
-- Field parsers for converting a string to a value type
--
local function dummy_parser(x)
    return x
end

local function uint64_parser(x)
    local remove_quotes = string.gsub(x, '"([%d%.]*)"', "%1")
    return UInt64(remove_quotes)
end

local function int64_parser(x)
    local remove_quotes = string.gsub(x, '"([%d%.]*)"', "%1")
    return Int64(remove_quotes)
end

local function bool_parser(x)
    if x:lower() == "true" then
        return true
    else
        return false
    end
end

--
-- Map between a protobufs FieldDescriptor::cpp_type_name and
-- a corresponding Wireshark field type, and a parser function
-- to convert a string to a value which is compatible with
-- that field type.
--
local type_lookup = {}
type_lookup["message"] = { ftypes.STRING, dummy_parser }
type_lookup["string"] = { ftypes.STRING, dummy_parser }
type_lookup["enum"] = { ftypes.STRING, dummy_parser }
type_lookup["int32"] = { ftypes.INT32, tonumber }
type_lookup["int64"] = { ftypes.INT64, int64_parser }
type_lookup["uint32"] = { ftypes.UINT32, tonumber }
type_lookup["uint64"] = { ftypes.UINT64, uint64_parser }
type_lookup["double"] = { ftypes.DOUBLE, tonumber }
type_lookup["float"] = { ftypes.DOUBLE, tonumber }
type_lookup["bool"] = { ftypes.BOOLEAN, bool_parser }

local function add_field_info(protocol_name, protocol, field_info)
    for i = 0, field_info:size() - 1 do
        local field_name = field_info[i].name
        local field_path = field_info[i].path
        local field_type = field_info[i].type
        local field_repeated = field_info[i].repeated
        local full_path = string.format("%s.%s", protocol_name, field_path)
        
        local pf_type = ftypes.STRING
        if type_lookup[field_type] ~= nil then
            pf_type = type_lookup[field_type][1]
        end
        
        protocol.fields[full_path] = ProtoField.new(field_name, full_path, pf_type)
    end
end

--
-- Init a subprotocol
--
-- protocol_name: name of the protocol as a string
-- protocol: Proto object
-- field_info: FieldInfoVector describing the message fields
--
local function init_proto(protocol_name, protocol, field_info)
    protocol_info[protocol_name] = {}
    protocol_info[protocol_name].protocol = protocol

    protocol.fields = {}
    protocol.fields["message"] = ProtoField.new("message", string.format("%s.message", protocol_name), ftypes.STRING)
    
    add_field_info(protocol_name, protocol, field_info)
end

--
-- Register lists of message fields, extracted from the protobufs
--
init_proto(CIL_SERVER_PROTO_NAME, cil_server_proto, cil_parser.GetTalkToServerFieldInfo())
init_proto(CIL_CLIENT_PROTO_NAME, cil_client_proto, cil_parser.GetTellClientFieldInfo())
init_proto(CIL_PEER_PROTO_NAME, cil_peer_proto, cil_parser.GetCilMessageFieldInfo())

--
-- Helper function to convert a variadic return value to an array
--
local function get_all_values (...)
    return { select(1,...) }
end

--
-- Generate a dissection tree for a message with field names
-- and values. 
--
-- parser: function to generate a FieldTreeNodeVector from a Wireshark ByteArray
-- tree: parent TreeItem
-- protocol_name: protocol_name as a string
-- data: TvbRange covering the packet
--
local function dissect_message(parser, tree, protocol_name, data)
    local data_bytearray = data:bytes()
    
    local protocol = protocol_info[protocol_name].protocol
    local parsed = parser(data_bytearray)
    
    local subtrees = {}
    
    for i = 0, parsed:size()-1 do
        local id = parsed[i].id
        local parent_id = parsed[i].parent_id
        local value = parsed[i].value
        local value_type = parsed[i].type
        local full_path
        
        if parsed[i].path ~= "" then
            full_path = string.format("%s.%s", protocol_name, parsed[i].path)
        else
            full_path = "message"
        end
        
        local field = protocol.fields[full_path]
        local parent_tree
        
        if parsed[i].parent_id >= 0 then
            parent_tree = subtrees[parent_id]
        else
            parent_tree = tree
        end
        
        local value_parser = dummy_parser
        if type_lookup[value_type] ~= nil then
            value_parser = type_lookup[value_type][2]
        end
        
        subtrees[id] = parent_tree:add(field,data(),value_parser(value))
    end
end

--
-- Dissector for the cil server (TalkToServer) protocol
--
function cil_server_proto.dissector(buffer,pinfo,tree)
    if f_data() then
        local payloads = get_all_values(f_data())
        pinfo.cols.protocol = "REG"
        local cil_tree = tree:add(cil_proto,buffer)
        
        for i = 1, #payloads do
            local payload_data = payloads[i].range()
            local subtree = cil_tree:add(cil_server_proto,payload_data())
            
            dissect_message(cil_parser.TalkToServerDecodeValues, subtree, CIL_SERVER_PROTO_NAME, payload_data())
        end
    end
end

--
-- Dissector for the cil client (TellClient) protocol
--
function cil_client_proto.dissector(buffer,pinfo,tree)
    if f_data() then
        local payloads = get_all_values(f_data())
        pinfo.cols.protocol = "REG"
        local cil_tree = tree:add(cil_proto,buffer)
        
        for i = 1, #payloads do
            local payload_data = payloads[i].range()
            local subtree = cil_tree:add(cil_client_proto,payload_data())

            dissect_message(cil_parser.TellClientDecodeValues, subtree, CIL_CLIENT_PROTO_NAME, payload_data())
        end
    end
end

--
-- Dissector for the cil peer (CilMessage) protocol
--
function cil_peer_proto.dissector(buffer,pinfo,tree)
    if f_data() then
        local payloads = get_all_values(f_data())
        pinfo.cols.protocol = "CIL"
        local cil_tree = tree:add(cil_proto,buffer)
        
        for i = 1, #payloads do
            local payload_data = payloads[i].range()
            local subtree = cil_tree:add(cil_peer_proto,payload_data())
            
            dissect_message(cil_parser.CilMessageDecodeValues, subtree, CIL_PEER_PROTO_NAME, payload_data())
        end
    end
end

-- Register protocol version as a target for CIL messages
local cil_table = DissectorTable.get("cil.version")
cil_table:add(CIL_VERSION..".server", cil_server_proto)
cil_table:add(CIL_VERSION..".client", cil_client_proto)
cil_table:add(CIL_VERSION..".peer", cil_peer_proto)

table.insert(_G["_CIL_VERSION_LIST_"], CIL_VERSION)
