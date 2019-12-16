#!/usr/bin/env python
# MIT License
#
# Copyright (c) 2019 Miklos Maroti
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

from __future__ import print_function, division
from collections import namedtuple
import math
import numpy as np
from shapely.geometry import box, Polygon

SpectrumVoxel = namedtuple(
    'Voxel', ['time_start', 'time_stop', 'freq_start', 'freq_stop', 'duty_cycle'])


def get_voxels_bounds(voxels):
    time_start = float("inf")
    time_stop = float("-inf")
    freq_start = float("inf")
    freq_stop = float("-inf")
    for voxel in voxels:
        time_start = min(time_start, voxel.time_start)
        time_stop = max(time_stop, voxel.time_stop)
        freq_start = min(freq_start, voxel.freq_start)
        freq_stop = max(freq_stop, voxel.freq_stop)
    return time_start, time_stop, freq_start, freq_stop


# Shapely data containing polygons or multipolygons
SpectrumShape = namedtuple('SpectrumShape', ['geometry', 'duty_cycle'])


def get_shapes_bounds(shapes):
    time_start = float("inf")
    time_stop = float("-inf")
    freq_start = float("inf")
    freq_stop = float("-inf")
    for shape in shapes:
        bounds = shape.geometry.bounds
        time_start = min(time_start, bounds[0])
        time_stop = max(time_stop, bounds[2])
        freq_start = min(freq_start, bounds[1])
        freq_stop = max(freq_stop, bounds[3])
    return time_start, time_stop, freq_start, freq_stop


def is_geometry_a_box(geometry):
    """Checks if the given shapely geometry object is a box."""

    good = False
    if geometry.geom_type == "Polygon" and not geometry.interiors and \
            len(geometry.exterior.coords) == 5:
        good = True
        bounds = geometry.bounds
        for coord in geometry.exterior.coords:
            good = good and (coord[0] == bounds[0] or coord[0] == bounds[2])
            good = good and (coord[1] == bounds[1] or coord[1] == bounds[3])

    return good


