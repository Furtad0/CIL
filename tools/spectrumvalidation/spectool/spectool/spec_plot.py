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
import logging
import math
from os import path
import numpy as np

from .reservation_reader import ReservationReader
from .observer_reader import ObserverReader
from .usage_reader import UsageReader
from .spectrum_grid import SpectrumGrid
from .geodata_reader import GeodataReader
from .predictor import predict_the_future


class SpecPlot(object):

    """
    Creates plots of various kind.
    """

    def __init__(self, reservation, observer_dir, gateway_pcap, threshold,
                 training_len, training_lag, training_rate, train_time_step, train_freq_bins,
                 gdf_dir=None, gdf_start_time=0):
        self.log = logging.getLogger('spec_plot')
        self.reservation = reservation
        self.observer_dir = observer_dir
        self.gateway_pcap = gateway_pcap
        self.threshold = threshold

        # training parameters in seconds
        self.training_len = training_len
        self.training_lag = training_lag
        self.training_rate = training_rate
        self.train_time_step = train_time_step
        self.train_freq_bins = train_freq_bins
        assert 0 < training_lag < training_len and 0 < training_rate

        # geoframe data
        self.gdf_dir = gdf_dir
        self.gdf_start_time = gdf_start_time
        self.gdf_shapes = {}

        self.observer_config = None
        self.observer_grid = None

        self.time_start = None
        self.time_stop = None
        self.time_bins = None
        self.freq_start = None
        self.freq_stop = None
        self.freq_bins = None

        self.gateway_stats = None
        self.measured_past_voxels = []    # real measurement
        self.measured_future_voxels = []  # invalid reports
        self.forecast_past_voxels = []    # invalid or stale
        self.forecast_future_voxels = []  # real prediction
        self.message_times = []

        self.modes = [None, None]
        self.grids = [None, None]

    def read_all(self, gateway_srn=None, incumbent_srn=None):
        reader = ObserverReader(self.observer_dir)
        reader.read_state_change()
        reader.read_configs()
        reader.read_pass_band_rf()
        self.observer_config = reader.config
        self.observer_grid = reader.grid

        reader = UsageReader(self.gateway_pcap, gateway_srn, incumbent_srn)
        reader.read_messages()
        self.gateway_stats = reader.stats
        self.measured_past_voxels = reader.measured_past_voxels
        self.measured_future_voxels = reader.measured_future_voxels
        self.forecast_past_voxels = reader.forecast_past_voxels
        self.forecast_future_voxels = reader.forecast_future_voxels
        self.message_times = reader.message_times

    def set_bounds(self, time_start, time_stop, time_bins, time_step,
                   freq_start, freq_stop, freq_bins, freq_step):
        # use the bounds from the observer if not specified
        time_start = time_start or self.observer_grid.time_start
        time_stop = time_stop or self.observer_grid.time_stop

        freq_start = freq_start or self.observer_grid.freq_start
        freq_stop = freq_stop or self.observer_grid.freq_stop

        # make sure that we have proper ranges
        time_start = min(max(time_start, self.observer_grid.time_start),
                         self.observer_grid.time_stop)
        time_stop = min(max(time_stop, self.observer_grid.time_start),
                        self.observer_grid.time_stop)
        freq_start = min(max(freq_start, self.observer_grid.freq_start),
                         self.observer_grid.freq_stop)
        freq_stop = min(max(freq_stop, self.observer_grid.freq_start),
                        self.observer_grid.freq_stop)

        # override bins if step is specified
        if time_step and (time_stop - time_start) > time_step > 0:
            time_stop = time_start + \
                math.floor((time_stop - time_start) / time_step) * time_step
            time_bins = int(round((time_stop - time_start) / time_step))

        if freq_step and (freq_stop - freq_start) > freq_step > 0:
            freq_stop = freq_start + \
                math.floor((freq_stop - freq_start) / freq_step) * freq_step
            freq_bins = int(round((freq_stop - freq_start) / freq_step))

        # align time grid to that of the observer
        bin_start = max(0, int(math.floor(
            (time_start - self.observer_grid.time_start) / self.observer_grid.time_step)))
        bin_stop = min(self.observer_grid.time_bins - 1, int(math.ceil(
            (time_stop - self.observer_grid.time_start) / self.observer_grid.time_step)))
        assert 0 <= bin_start < bin_stop <= self.observer_grid.time_bins
        time_start = self.observer_grid.time_start + \
            bin_start * self.observer_grid.time_step
        time_stop = self.observer_grid.time_start + \
            bin_stop * self.observer_grid.time_step

        # align freq grid to that of the observer
        bin_start = max(0, int(math.floor(
            (freq_start - self.observer_grid.freq_start) / self.observer_grid.freq_step)))
        bin_stop = min(self.observer_grid.freq_bins - 1, int(math.ceil(
            (freq_stop - self.observer_grid.freq_start) / self.observer_grid.freq_step)))
        assert 0 <= bin_start < bin_stop <= self.observer_grid.freq_bins
        freq_start = self.observer_grid.freq_start + \
            bin_start * self.observer_grid.freq_step
        freq_stop = self.observer_grid.freq_start + \
            bin_stop * self.observer_grid.freq_step

        # save everything
        self.time_start = time_start
        self.time_stop = time_stop
        self.time_bins = time_bins
        self.freq_start = freq_start
        self.freq_stop = freq_stop
        self.freq_bins = freq_bins

    def get_gdf_shapes(self, filename):
        if not filename in self.gdf_shapes:
            reader = GeodataReader(filename, self.gdf_start_time)
            shapes = reader.select_shapes()
            self.gdf_shapes[filename] = shapes
            bbox = reader.stats['bbox']
            self.log.info("%s shapes %s time start %s stop %s",
                          filename, len(shapes), bbox[0], bbox[2])

        return self.gdf_shapes[filename]

    def print_parameters(self):
        self.log.info("Observer frame_len %s real_frame_len %s max time error %s obs_nfft %s",
                      self.observer_config['frame_len'], self.observer_config['real_frame_len'],
                      self.observer_config['max_time_error'], self.observer_config['obs_nfft'])
        self.log.info("Time start %s stop %s bins %s",
                      self.time_start, self.time_stop, self.time_bins)
        self.log.info("Freq start %s stop %s bins %s",
                      self.freq_start, self.freq_stop, self.freq_bins)

    def set_grid_to_observer_raw(self, grid_id):
        time_bin_start = int(round((self.time_start - self.observer_grid.time_start) /
                                   self.observer_grid.time_step))
        time_bin_stop = int(round((self.time_stop - self.observer_grid.time_start) /
                                  self.observer_grid.time_step))

        freq_bin_start = int(round((self.freq_start - self.observer_grid.freq_start) /
                                   self.observer_grid.freq_step))
        freq_bin_stop = int(round((self.freq_stop - self.observer_grid.freq_start) /
                                  self.observer_grid.freq_step))

        grid = self.observer_grid.crop(
            time_bin_start, time_bin_stop, freq_bin_start, freq_bin_stop)

        assert grid.time_start == self.time_start
        assert grid.time_stop == self.time_stop
        assert grid.freq_start == self.freq_start
        assert grid.freq_stop == self.freq_stop

        self.grids[grid_id] = grid

    def apply_threshold(self, grid_id):
        self.grids[grid_id] = self.grids[grid_id].threshold(self.threshold)

    def resample_to_bins(self, grid_id):
        self.grids[grid_id] = self.grids[grid_id].resample(
            self.time_start,
            self.time_stop,
            self.time_bins,
            self.freq_start,
            self.freq_stop,
            self.freq_bins)

    def set_grid_to_voxels(self, grid_id, voxels):
        grid = SpectrumGrid(
            self.time_start,
            self.time_stop,
            self.time_bins,
            self.freq_start,
            self.freq_stop,
            self.freq_bins)

        for voxel in voxels:
            grid.add_voxel(voxel)
        self.grids[grid_id] = grid

    def set_grid_to_shapes(self, grid_id, shapes):
        grid = SpectrumGrid(
            self.time_start,
            self.time_stop,
            self.time_bins,
            self.freq_start,
            self.freq_stop,
            self.freq_bins)

        for shape in shapes:
            grid.add_shape(shape)
        self.grids[grid_id] = grid

    def apply_training(self, grid_id):
        train_time_bins = int(
            round((self.time_stop - self.time_start) / self.train_time_step))
        self.log.info("Resampling for training to %s by %s",
                      train_time_bins, self.train_freq_bins)

        grid = self.grids[grid_id]
        grid = grid.resample(
            self.time_start,
            self.time_stop,
            train_time_bins,
            self.freq_start,
            self.freq_stop,
            self.train_freq_bins)

        training_len = int(math.ceil(self.training_len/grid.time_step))
        training_lag = int(math.ceil(self.training_lag/grid.time_step))
        training_rate = int(math.ceil(self.training_rate/grid.time_step))

        self.log.info(
            "Training params len %s secs %s bins, lag %s secs %s bins, rate %s secs %s bins",
            self.training_len, training_len, self.training_lag, training_lag, self.training_rate,
            training_rate)

        grid.data = predict_the_future(
            grid.data, training_len, training_lag, training_rate)
        grid.data = np.minimum(np.maximum(grid.data, 0), 1)

        self.grids[grid_id] = grid

    def calculate_grid(self, grid_id, mode):
        """Calculate a grid according to the give mode."""

        if mode == 'none':
            self.grids[grid_id] = None
        elif mode == 'observer-spec':
            self.set_grid_to_observer_raw(grid_id)
            self.resample_to_bins(grid_id)
        elif mode == 'observer-duty':
            self.set_grid_to_observer_raw(grid_id)
            self.apply_threshold(grid_id)
            self.resample_to_bins(grid_id)
        elif mode == 'observer-pred':
            self.set_grid_to_observer_raw(grid_id)
            self.apply_threshold(grid_id)
            self.apply_training(grid_id)
        elif mode == 'cil-measured-past':
            self.set_grid_to_voxels(grid_id, self.measured_past_voxels)
        elif mode == 'cil-measured-future':
            self.set_grid_to_voxels(grid_id, self.measured_future_voxels)
        elif mode == 'cil-forecast-past':
            self.set_grid_to_voxels(grid_id, self.forecast_past_voxels)
        elif mode == 'cil-forecast-future':
            self.set_grid_to_voxels(
                grid_id, self.forecast_future_voxels)
        elif mode == 'spec-val-tx':
            self.set_grid_to_shapes(
                grid_id, self.get_gdf_shapes('tx_gdf.json'))
        elif mode == 'spec-val-cil':
            self.set_grid_to_shapes(
                grid_id, self.get_gdf_shapes('cil_gdf.json'))
        elif mode == 'spec-val-cil-past':
            self.set_grid_to_shapes(
                grid_id, self.get_gdf_shapes('historical_cil_gdf.json'))
        elif mode == 'spec-val-cil-future':
            self.set_grid_to_shapes(
                grid_id, self.get_gdf_shapes('future_cil_gdf.json'))
        elif mode == 'spec-val-prediction':
            self.set_grid_to_shapes(
                grid_id, self.get_gdf_shapes('prediction_gdf.json'))
        else:
            self.grids[grid_id] = None
            self.log.critical("Unknown mode %s", mode)

    def plot_on_axes(self, ax, grid, title, take_max=False,
                     time_pixels=1024, freq_pixels=512, clim=None):
        """Prepares a full plot of the grid on the given figure axis."""

        grid = grid.resample(grid.time_start, grid.time_stop, time_pixels,
                             grid.freq_start, grid.freq_stop, freq_pixels,
                             take_max=take_max)

        grid.plot_on_axes(ax, clim=clim)

        grid.plot_grid_lines(
            ax,
            self.time_start,
            (self.time_stop - self.time_start) / self.time_bins,
            self.freq_start,
            (self.freq_stop - self.freq_start) / self.freq_bins)

        if self.message_times and self.time_stop - self.time_start < 30:
            grid.plot_message_times(ax, self.message_times)

        ax.set_title(title + ' ' + 'maximum' if take_max else 'average')

    def plot_figure(self, save=False, diff_mode='none'):
        import matplotlib.pyplot as plt

        if self.grids[0] is None or self.grids[1] is None:
            grid_id = 0 if self.grids[0] is not None else 1
            grid = self.grids[grid_id]
            if grid is None:
                self.log.critical("No plot was selected")
                return

            title = self.modes[grid_id].replace('-', ' ')

            clim = (np.amin(grid.data), np.amax(grid.data))

            fig, axs = plt.subplots(2, 1, figsize=(12, 10))
            self.plot_on_axes(axs[0], grid, title, take_max=True, clim=clim)
            self.plot_on_axes(axs[1], grid, title, take_max=False, clim=clim)

        elif diff_mode not in ['on', 'pos', 'neg', 'abs']:
            title0 = self.modes[0].replace('-', ' ')
            title1 = self.modes[1].replace('-', ' ')
            title = title0 + ' vs ' + title1

            cmin = min(np.amin(self.grids[0].data),
                       np.amin(self.grids[1].data))
            cmax = max(np.amax(self.grids[0].data),
                       np.amax(self.grids[1].data))
            clim = (cmin, cmax)

            fig, axs = plt.subplots(2, 2, figsize=(12, 10))
            self.plot_on_axes(
                axs[0][0], self.grids[0], title0, take_max=True, clim=clim)
            self.plot_on_axes(
                axs[1][0], self.grids[0], title0, take_max=False, clim=clim)
            self.plot_on_axes(
                axs[0][1], self.grids[1], title1, take_max=True, clim=clim)
            self.plot_on_axes(
                axs[1][1], self.grids[1], title1, take_max=False, clim=clim)

        else:
            title0 = self.modes[0].replace('-', ' ')
            title1 = self.modes[1].replace('-', ' ')
            title = 'diff-mode ' + diff_mode + ' for ' + title0 + ' vs ' + title1

            g = self.grids[0]
            grid = SpectrumGrid(g.time_start, g.time_stop, g.time_bins,
                                g.freq_start, g.freq_stop, g.freq_bins)
            grid.data = self.grids[0].data - self.grids[1].data

            if diff_mode == 'pos':
                grid.data = np.maximum(0, grid.data)
            elif diff_mode == 'neg':
                grid.data = np.minimum(0, grid.data)
            elif diff_mode == 'abs':
                grid.data = np.absolute(grid.data)

            clim = (np.amin(grid.data), np.amax(grid.data))

            fig, axs = plt.subplots(2, 1, figsize=(12, 10))
            self.plot_on_axes(axs[0], grid, title, take_max=True, clim=clim)
            self.plot_on_axes(axs[1], grid, title, take_max=False, clim=clim)

        fig.suptitle("RESERVATION " + str(self.reservation) +
                     " threshold " + str(self.threshold))
        fig.tight_layout(h_pad=4, rect=[0, 0, 1, 0.95])

        if save:
            png_file = str(self.reservation) + '_' + \
                title.replace(' ', '_') if save else None
            self.log.info('Saving to %s', png_file)
            fig.savefig(png_file, dpi=150)
        else:
            plt.show()


