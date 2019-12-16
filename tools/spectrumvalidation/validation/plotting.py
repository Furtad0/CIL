# MIT License
#
# Copyright (c) 2019 DARPA
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

import matplotlib.pyplot as plt


def plot_gdf(gdf, fig_width, fig_height, xlim, ylim, **kwargs):
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    gdf.plot(ax=ax, **kwargs)
    ax.set_aspect('auto')
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)

    return ax


def overlay_gdfs(gdfs, colors, alphas, fig_width, fig_height, xlim, ylim,  **kwargs):
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    for gdf, color, alpha in zip(gdfs, colors, alphas):
        gdf.plot(ax=ax, fc=color, alpha=alpha, **kwargs)
    ax.set_aspect('auto')
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)