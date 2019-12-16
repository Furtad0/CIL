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

%module cil_parser
%{
#include "cil_parser.h"
%}

%include <std_string.i>
%include <std_vector.i>
%include "bytearray.i"

%include "cil_parser.h"

/*
 * Expose vector templates
 */
%template(StringVector) std::vector<std::string>;
%template(FieldInfoVector) std::vector<FieldInfo>;
%template(FieldTreeNodeVector) std::vector<FieldTreeNode>;

/*
 * Expose functions for generating a FieldInfoVector
 */
%template(GetTalkToServerFieldInfo) GetMessageFieldInfo<sc2::reg::TalkToServer>;
%template(GetTellClientFieldInfo) GetMessageFieldInfo<sc2::reg::TellClient>;
%template(GetCilMessageFieldInfo) GetMessageFieldInfo<sc2::cil::CilMessage>;

/*
 * Expose functions for decoding a CIL message to JSON
 */
%template(TalkToServerDecodeJSON) DecodeAsJSON<sc2::reg::TalkToServer>;
%template(TellClientDecodeJSON) DecodeAsJSON<sc2::reg::TellClient>;
%template(CilMessageDecodeJSON) DecodeAsJSON<sc2::cil::CilMessage>;

/*
 * Expose functions for decoding a CIL message to a FieldTreeNodeVector
 */
%template(TalkToServerDecodeValues) DecodeFieldValues<sc2::reg::TalkToServer>;
%template(TellClientDecodeValues) DecodeFieldValues<sc2::reg::TellClient>;
%template(CilMessageDecodeValues) DecodeFieldValues<sc2::cil::CilMessage>;