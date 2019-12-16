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

/*
 * Typemap from a Wireshark ByteArray object to a variable length C array
 */
 
%typemap(in) (unsigned char * data, int len)
%{
    lua_getfield(L, -1, "len");
    lua_pushvalue(L, -2);
    lua_call(L, 1, 1);
    $2 = lua_tonumber(L,-1);
    lua_pop(L, 1);
    
    if (!$2) SWIG_fail;
    
    $1 = new unsigned char[$2];
    
    if (!$1) SWIG_fail;
    
    for (int i=0; i<$2; i++) {
        lua_getfield(L, -1, "get_index");
        lua_pushvalue(L, -2);
        lua_pushinteger(L, i);
        lua_call(L, 2, 1);
        $1[i] = (unsigned char)lua_tonumber(L,-1);
        lua_pop(L, 1);
    }
%}

%typemap(freearg) (unsigned char * data, int len)
%{
    delete [] $1;
%}