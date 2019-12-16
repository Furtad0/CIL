/*
 * MIT License
 *
 * Copyright (c) 2019 Malcolm Stagg
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 * This file is a part of the CIRN Interaction Language.
 */
 
#pragma once
 
#include <google/protobuf/util/json_util.h>
#include <string>
#include <vector>

#include "registration.pb.h"
#include "cil.pb.h"

struct FieldInfo 
{
    std::string name; // Name of the field
    std::string path; // Full path to the field, separated by '.'
    std::string type; // Field type as a string, taken from FieldDescriptor::cpp_type_name
    bool repeated;    // True if the field is repeated
};

struct FieldTreeNode 
{
    int id;            // Unique ID of the field within the current tree
    int parent_id;     // ID of the parent message, or -1 if this is the top-level message
    std::string name;  // Name of the field
    std::string path;  // Full path to the field, separated by '.'
    std::string type;  // Field type as a string, taken from FieldDescriptor::cpp_type_name
    std::string value; // Field value as a string
    bool repeated;     // True if the field is repeated
};

/*
 * Returns field names recursively
 */
void GetFieldInfo(const google::protobuf::Message& m, std::vector<FieldInfo>& field_info, const std::string& prefix = "");

template<class T>
inline std::vector<FieldInfo> GetMessageFieldInfo()
{
    T m;
    std::vector<FieldInfo> field_info;
    GetFieldInfo(m, field_info);
    return field_info;
}

/*
 * Recursively returns a flattened tree of field names, types, and values
 */
void GetFieldValues(const google::protobuf::Message& m, std::vector<FieldTreeNode>& field_values, const std::string& prefix, int& id, int parent_id);

template<class T>
inline std::vector<FieldTreeNode> DecodeFieldValues(unsigned char * data, int len)
{
    T m;
    std::string serialized((const char *)data, len);
    m.ParseFromString(serialized);
    
    int id = 0;
    std::vector<FieldTreeNode> field_values;
    GetFieldValues(m, field_values, "", id, -1);
    
    return field_values;
}


std::string GetJSON(const google::protobuf::Message& m);

/*
 * Deserialize a message to a JSON string
 */
template<class T>
std::string DecodeAsJSON(unsigned char * data, int len)
{
    T m;
    std::string serialized((const char *)data, len);
    m.ParseFromString(serialized);
    return GetJSON(m);
}