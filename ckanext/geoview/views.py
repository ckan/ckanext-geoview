# -*- coding: utf-8 -*-

import logging

from flask import Blueprint

from ckan import plugins as p
from ckan.plugins import toolkit

import ckanext.geoview.utils as utils

log = logging.getLogger(__name__)
service_proxy = Blueprint("service_proxy", __name__)


def proxy_service(id, resource_id):
    data_dict = {"resource_id": resource_id}
    context = {
        "user": toolkit.c.user or toolkit.c.author,
    }
    return utils.proxy_service_resource(p.toolkit.request, context, data_dict)


def get_blueprints():
    return [service_proxy]


service_proxy.add_url_rule(
    "/dataset/<id>/resource/<resource_id>/service_proxy",
    view_func=proxy_service,
)
