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
 
#include "cil_parser.h"

#include <sstream>
#include <google/protobuf/text_format.h>

using namespace std;
using namespace google::protobuf;

void GetFieldInfo(const Message& m, vector<FieldInfo>& field_info, const string& prefix) 
{
    const Descriptor * desc = m.GetDescriptor();
    const Reflection * refl = m.GetReflection();
    MessageFactory * factory = refl->GetMessageFactory();
    
    int field_count = desc->field_count();
    for(int i=0; i<field_count; i++)
    {
        const FieldDescriptor * field = desc->field(i);
        
        FieldInfo info;
        info.name = field->name();
        info.path = prefix + field->name();
        info.type = field->cpp_type_name();
        info.repeated = field->is_repeated();
        
        field_info.push_back(info);
        
        if (field->type() == FieldDescriptor::TYPE_MESSAGE)
        {
            std::string new_prefix = info.path + ".";
        
            if (!field->is_repeated()) {
                string new_prefix = info.path + ".";
                const Message &message_field = refl->GetMessage(m, field);
                GetFieldInfo(message_field, field_info, new_prefix);
            }
            else
            {
                string new_prefix = info.path + ".";
                const Descriptor * child_desc = field->message_type();
                const Message * message_field = factory->GetPrototype(child_desc);
                GetFieldInfo(*message_field, field_info, new_prefix);
            }
        }
    }
}

void GetFieldValues(const Message& m, vector<FieldTreeNode>& field_values, const string& prefix, int& id, int parent_id) 
{
    const Descriptor * desc = m.GetDescriptor();
    const Reflection * refl = m.GetReflection();
    
    FieldTreeNode info;
    info.parent_id = parent_id;
    
    // Start off the tree with a JSON representation of the entire message
    if (parent_id < 0)
    {
        info.name = "";
        info.path = prefix;
        info.type = "message";
        info.repeated = false;
        info.id = id++;
        info.value = GetJSON(m);
        
        field_values.push_back(info);
    }
    
    TextFormat::Printer printer;
    printer.SetSingleLineMode(true);
    printer.SetHideUnknownFields(false);
    
    std::vector<const FieldDescriptor *> field_list;
    refl->ListFields(m, &field_list);
    
    int field_count = field_list.size();
    for(int i=0; i<field_count; i++)
    {
        const FieldDescriptor * field = field_list[i];
        
        FieldTreeNode info;
        info.parent_id = parent_id;
        info.name = field->name();
        info.path = prefix + field->name();
        info.type = field->cpp_type_name();
        info.repeated = field->is_repeated();
        
        if (field->is_repeated()) 
        {
            int field_size = refl->FieldSize(m, field);
            for (int index=0; index<field_size; index++) 
            {
                info.id = id++;
                printer.PrintFieldValueToString(m, field, index, &info.value);
                field_values.push_back(info);
                
                if (field->type() == FieldDescriptor::TYPE_MESSAGE)
                {
                    string new_prefix = info.path + ".";
                    const Message &message_field = refl->GetRepeatedMessage(m, field, index);
                    GetFieldValues(message_field, field_values, new_prefix, id, info.id);
                }
            }
        }
        else
        {
            info.id = id++;
            printer.PrintFieldValueToString(m, field, -1, &info.value);
            field_values.push_back(info);
            
            if (field->type() == FieldDescriptor::TYPE_MESSAGE)
            {
                string new_prefix = info.path + ".";
                const Message &message_field = refl->GetMessage(m, field);
                GetFieldValues(message_field, field_values, new_prefix, id, info.id);
            }
        }
    }
}

std::string GetJSON(const google::protobuf::Message& m)
{
    string json_string;
    util::JsonOptions opts;
    opts.preserve_proto_field_names = true;
    util::MessageToJsonString(m, &json_string, opts);
    return json_string;
}
