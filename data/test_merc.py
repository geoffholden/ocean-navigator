import unittest
import mercator
import numpy as np
import datetime
import pytz


class TestMercator(unittest.TestCase):

    def test_init(self):
        mercator.Mercator(None)

    def test_open(self):
        with mercator.Mercator('data/testdata/mercator_test.nc'):
            pass

    def test_variables(self):
        with mercator.Mercator('data/testdata/mercator_test.nc') as n:
            variables = n.variables

            self.assertEqual(len(variables), 6)
            self.assertTrue('votemper' in variables)
            self.assertEqual(variables['votemper'].name,
                             'Sea water potential temperature')
            self.assertEqual(variables['votemper'].unit, 'Kelvin')

    def test_get_point(self):
        with mercator.Mercator('data/testdata/mercator_test.nc') as n:
            self.assertAlmostEqual(
                n.get_point(13.0, -149.0, 0, 0, 'votemper'),
                298.42, places=2
            )
            self.assertAlmostEqual(
                n.get_point(47.0, -47.0, 0, 0, 'votemper'),
                273.66, places=2
            )

            p = n.get_point([13.0, 47.0], [-149.0, -47.0], 0, 0, 'votemper')
            self.assertAlmostEqual(p[0], 298.42, places=2)
            self.assertAlmostEqual(p[1], 273.66, places=2)

    def test_get_raw_point(self):
        with mercator.Mercator('data/testdata/mercator_test.nc') as n:
            lat, lon, data = n.get_raw_point(
                13.0, -149.0, 0, 0, 'votemper'
            )

        self.assertEqual(len(lat.ravel()), 100)
        self.assertEqual(len(lon.ravel()), 100)
        self.assertEqual(len(data.ravel()), 100)
        self.assertAlmostEqual(data[4, 4], 298.6, places=1)

    def test_get_profile(self):
        with mercator.Mercator('data/testdata/mercator_test.nc') as n:
            p, d = n.get_profile(13.0, -149.0, 0, 'votemper')
            self.assertAlmostEqual(p[0], 298.42, places=2)
            self.assertAlmostEqual(p[10], 298.42, places=2)
            self.assertTrue(np.ma.is_masked(p[49]))

    def test_bottom_point(self):
        with mercator.Mercator('data/testdata/mercator_test.nc') as n:
            self.assertAlmostEqual(
                n.get_point(13.01, -149.0, 'bottom', 0, 'votemper'),
                273.95, places=2
            )

    def test_timestamps(self):
        with mercator.Mercator('data/testdata/mercator_test.nc') as n:
            self.assertEqual(len(n.timestamps), 1)
            self.assertEqual(n.timestamps[0],
                             datetime.datetime(2017, 3, 3, 0, 0, 0, 0,
                                               pytz.UTC))

            # Property is read-only
            with self.assertRaises(AttributeError):
                n.timestamps = []

            # List is immutable
            with self.assertRaises(ValueError):
                n.timestamps[0] = 0
