# -*- coding: utf-8 -*-

import json
import logging
from six.moves.urllib.parse import urlencode, urlsplit, parse_qs

import requests

from ckan import plugins as p
from ckan.plugins import toolkit

log = logging.getLogger(__name__)

GEOJSON_MAX_FILE_SIZE = 25 * 1024 * 1024


MAX_FILE_SIZE = 3 * 1024 * 1024  # 1MB
CHUNK_SIZE = 512

# HTTP request parameters that may conflict with OGC services
# protocols and should be excluded from proxied calls
OGC_EXCLUDED_PARAMS = [
    "service",
    "version",
    "request",
    "outputformat",
    "typename",
    "layers",
    "srsname",
    "bbox",
    "maxfeatures",
]


def proxy_service_resource(request, context, data_dict):
    """ Chunked proxy for resources. To make sure that the file is not too
    large, first, we try to get the content length from the headers.
    If the headers to not contain a content length (if it is a chinked
    response), we only transfer as long as the transferred data is less
    than the maximum file size. """
    resource_id = data_dict["resource_id"]
    log.info("Proxify resource {id}".format(id=resource_id))
    resource = toolkit.get_action("resource_show")(context, {"id": resource_id})
    url = resource["url"]
    return proxy_service_url(request, url)


def proxy_service_url(req, url):

    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        toolkit.abort(409, detail="Invalid URL.")

    try:
        method = req.environ["REQUEST_METHOD"]

        params = parse_qs(parts.query)

        if not p.toolkit.asbool(
            toolkit.config.get(
                "ckanext.geoview.forward_ogc_request_params", "False"
            )
        ):
            # remove query parameters that may conflict with OGC protocols
            for key in dict(params):
                if key.lower() in OGC_EXCLUDED_PARAMS:
                    del params[key]
            parts = parts._replace(query=urlencode(params))

        parts = parts._replace(fragment="")  # remove potential fragment
        url = parts.geturl()
        if method == "POST":
            length = int(req.environ["CONTENT_LENGTH"])
            headers = {"Content-Type": req.environ["CONTENT_TYPE"]}
            body = req.body
            r = requests.post(url, data=body, headers=headers, stream=True)
        else:
            r = requests.get(url, params=req.query_string, stream=True)

        # log.info('Request: {req}'.format(req=r.request.url))
        # log.info('Request Headers: {h}'.format(h=r.request.headers))

        cl = r.headers.get("content-length")
        if cl and int(cl) > MAX_FILE_SIZE:
            toolkit.abort(
                409,
                (
                    """Content is too large to be proxied. Allowed
                file size: {allowed}, Content-Length: {actual}. Url: """
                    + url
                ).format(allowed=MAX_FILE_SIZE, actual=cl),
            )
        if toolkit.check_ckan_version("2.9"):
            from flask import make_response

            response = make_response()
        else:
            response = toolkit.response

        response.content_type = r.headers["content-type"]
        response.charset = r.encoding

        length = 0
        for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
            if toolkit.check_ckan_version("2.9"):
                response.data += chunk
            else:
                response.body_file.write(chunk)
            length += len(chunk)

            if length >= MAX_FILE_SIZE:
                toolkit.abort(
                    409,
                    (
                        """Content is too large to be proxied. Allowed
                file size: {allowed}, Content-Length: {actual}. Url: """
                        + url
                    ).format(allowed=MAX_FILE_SIZE, actual=length),
                )

    except requests.exceptions.HTTPError as error:
        details = "Could not proxy resource. Server responded with %s %s" % (
            error.response.status_code,
            error.response.reason,
        )
        toolkit.abort(409, detail=details)
    except requests.exceptions.ConnectionError as error:
        details = (
            """Could not proxy resource because a
                            connection error occurred. %s"""
            % error
        )
        toolkit.abort(502, detail=details)
    except requests.exceptions.Timeout as error:
        details = "Could not proxy resource because the connection timed out."
        toolkit.abort(504, detail=details)
    return response


def get_common_map_config():
    """Returns a dict with all configuration options related to the common
    base map (ie those starting with 'ckanext.spatial.common_map.')
    """
    namespace = "ckanext.spatial.common_map."
    return dict(
        [
            (k.replace(namespace, ""), v)
            for k, v in toolkit.config.items()
            if k.startswith(namespace)
        ]
    )


def get_common_map_config_for_leaflet():
    """Normalize common map settings for Leaflet + leaflet-providers.

    * ``ckanext.spatial.common_map.mapbox.id``
    * ``ckanext.spatial.common_map.mapbox.accesstoken``
    """
    raw = dict(get_common_map_config())
    type_val = toolkit.config.get("ckanext.spatial.common_map.type") or ""
    if not (isinstance(type_val, str) and type_val.strip().lower() == "mapbox"):
        return raw

    map_id = toolkit.config.get("ckanext.spatial.common_map.mapbox.id")
    token = toolkit.config.get("ckanext.spatial.common_map.mapbox.accesstoken")

    out = {
        "type": "mapbox",
        "id": "" if map_id in (None, False) else str(map_id),
        "accessToken": "" if token in (None, False) else str(token),
    }

    for suffix in ("attribution", "subdomains", "tms"):
        val = toolkit.config.get("ckanext.spatial.common_map." + suffix)
        if val is not None:
            out[suffix] = val

    return out


def get_shapefile_viewer_config():
    """
        Returns a dict with all configuration options related to the
        Shapefile viewer (ie those starting with 'ckanext.geoview.shp_viewer.')
    """
    namespace = "ckanext.geoview.shp_viewer."
    return dict(
        [
            (k.replace(namespace, ""), v)
            for k, v in toolkit.config.items()
            if k.startswith(namespace)
        ]
    )


def get_max_file_size():
    return toolkit.config.get(
        "ckanext.geoview.geojson.max_file_size", GEOJSON_MAX_FILE_SIZE
    )


def get_openlayers_viewer_config():
    """
        Returns a dict with all configuration options related to the
        OpenLayers viewer (ie those starting with 'ckanext.geoview.ol_viewer.')
    """
    namespace = "ckanext.geoview.ol_viewer."
    return dict(
        [
            (k.replace(namespace, ""), v)
            for k, v in toolkit.config.items()
            if k.startswith(namespace)
        ]
    )


def load_basemaps(basemapsFile):

    try:
        with open(basemapsFile) as config_file:
            basemapsConfig = json.load(config_file)
    except Exception as inst:
        msg = "Couldn't read basemaps config from %r: %s" % (
            basemapsFile,
            inst,
        )
        raise Exception(msg)

    return basemapsConfig


def get_proxified_service_url(data_dict):
    """
    :param data_dict: contains a resource and package dict
    :type data_dict: dictionary
    """
    url = toolkit.url_for(
        action="proxy_service",
        controller='service_proxy',
        id=data_dict["package"]["name"],
        resource_id=data_dict["resource"]["id"],
    )
    log.debug("Proxified url is {0}".format(url))
    return url
