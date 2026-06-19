# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from ckanext.geoview import utils


class TestGetCommonMapConfigForLeaflet(unittest.TestCase):
    @patch.object(utils.toolkit.config, "get")
    @patch.object(utils, "get_common_map_config")
    def test_mapbox_normalizes_type_and_keys(self, mock_gcm, mock_cfg_get):
        def cfg_get(key, default=None):
            return {
                "ckanext.spatial.common_map.type": "mapbox",
                "ckanext.spatial.common_map.mapbox.id": "mapbox/streets-v12",
                "ckanext.spatial.common_map.mapbox.accesstoken": "pk.test",
            }.get(key, default)

        mock_cfg_get.side_effect = cfg_get
        mock_gcm.return_value = {"type": "mapbox", "mapbox.id": "ignored"}
        out = utils.get_common_map_config_for_leaflet()
        self.assertEqual(out["type"], "mapbox")
        self.assertEqual(out["id"], "mapbox/streets-v12")
        self.assertEqual(out["accessToken"], "pk.test")

    @patch.object(utils.toolkit.config, "get")
    @patch.object(utils, "get_common_map_config")
    def test_mapbox_passes_attribution(self, mock_gcm, mock_cfg_get):
        def cfg_get(key, default=None):
            return {
                "ckanext.spatial.common_map.type": "mapbox",
                "ckanext.spatial.common_map.mapbox.id": "i",
                "ckanext.spatial.common_map.mapbox.accesstoken": "t",
                "ckanext.spatial.common_map.attribution": "© OpenStreetMap",
            }.get(key, default)

        mock_cfg_get.side_effect = cfg_get
        mock_gcm.return_value = {}
        out = utils.get_common_map_config_for_leaflet()
        self.assertEqual(out["attribution"], "© OpenStreetMap")

    @patch.object(utils.toolkit.config, "get")
    @patch.object(utils, "get_common_map_config")
    def test_non_mapbox_shallow_copy(self, mock_gcm, mock_cfg_get):
        def cfg_get(key, default=None):
            if key == "ckanext.spatial.common_map.type":
                return "Stamen.Toner"
            return default

        mock_cfg_get.side_effect = cfg_get
        base = {"type": "Stamen.Toner", "foo": "bar"}
        mock_gcm.return_value = base
        out = utils.get_common_map_config_for_leaflet()
        self.assertIsNot(out, base)
        self.assertEqual(out, base)
        out["mutate"] = True
        self.assertNotIn("mutate", base)