class SpectrumGrid(object):

    """
    The spectrum grid class represends a rectangular grid in frequency
    and time containing for each cell a value (which can be either energy or
    duty cycle). It allow you to reshape this and truncate grid while 
    properly maintain this value using averaging or maximums or sums.
    """

    def __init__(self, time_start, time_stop, time_bins, freq_start, freq_stop, freq_bins,
                 data=None):
        """Creates a rectangular spectrum grid with the given parameters."""

        assert time_start < time_stop and time_bins > 0
        assert freq_start < freq_stop and freq_bins > 0

        self.time_start = float(time_start)
        self.time_stop = float(time_stop)
        self.time_bins = int(time_bins)
        self.time_step = (self.time_stop - self.time_start) / self.time_bins

        self.freq_start = float(freq_start)
        self.freq_stop = float(freq_stop)
        self.freq_bins = int(freq_bins)
        self.freq_step = (self.freq_stop - self.freq_start) / self.freq_bins

        shape = (self.time_bins, self.freq_bins)

        if data is not None:
            assert data.shape == shape
            self.data = data
        else:
            self.data = np.zeros(shape, dtype=np.float32)

    def __repr__(self):
        return "spectrum {s.time_bins}x{s.freq_bins} from {s.time_start} to {s.time_stop}".format(
            s=self)

    @staticmethod
    def resample_axis_maximum(axis, old_data, old_start, old_stop, new_start, new_stop, new_bins):
        """For each new cell we find all overlapping old cells and take the maximum value
        from those."""

        old_bins = old_data.shape[axis]
        assert old_start <= new_start < new_stop <= old_stop
        assert old_bins > 0 and new_bins > 0
        if old_start == new_start and old_stop == new_stop and old_bins == new_bins:
            return old_data

        old_shape = old_data.shape
        new_shape = list(old_shape)
        new_shape[axis] = new_bins

        new_data = np.empty(new_shape, dtype=np.float32)

        old_step = (old_stop - old_start) / old_bins
        new_step = (new_stop - new_start) / new_bins

        old_index = [slice(None)] * len(old_shape)
        new_index = [slice(None)] * len(new_shape)

        for idx in range(new_bins):
            x = (new_start + idx * new_step - old_start) / old_step
            y = (new_start + (idx + 1) * new_step - old_start) / old_step
            a = max(int(math.floor(x)), 0)
            b = min(int(math.ceil(y)), old_bins)
            assert 0 <= a < b <= old_bins

            old_index[axis] = slice(a, b)
            new_index[axis] = slice(idx, idx+1)
            new_data[tuple(new_index)] = np.amax(
                old_data[tuple(old_index)], axis=axis, keepdims=True)

        return new_data

    @staticmethod
    def resample_axis_average(axis, old_data, old_start, old_stop, new_start, new_stop, new_bins):
        """For each new cell we find all overlapping old cells and take the proportional value
        from each."""

        old_bins = old_data.shape[axis]
        assert old_start <= new_start < new_stop <= old_stop
        assert old_bins > 0 and new_bins > 0
        if old_start == new_start and old_stop == new_stop and old_bins == new_bins:
            return old_data

        old_shape = old_data.shape
        new_shape = list(old_shape)
        new_shape[axis] = new_bins

        new_data = np.empty(new_shape, dtype=np.float32)

        old_step = (old_stop - old_start) / old_bins
        new_step = (new_stop - new_start) / new_bins

        old_index = [slice(None)] * len(old_shape)
        new_index = [slice(None)] * len(new_shape)

        for idx in range(new_bins):
            x = (new_start + idx * new_step - old_start) / old_step
            y = (new_start + (idx + 1) * new_step - old_start) / old_step
            a = max(int(math.floor(x)), 0)
            b = min(int(math.ceil(y)), old_bins)
            assert 0 <= a < b <= old_bins

            if a + 1 >= b:
                old_index[axis] = a
                new_index[axis] = idx
                new_data[tuple(new_index)] = old_data[tuple(old_index)]
            else:
                old_index[axis] = slice(a, a + 1)
                old_data1 = old_data[tuple(old_index)]
                old_index[axis] = slice(a + 1, b - 1)
                old_data2 = old_data[tuple(old_index)]
                old_index[axis] = slice(b - 1, b)
                old_data3 = old_data[tuple(old_index)]

                new_index[axis] = slice(idx, idx + 1)
                new_data[tuple(new_index)] = (
                    (a + 1 - x) * old_data1 +
                    np.sum(old_data2, axis=axis, keepdims=True) +
                    (y - (b - 1)) * old_data3) / (y - x)

        return new_data

    def resample(self, time_start, time_stop, time_bins, freq_start, freq_stop, freq_bins,
                 take_max=False):
        """Resamples this spectrum grid to the shape provided in the arguments
        where the values are either proportionally averaged or maxed together."""

        assert self.time_start <= time_start < time_stop <= self.time_stop
        assert self.freq_start <= freq_start < freq_stop <= self.freq_stop
        assert time_bins > 0 and freq_bins > 0

        data = self.data
        if take_max:
            data = SpectrumGrid.resample_axis_maximum(
                0, data, self.time_start, self.time_stop, time_start, time_stop, time_bins)
            data = SpectrumGrid.resample_axis_maximum(
                1, data, self.freq_start, self.freq_stop, freq_start, freq_stop, freq_bins)
        else:
            data = SpectrumGrid.resample_axis_average(
                0, data, self.time_start, self.time_stop, time_start, time_stop, time_bins)
            data = SpectrumGrid.resample_axis_average(
                1, data, self.freq_start, self.freq_stop, freq_start, freq_stop, freq_bins)

        return SpectrumGrid(time_start, time_stop, time_bins, freq_start, freq_stop, freq_bins,
                            data)

    def crop(self, time_start_bin, time_stop_bin, freq_start_bin, freq_stop_bin):
        """Cuts out a rectangular region aliged at grid boundaries without resampling"""

        assert 0 <= time_start_bin < time_stop_bin <= self.time_bins
        assert 0 <= freq_start_bin < freq_stop_bin <= self.freq_bins

        time_start = self.time_start + time_start_bin * self.time_step
        time_stop = self.time_start + time_stop_bin * self.time_step
        time_bins = time_stop_bin - time_start_bin

        freq_start = self.freq_start + freq_start_bin * self.freq_step
        freq_stop = self.freq_start + freq_stop_bin * self.freq_step
        freq_bins = freq_stop_bin - freq_start_bin

        return SpectrumGrid(time_start, time_stop, time_bins, freq_start, freq_stop, freq_bins,
                            self.data[time_start_bin:time_stop_bin,
                                      freq_start_bin:freq_stop_bin])

    def threshold(self, threshold):
        """applies the threshold function to the data."""

        return SpectrumGrid(self.time_start, self.time_stop, self.time_bins,
                            self.freq_start, self.freq_stop, self.freq_bins,
                            self.data >= threshold)

    def combine(self, grid, take_max=False):
        """Takes this grid and another one with the exact same shape and combines them
        into a new grid where the values added or maxed together."""

        assert self.time_start == grid.time_start and self.time_stop == grid.time_stop
        assert self.freq_start == grid.freq_start and self.freq_stop == grid.freq_stop
        assert self.time_bins == grid.time_bins and self.freq_bins == grid.freq_bins

        if take_max:
            data = np.maximum(self.data, grid.data)
        else:
            data = self.data + grid.data

        return SpectrumGrid(self.time_start, self.time_stop, self.time_bins,
                            self.freq_start, self.freq_stop, self.freq_bins,
                            data)

    def add_voxel(self, voxel, take_max=False):
        """Takes a rectangular voxel and adds it to the current grid where the
        values are added or maxed together."""

        assert voxel.time_start <= voxel.time_stop and voxel.freq_start <= voxel.freq_stop
        time_start = min(
            max(voxel.time_start, self.time_start), self.time_stop)
        time_stop = min(max(voxel.time_stop, self.time_start), self.time_stop)
        freq_start = min(
            max(voxel.freq_start, self.freq_start), self.freq_stop)
        freq_stop = min(max(voxel.freq_stop, self.freq_start), self.freq_stop)
        if time_start == time_stop or freq_start == freq_stop:
            return

        time_x = (time_start - self.time_start) / self.time_step
        time_y = (time_stop - self.time_start) / self.time_step
        time_a = max(int(math.floor(time_x)), 0)
        time_b = min(int(math.ceil(time_y)), self.time_bins)
        assert 0 <= time_a < time_b <= self.time_bins

        freq_x = (freq_start - self.freq_start) / self.freq_step
        freq_y = (freq_stop - self.freq_start) / self.freq_step
        freq_a = max(int(math.floor(freq_x)), 0)
        freq_b = min(int(math.ceil(freq_y)), self.freq_bins)
        assert 0 <= freq_a < freq_b <= self.freq_bins

        if take_max:
            # avoid spilling maximums to neighboring cells if there is only 1% overlap
            index = (
                slice(time_a + (1 if time_x - time_a > 0.99 else 0),
                      time_b - (1 if time_b - time_y > 0.99 else 0)),
                slice(freq_a + (1 if freq_x - freq_a > 0.99 else 0),
                      freq_b - (1 if freq_b - freq_y > 0.99 else 0))
            )
            self.data[index] = np.average(
                self.data[index], voxel.duty_cycle)
        else:
            time_mul = np.zeros([self.time_bins, 1], dtype=np.float32)
            if time_a + 1 >= time_b:
                time_mul[time_a, 0] = time_y - time_x
            else:
                time_mul[time_a, 0] = (time_a + 1 - time_x)
                time_mul[time_a + 1: time_b - 1, 0] = 1
                time_mul[time_b - 1, 0] = time_y - (time_b - 1)

            freq_mul = np.zeros([1, self.freq_bins], dtype=np.float32)
            if freq_a + 1 >= freq_b:
                freq_mul[0, freq_a] = freq_y - freq_x
            else:
                freq_mul[0, freq_a] = (freq_a + 1 - freq_x)
                freq_mul[0, freq_a + 1: freq_b - 1] = 1
                freq_mul[0, freq_b - 1] = freq_y - (freq_b - 1)

            self.data += time_mul * freq_mul * voxel.duty_cycle

    def add_shape(self, shape, take_max=False):
        """Takes a voxel shape and adds it to the current grid  where the
        values are added or maxed together."""

        geometry = shape.geometry
        time_start = geometry.bounds[0]
        time_stop = geometry.bounds[2]
        freq_start = geometry.bounds[1]
        freq_stop = geometry.bounds[3]
        duty_cycle = shape.duty_cycle

        # detect rectangular voxels, the majority of cases
        if is_geometry_a_box(geometry):
            self.add_voxel(SpectrumVoxel(
                time_start, time_stop, freq_start, freq_stop, duty_cycle))
            return

        assert time_start <= time_stop and freq_start <= freq_stop
        time_start = min(max(time_start, self.time_start), self.time_stop)
        time_stop = min(max(time_stop, self.time_start), self.time_stop)
        freq_start = min(max(freq_start, self.freq_start), self.freq_stop)
        freq_stop = min(max(freq_stop, self.freq_start), self.freq_stop)
        if time_start == time_stop or freq_start == freq_stop:
            return

        # very slow, but works, go through all cells and take the intersection
        time_x = (time_start - self.time_start) / self.time_step
        time_y = (time_stop - self.time_start) / self.time_step
        time_a = max(int(math.floor(time_x)), 0)
        time_b = min(int(math.ceil(time_y)), self.time_bins)
        assert 0 <= time_a < time_b <= self.time_bins

        freq_x = (freq_start - self.freq_start) / self.freq_step
        freq_y = (freq_stop - self.freq_start) / self.freq_step
        freq_a = max(int(math.floor(freq_x)), 0)
        freq_b = min(int(math.ceil(freq_y)), self.freq_bins)
        assert 0 <= freq_a < freq_b <= self.freq_bins

        multiplier = duty_cycle / (self.time_step * self.freq_step)
        for time_i in range(time_a, time_b):
            cell_time1 = self.time_start + time_i * self.time_step
            cell_time2 = cell_time1 + self.time_step

            for freq_i in range(freq_a, freq_b):
                cell_freq1 = self.freq_start + freq_i * self.freq_step
                cell_freq2 = cell_freq1 + self.freq_step

                cell = box(cell_time1, cell_freq1, cell_time2, cell_freq2)
                area = cell.intersection(geometry).area

                if area > 0.0:
                    if take_max:
                        self.data[time_i, freq_i] = max(
                            self.data[time_i, freq_i], duty_cycle)
                    else:
                        self.data[time_i, freq_i] += area * multiplier

    def plot_on_axes(self, ax, clim=None, cbar=True):
        """Helper function to plot spectrogram grid to a figure axes."""

        import matplotlib.pyplot as plt

        img = ax.imshow(self.data.transpose(), aspect='auto', clim=clim,
                        extent=(self.time_start, self.time_stop, self.freq_stop, self.freq_start))
        ax.set_xlabel('Time [s]')
        ax.set_ylabel('Freq [Hz]')
        if cbar:
            plt.colorbar(img, ax=ax)

    def plot_grid_lines(self, ax, line_time_ref, line_time_step, line_freq_ref, line_freq_step):
        """Plots grid lines on the given figure axis."""

        assert line_time_step > 0
        if line_time_step / self.time_step >= 20:
            offset = math.fmod(line_time_ref - self.time_start, line_time_step)
            if offset < 0:
                offset += line_time_step

            xpos = self.time_start + offset
            while xpos <= self.time_stop:
                ax.axvline(x=xpos, alpha=0.5, color='grey', linewidth=1)
                xpos += line_time_step

        assert line_freq_step > 0
        if line_freq_step / self.freq_step >= 20:
            offset = math.fmod(line_freq_ref - self.freq_start, line_freq_step)
            if offset < 0:
                offset += line_freq_step

            ypos = self.freq_start + offset
            while ypos <= self.freq_stop:
                ax.axhline(y=ypos, alpha=0.5, color='grey', linewidth=1)
                ypos += line_freq_step

    def plot_message_times(self, ax, message_times):
        """Plots vertical lines indicating when messages were received."""

        for time in message_times:
            if self.time_start <= time <= self.time_stop:
                ax.axvline(x=time, alpha=0.5, color='red',
                           linewidth=1, linestyle='--')

    def plot_figure(self, time_start=None, time_stop=None, time_pixels=1024,
                    freq_start=None, freq_stop=None, freq_pixels=512,
                    title=None, png_file=None, message_times=None):
        """Plots this spectrogram grid."""

        import matplotlib.pyplot as plt

        time_start = time_start or self.time_start
        time_stop = time_stop or self.time_stop
        freq_start = freq_start or self.freq_start
        freq_stop = freq_stop or self.freq_stop
        title = title or "Spectrogram grid"

        grid_max = self.resample(time_start, time_stop, time_pixels,
                                 freq_start, freq_stop, freq_pixels, take_max=True)
        grid_avg = self.resample(time_start, time_stop, time_pixels,
                                 freq_start, freq_stop, freq_pixels, take_max=False)

        fig, axs = plt.subplots(2, 1, figsize=(12, 10))
        grid_max.plot_on_axes(axs[0])
        grid_avg.plot_on_axes(axs[1])

        grid_max.plot_grid_lines(axs[0], self.time_start, self.time_step,
                                 self.freq_start, self.freq_step)
        grid_avg.plot_grid_lines(axs[1], self.time_start, self.time_step,
                                 self.freq_start, self.freq_step)

        if message_times:
            grid_max.plot_message_times(axs[0], message_times)
            grid_avg.plot_message_times(axs[1], message_times)

        axs[0].set_title(title + " maximum")
        axs[1].set_title(title + " average")
        fig.tight_layout(h_pad=4)

        if png_file is None:
            plt.show()
        else:
            import logging
            logging.info('Saving to %s', png_file)
            fig.savefig(png_file, dpi=150)