def run(args=None):
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('directory', help="RESERVATION directory")
    parser.add_argument('--observer-srn', type=int,
                        help="override the observer SRN to be used")
    parser.add_argument('--gateway-srn', type=int,
                        help="override the gateway SRN to be used")
    parser.add_argument('--incumbent-srn', type=int,
                        help="override the incumbent SRN to be used")
    parser.add_argument('--gdf-dir', default=None,
                        help="Overrides the directory where the verifier gdfs are saved")
    parser.add_argument('--threshold', type=float, default=-65,
                        help="The duty cycle threshold for the observer in dB")
    parser.add_argument('--training-len', type=float, default=5.0,
                        help="how many seconds of data to use for training")
    parser.add_argument('--training-lag', type=float, default=0.6,
                        help="how many seconds of lag to use for training")
    parser.add_argument('--training-rate', type=float, default=1.0,
                        help="how frequently should we retrain in seconds")
    parser.add_argument('--train-time-step', type=float, default=0.2,
                        help="the time resolution used for training")
    parser.add_argument('--train-freq-bins', type=int, default=64,
                        help="the freq resolution used for training")
    parser.add_argument('--save', action='store_true',
                        help="save the plot instead of displying it")
    parser.add_argument('--time-start', type=float,
                        help="specifies the start time of the plot")
    parser.add_argument('--time-stop', type=float,
                        help="specifies the stop time of the plot")
    parser.add_argument('--time-bins', type=int, default=2048,
                        help="specifies the number of frequency bins")
    parser.add_argument('--time-step', type=float,
                        help="calculates the time bins parameter")
    parser.add_argument('--freq-start', type=float,
                        help="specifies the start freq of the plot")
    parser.add_argument('--freq-stop', type=float,
                        help="specifies the stop freq of the plot")
    parser.add_argument('--freq-bins', type=int, default=512,
                        help="specifies the number of frequency bins")
    parser.add_argument('--freq-step', type=float,
                        help="calculates the freq bins parameter")
    MODES = ['observer-spec', 'observer-duty', 'observer-pred',
             'cil-measured-past', 'cil-measured-future', 'cil-forecast-past',
             'cil-forecast-future', 'spec-val-tx', 'spec-val-cil',
             'spec-val-cil-past', 'spec-val-cil-future', 'spec-val-prediction',
             'none']
    parser.add_argument('--mode1', choices=MODES,
                        default='observer-spec',
                        help="selects a mode for the first plot")
    parser.add_argument('--mode2', choices=MODES,
                        default='none',
                        help="selects a mode for the second plot")
    parser.add_argument('--diff-mode', default='off',
                        choices=['off', 'on', 'pos', 'neg', 'abs'],
                        help="plot the difference between mode1 and mode2")

    args = parser.parse_args(args)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    if args.save:
        import matplotlib
        matplotlib.use('Agg')

    res = ReservationReader(args.directory).read_all()
    res['observer_srn'] = args.observer_srn or res.get('observer_srn')
    res['gateway_srn'] = args.gateway_srn or res.get('gateway_srn')
    res['incumbent_srn'] = args.incumbent_srn or res.get('incumbent_srn')

    observer_dir = path.join(res['directory'],
                             res['nodes'][res['observer_srn']]['logs_dir'])
    gateway_pcap = path.join(res['directory'],
                             res['nodes'][res['gateway_srn']]['pcap_file'])

    plotter = SpecPlot(res['reservation'],
                       observer_dir, gateway_pcap, args.threshold,
                       args.training_len, args.training_lag, args.training_rate,
                       args.train_time_step, args.train_freq_bins,
                       args.gdf_dir or args.directory, res['rf_start_time'])
    plotter.read_all(res['gateway_srn'], res['incumbent_srn'])
    plotter.set_bounds(args.time_start, args.time_stop, args.time_bins, args.time_step,
                       args.freq_start, args.freq_stop, args.freq_bins, args.freq_step)
    plotter.print_parameters()
    plotter.modes[0] = args.mode1
    plotter.modes[1] = args.mode2
    plotter.calculate_grid(0, args.mode1)
    plotter.calculate_grid(1, args.mode2)

    plotter.plot_figure(args.save, diff_mode=args.diff_mode)


if __name__ == "__main__":
    run()
