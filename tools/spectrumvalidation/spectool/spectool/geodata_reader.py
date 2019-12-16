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
from collections import Counter
import logging
import json
from shapely import geometry, affinity


from .spectrum_grid import SpectrumGrid, SpectrumShape, \
    get_shapes_bounds, is_geometry_a_box
from .reservation_reader import ip_to_srn


class GeodataReader(object):

    """
    This is essentially a copy of the `spec-val` tool. It would be nice to
    refactor that and make it a module so it can be properly imported, but
    maybe later.
    """

    def __init__(self, filename, gdf_start_time=0):
        self.log = logging.getLogger('observer_reader')
        self.filename = filename
        self.gdf_start_time = gdf_start_time

        with open(self.filename, 'r') as f:
            gdf_data = json.load(f)

        src_ips = set()
        dst_ips = set()
        measured_flags = set()
        geom_types = Counter()

        self.features = []
        for feature in gdf_data.get('features', []):

            geom = geometry.shape(feature['geometry'])
            if self.gdf_start_time != 0:
                geom = affinity.translate(geom, xoff=self.gdf_start_time)
                geom = geom.buffer(0)  # fix errors caused by rounding

            if is_geometry_a_box(geom):
                geom_types['Box'] += 1
            else:
                geom_types[geom.geom_type] += 1

            feature2 = {
                'geometry': geom
            }

            properties = feature.get('properties', {})

            if 'src_ip' in properties:
                src_ip = properties['src_ip']
                feature2['src_ip'] = src_ip
                src_ips.add(src_ip)

            if 'dst_ip' in properties:
                dst_ip = properties['dst_ip']
                feature2['dst_ip'] = dst_ip
                dst_ips.add(dst_ip)

            if 'measured_data' in properties:
                measured = properties['measured_data']
                feature2['measured'] = measured
                measured_flags.add(measured)

            if 'duty_cycle' in properties:
                feature2['duty_cycle'] = properties['duty_cycle']

            if 'report_on' in properties:
                feature2['report_on'] = properties['report_on']

            self.features.append(feature2)

        bbox = gdf_data.get('bbox', [0, 0, 0, 0])
        bbox[0] += gdf_start_time
        bbox[2] += gdf_start_time

        self.stats = {
            'filename': self.filename,
            'gdf_start_time': self.gdf_start_time,
            'bbox': bbox,
            'features': len(self.features),
            'src_ips': list(src_ips),
            'dst_ips': list(dst_ips),
            'measured_flags': list(measured_flags),
            'geometry_types': dict(geom_types)
        }

    def select_shapes(self, src_srn=None, dst_srn=None, measured=None):
        """Reads the geodata json file and converts it to a list of shapes.
        The optional fields are all filters. If the values do not match,
        then those voxels will be ignored."""

        shapes = []
        for feature in self.features:
            if src_srn and src_srn != ip_to_srn(feature['src_ip']):
                continue
            if dst_srn and dst_srn != ip_to_srn(feature['dst_ip']):
                continue
            if measured is not None and measured != feature['measured']:
                continue

            geom = feature['geometry']

            # somewhat of a hack
            if 'duty_cycle' in feature:
                duty_cycle = feature['duty_cycle']
            elif 'report_on' in feature:
                duty_cycle = feature['report_on'] / geom.area
            else:
                duty_cycle = 1

            shapes.append(SpectrumShape(geom, duty_cycle))

        return shapes


def run(args=None):
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("filename", help="json file containing geodata")
    parser.add_argument('--src-srn', type=int,
                        help="filter voxels by this source SRN")
    parser.add_argument('--dst-srn', type=int,
                        help="filter voxels by this destionation SRN")
    parser.add_argument('--measured', choices=['none', 'true', 'false'], default='none',
                        help="if not none, then filter voxels by their measured flag")
    parser.add_argument('--gdf-start-time', type=float, default=0,
                        help="sets the gdf time offset")
    parser.add_argument('--save', action='store_true',
                        help="save spectrogram avg/max plots into PNG")
    parser.add_argument('--plot', action='store_true',
                        help="displays spectrogram avg/max plots")
    parser.add_argument('--time-start', type=float,
                        help="specifies the start time of the plot")
    parser.add_argument('--time-stop', type=float,
                        help="specifies the stop time of the plot")
    parser.add_argument('--time-bins', type=int, default=1024,
                        help="specifies the number of frequency bins")
    parser.add_argument('--freq-start', type=float,
                        help="specifies the start freq of the plot")
    parser.add_argument('--freq-stop', type=float,
                        help="specifies the stop freq of the plot")
    parser.add_argument('--freq-bins', type=int, default=512,
                        help="specifies the number of frequency bins")

    args = parser.parse_args(args)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    if args.save:
        import matplotlib
        matplotlib.use('Agg')

    args.measured = {
        'none': None,
        'true': True,
        'false': False
    }[args.measured]

    reader = GeodataReader(args.filename, args.gdf_start_time)
    print(json.dumps(reader.stats, indent=2, sort_keys=True))

    if args.plot or args.save:
        shapes = reader.select_shapes(
            args.src_srn, args.dst_srn, args.measured)
        if shapes:
            time_start, time_stop, freq_start, freq_stop = get_shapes_bounds(
                shapes)
            time_start = args.time_start or time_start
            time_stop = args.time_stop or time_stop
            freq_start = args.freq_start or freq_start
            freq_stop = args.freq_stop or freq_stop
            grid = SpectrumGrid(time_start, time_stop, args.time_bins,
                                freq_start, freq_stop, args.freq_bins)
            for shape in shapes:
                grid.add_shape(shape)

            title = args.filename.replace('-', ' ') + " voxels"
            png_file = (title + '.png').replace(' ',
                                                '_') if args.save else None
            grid.plot_figure(title=title, png_file=png_file)


if __name__ == "__main__":
    run()