def spectrum_grid_test1():
    grid = SpectrumGrid(0, 10, 10, 0, 10, 10)
    grid.add_voxel(SpectrumVoxel(2.1, 5.1, 1.5, 5.5, 1))
    grid.add_voxel(SpectrumVoxel(6, 7, 7, 8, 1))
    grid.add_voxel(SpectrumVoxel(7.1, 7.2, 8.1, 9.2, 1))
    print(grid.data)
    grid.plot_figure(time_start=0.3, freq_start=0.3)


def spectrum_grid_test2():
    grid = SpectrumGrid(0, 10, 10, 0, 10, 10)
    grid.add_voxel(SpectrumVoxel(2, 8, 2, 8, 1))
    grid.plot_figure()

    grid = grid.resample(1, 9, 10, 0, 10, 10)
    print(grid.data)
    grid.plot_figure()


def spectrum_grid_test3():
    grid = SpectrumGrid(0, 10, 100, 10, 20, 100)
    grid.add_shape(SpectrumShape(Polygon([(1, 11), (5, 18), (7, 15)]), 1))
    grid.add_shape(SpectrumShape(
        Polygon([(2, 14), (2, 19), (4, 19), (4, 14)]), 1))
    grid.add_shape(SpectrumShape(
        Polygon([(8, 14), (8.1, 19), (6, 19), (6, 14)]), 1))
    grid.plot_figure()


if __name__ == '__main__':
    spectrum_grid_test3()
