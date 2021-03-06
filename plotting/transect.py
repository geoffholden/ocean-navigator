from grid import bathymetry
from netCDF4 import Dataset
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter, StrMethodFormatter
import numpy as np
import re
import colormap
from oceannavigator import app
from geopy.distance import VincentyDistance
import utils
from oceannavigator.util import get_variable_name, get_variable_unit, \
    get_dataset_url, get_dataset_climatology, get_variable_scale_factor
import line
from flask_babel import gettext
from data import open_dataset, geo


class TransectPlotter(line.LinePlotter):

    def __init__(self, dataset_name, query, format):
        self.plottype = "transect"
        super(TransectPlotter, self).__init__(dataset_name, query, format)
        self.size = '11x5'

    def parse_query(self, query):
        super(TransectPlotter, self).parse_query(query)
        depth_limit = query.get("depth_limit")
        if depth_limit is None or depth_limit == '' or depth_limit is False:
            self.depth_limit = None
        else:
            self.depth_limit = int(depth_limit)

    def __fill_invalid_shift(self, z):
        for s in range(1, z.shape[0]):
            if z.mask.any():
                z_shifted = np.roll(z, shift=s, axis=0)
                idx = ~z_shifted.mask * z.mask
                z[idx] = z_shifted[idx]
            else:
                break

    def load_data(self):
        with open_dataset(get_dataset_url(self.dataset_name)) as dataset:
            if self.time < 0:
                self.time += len(dataset.timestamps)
            time = np.clip(self.time, 0, len(dataset.timestamps) - 1)

            for idx, v in enumerate(self.variables):
                var = dataset.variables[v]
                if not (set(var.dimensions) & set(dataset.depth_dimensions)):
                    for potential in dataset.variables:
                        if potential in self.variables:
                            continue
                        pot = dataset.variables[potential]
                        if (set(pot.dimensions) &
                                set(dataset.depth_dimensions)):
                            if len(pot.shape) > 3:
                                self.variables[idx] = potential
                                self.variables_anom[idx] = potential

            value = parallel = perpendicular = None

            variable_names = self.get_variable_names(dataset, self.variables)
            variable_units = self.get_variable_units(dataset, self.variables)
            scale_factors = self.get_variable_scale_factors(dataset,
                                                            self.variables)

            if len(self.variables) > 1:
                v = []
                for name in self.variables:
                    v.append(dataset.variables[name])

                distances, times, lat, lon, bearings = geo.path_to_points(
                    self.points, 100
                )
                transect_pts, distance, x, dep = dataset.get_path_profile(
                    self.points, time, self.variables[0], 100)
                transect_pts, distance, y, dep = dataset.get_path_profile(
                    self.points, time, self.variables[1], 100)

                x = np.multiply(x, scale_factors[0])
                y = np.multiply(y, scale_factors[1])

                r = np.radians(np.subtract(90, bearings))
                theta = np.arctan2(y, x) - r
                mag = np.sqrt(x ** 2 + y ** 2)

                parallel = mag * np.cos(theta)
                perpendicular = mag * np.sin(theta)

            else:
                transect_pts, distance, value, dep = dataset.get_path_profile(
                    self.points, time, self.variables[0])

                value = np.multiply(value, scale_factors[0])

            variable_units[0], value = self.kelvin_to_celsius(
                variable_units[0],
                value
            )

            if len(self.variables) == 2:
                variable_names[0] = self.vector_name(variable_names[0])

            if self.cmap is None:
                self.cmap = colormap.find_colormap(variable_names[0])

            self.timestamp = dataset.timestamps[int(time)]

            self.depth = dep
            self.depth_unit = "m"

            self.transect_data = {
                "points": transect_pts,
                "distance": distance,
                "data": value,
                "name": variable_names[0],
                "unit": variable_units[0],
                "parallel": parallel,
                "perpendicular": perpendicular,
            }

            if self.surface is not None:
                surface_pts, surface_dist, t, surface_value = \
                    dataset.get_path(
                        self.points,
                        0,
                        time,
                        self.surface,
                    )
                surface_unit = get_variable_unit(
                    self.dataset_name,
                    dataset.variables[self.surface]
                )
                surface_name = get_variable_name(
                    self.dataset_name,
                    dataset.variables[self.surface]
                )
                surface_factor = get_variable_scale_factor(
                    self.dataset_name,
                    dataset.variables[self.surface]
                )
                surface_value = np.multiply(surface_value, surface_factor)
                surface_unit, surface_value = self.kelvin_to_celsius(
                    surface_unit,
                    surface_value
                )

                self.surface_data = {
                    "points": surface_pts,
                    "distance": surface_dist,
                    "data": surface_value,
                    "name": surface_name,
                    "unit": surface_unit
                }

        if self.variables != self.variables_anom:
            with open_dataset(
                get_dataset_climatology(self.dataset_name)
            ) as dataset:
                if self.variables[0] in dataset.variables:
                    if len(self.variables) == 1:
                        climate_points, climate_distance, climate_data = \
                            dataset.get_path_profile(self.points,
                                                     self.timestamp.month - 1,
                                                     self.variables[0])
                        u, climate_data = self.kelvin_to_celsius(
                            dataset.variables[self.variables[0]].unit,
                            climate_data
                        )
                        self.transect_data['data'] -= - climate_data
                    else:
                        climate_pts, climate_distance, climate_x, cdep = \
                            dataset.get_path_profile(
                                self.points,
                                self.timestamp.month - 1,
                                self.variables[0],
                                100
                            )
                        climate_pts, climate_distance, climate_y, cdep = \
                            dataset.get_path_profile(
                                self.points,
                                self.timestamp.month - 1,
                                self.variables[0],
                                100
                            )

                        climate_distances, ctimes, clat, clon, bearings = \
                            geo.path_to_points(self.points, 100)

                        r = np.radians(np.subtract(90, bearings))
                        theta = np.arctan2(y, x) - r
                        mag = np.sqrt(x ** 2 + y ** 2)

                        climate_parallel = mag * np.cos(theta)
                        climate_perpendicular = mag * np.sin(theta)

                        self.transect_data['parallel'] -= climate_parallel
                        self.transect_data[
                            'perpendicular'] -= climate_perpendicular

        # Bathymetry
        with Dataset(app.config['BATHYMETRY_FILE'], 'r') as dataset:
            bath_x, bath_y = bathymetry(
                dataset.variables['y'],
                dataset.variables['x'],
                dataset.variables['z'],
                self.points)

        self.bathymetry = {
            'x': bath_x,
            'y': bath_y
        }

    def csv(self):
        header = [
            ['Dataset', self.dataset_name],
            ["Timestamp", self.timestamp.isoformat()]
        ]

        columns = [
            "Latitude",
            "Longitude",
            "Distance (km)",
            "Depth (m)",
        ]

        if self.surface is not None:
            columns.append("%s (%s)" % (
                self.surface_data['name'],
                self.surface_data['unit']
            ))

        if len(self.variables) > 1:
            columns.append("Parallel %s (%s)" % (self.transect_data['name'],
                                                 self.transect_data['unit']))
            columns.append(
                "Perpendicular %s (%s)" % (self.transect_data['name'],
                                           self.transect_data['unit']))
            values = ['parallel', 'perpendicular']
        else:
            columns.append("%s (%s)" % (self.transect_data['name'],
                                        self.transect_data['unit']))
            values = ['data']

        data = []
        for idx, dist in enumerate(self.transect_data['distance']):
            if dist == self.transect_data['distance'][idx - 1]:
                continue

            for j in range(0, len(self.transect_data[values[0]][:, idx])):
                entry = [
                    "%0.4f" % self.transect_data['points'][0, idx],
                    "%0.4f" % self.transect_data['points'][1, idx],
                    "%0.1f" % dist,
                    "%0.1f" % self.depth[idx, j]
                ]
                if self.surface is not None:
                    if j == 0:
                        entry.append("%0.4f" % self.surface_data['data'][idx])
                    else:
                        entry.append("-")

                for t in values:
                    entry.append("%0.4f" % self.transect_data[t][j, idx])

                if entry[-1] == "nan":
                    continue

                data.append(entry)

        return super(TransectPlotter, self).csv(header, columns, data)

    def odv_ascii(self):
        float_to_str = np.vectorize(lambda x: "%0.3f" % x)
        numstations = len(self.transect_data['distance'])
        station = range(1, 1 + numstations)
        station = map(lambda s: "%03d" % s, station)

        latitude = np.repeat(self.transect_data['points'][0, :],
                             len(self.depth))
        longitude = np.repeat(self.transect_data['points'][1, :],
                              len(self.depth))
        time = np.repeat(self.timestamp, len(station))
        depth = self.depth

        if len(self.variables) > 1:
            variable_names = [
                "%s Parallel" % self.transect_data['name'],
                "%s Perpendicular" % self.transect_data['name']
            ]
            variable_units = [self.transect_data['unit']] * 2
            pa = self.transect_data['parallel'].transpose()
            pe = self.transect_data['perpendicular'].transpose()
            data = np.ma.array([pa, pe])
            data = np.rollaxis(data, 0, 2)
        else:
            variable_names = [self.transect_data['name']]
            variable_units = [self.transect_data['unit']]
            data = self.transect_data['data'].transpose()

        data = float_to_str(data)

        return super(TransectPlotter, self).odv_ascii(
            self.dataset_name,
            variable_names,
            variable_units,
            station,
            latitude,
            longitude,
            depth,
            time,
            data
        )

    def plot(self):
        # Figure size
        figuresize = map(float, self.size.split("x"))
        figuresize[1] *= len(self.variables)
        fig = plt.figure(figsize=figuresize, dpi=self.dpi)

        velocity = len(self.variables) == 2
        anom = self.variables[0] != self.variables_anom[0]

        if self.showmap:
            width = 2
            width_ratios = [2, 7]
        else:
            width = 1
            width_ratios = [1]

        if velocity:
            gs = gridspec.GridSpec(
                2, width, width_ratios=width_ratios, height_ratios=[1, 1])
        else:
            gs = gridspec.GridSpec(1, width, width_ratios=width_ratios)

        if self.showmap:
            # Plot the transect on a map
            if velocity:
                plt.subplot(gs[:, 0])
            else:
                plt.subplot(gs[0])

            utils.path_plot(self.transect_data['points'])

        def do_plot(subplots, map_subplot, nomap_subplot, data, name):
            if self.showmap:
                plt.subplot(subplots[map_subplot])
            else:
                plt.subplot(subplots[nomap_subplot])

            divider = self._transect_plot(data, self.depth, name, vmin, vmax)

            if self.surface:
                self._surface_plot(divider)

        # transect Plot
        if velocity:
            if self.scale:
                vmin = self.scale[0]
                vmax = self.scale[1]
            else:
                vmin = min(np.amin(self.transect_data['parallel']),
                           np.amin(self.transect_data['perpendicular']))
                vmax = max(np.amax(self.transect_data['parallel']),
                           np.amin(self.transect_data['perpendicular']))
                vmin = min(vmin, -vmax)
                vmax = max(vmax, -vmin)

            do_plot(
                gs, 1, 0,
                self.transect_data['parallel'],
                gettext("Parallel")
            )
            do_plot(
                gs, 3, 1,
                self.transect_data['perpendicular'],
                gettext("Perpendicular")
            )
        else:
            if self.scale:
                vmin = self.scale[0]
                vmax = self.scale[1]
            else:
                vmin = np.amin(self.transect_data['data'])
                vmax = np.amax(self.transect_data['data'])
                if re.search(
                    "velocity",
                    self.transect_data['name'],
                    re.IGNORECASE
                ) or anom:
                    vmin = min(vmin, -vmax)
                    vmax = max(vmax, -vmin)

            do_plot(
                gs, 1, 0,
                self.transect_data['data'],
                self.transect_data['name'],
            )

        fig.suptitle("%s, %s\n%s" % (
            self.transect_data['name'],
            self.date_formatter(self.timestamp),
            self.name
        ))

        fig.tight_layout(pad=3, w_pad=4)
        if velocity:
            fig.subplots_adjust(top=0.9)

        return super(TransectPlotter, self).plot(fig)

    def _surface_plot(self, axis_divider):
        ax = axis_divider.append_axes("top", size="15%", pad=0.15)
        ax.plot(self.surface_data['distance'],
                self.surface_data['data'], color='r')
        ax.locator_params(nbins=3)
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        label = plt.ylabel(utils.mathtext(self.surface_data['unit']))
        title = plt.title(self.surface_data['name'], y=1.1)
        plt.setp(title, size='smaller')
        plt.setp(label, size='smaller')
        plt.setp(ax.get_yticklabels(), size='x-small')
        plt.xlim([0, self.surface_data['distance'][-1]])
        if np.any(map(
            lambda x: re.search(x, self.surface_data['name'], re.IGNORECASE),
            [
                "free surface",
                "surface height"
            ]
        )):
            ylim = plt.ylim()
            plt.ylim([min(ylim[0], -ylim[1]), max([-ylim[0], ylim[1]])])
            ax.yaxis.grid(True)
        ax.axes.get_xaxis().set_visible(False)

    def _transect_plot(self, values, depths, name, vmin, vmax):
        self.__fill_invalid_shift(values)

        dist = np.tile(self.transect_data['distance'], (values.shape[0], 1))
        c = plt.pcolormesh(dist, depths.transpose(), values,
                           cmap=self.cmap,
                           shading='gouraud',
                           vmin=vmin,
                           vmax=vmax)
        ax = plt.gca()
        ax.invert_yaxis()
        if self.depth_limit is None or (
            self.depth_limit is not None and
            self.linearthresh < self.depth_limit
        ):
            plt.yscale('symlog', linthreshy=self.linearthresh)
        ax.yaxis.set_major_formatter(ScalarFormatter())

        # Mask out the bottom
        plt.fill_between(
            self.bathymetry['x'],
            self.bathymetry['y'] * -1,
            plt.ylim()[0],
            facecolor='dimgray',
            hatch='xx'
        )
        ax.set_axis_bgcolor('dimgray')

        plt.xlabel(gettext("Distance (km)"))
        plt.ylabel(gettext("Depth (m)"))
        plt.xlim([self.transect_data['distance'][0],
                  self.transect_data['distance'][-1]])

        # Tighten the y-limits
        if self.depth_limit:
            plt.ylim(self.depth_limit, 0)
        else:
            deep = np.amax(self.bathymetry['y'] * -1)
            l = 10 ** np.floor(np.log10(deep))
            plt.ylim(np.ceil(deep / l) * l, 0)

        ticks = sorted(set(list(plt.yticks()[0]) + [self.linearthresh,
                                                    plt.ylim()[0]]))
        if self.depth_limit is not None:
            ticks = filter(lambda y: y <= self.depth_limit, ticks)

        plt.yticks(ticks)

        # Show the linear threshold
        plt.plot([self.transect_data['distance'][0],
                  self.transect_data['distance'][-1]],
                 [self.linearthresh, self.linearthresh],
                 'k:', alpha=0.5)

        divider = make_axes_locatable(ax)
        cax = divider.append_axes("right", size="5%", pad=0.05)
        bar = plt.colorbar(c, cax=cax)
        bar.set_label(
            name + " (" + utils.mathtext(self.transect_data['unit']) + ")")

        if len(self.points) > 2:
            station_distances = []
            current_dist = 0
            d = VincentyDistance()
            for idx, p in enumerate(self.points):
                if idx == 0:
                    station_distances.append(0)
                else:
                    current_dist += d.measure(
                        p, self.points[idx - 1])
                    station_distances.append(current_dist)

            ax2 = ax.twiny()
            ax2.set_xticks(station_distances)
            ax2.set_xlim([self.transect_data['distance'][0],
                          self.transect_data['distance'][-1]])
            ax2.tick_params(
                'x',
                length=0,
                width=0,
                pad=-3,
                labelsize='xx-small',
                which='major')
            ax2.xaxis.set_major_formatter(StrMethodFormatter(u"$\u25bc$"))
            cax = make_axes_locatable(ax2).append_axes(
                "right", size="5%", pad=0.05)
            bar2 = plt.colorbar(c, cax=cax)
            bar2.remove()
        return divider
