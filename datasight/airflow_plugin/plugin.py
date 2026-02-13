"""
DataSight Airflow Plugin — adds a "DataSight" menu item to the Airflow Web UI.

This plugin registers a Flask Blueprint that serves the DataSight
monitoring dashboard directly within the Airflow web interface.
"""

from __future__ import annotations

import logging

from airflow.plugins_manager import AirflowPlugin

from datasight.airflow_plugin.views import datasight_blueprint

logger = logging.getLogger("datasight.airflow_plugin")


class DataSightAirflowPlugin(AirflowPlugin):
    """
    Registers DataSight as a native Airflow plugin.

    This adds:
    - A "DataSight" menu item in the Airflow navigation bar
    - An embedded monitoring dashboard
    - Approval/rejection buttons for incidents
    """

    name = "datasight"
    flask_blueprints = [datasight_blueprint]
    appbuilder_views = [
        {
            "name": "DataSight AI",
            "category": "DataSight",
            "view": None,  # Using blueprint-based views
        }
    ]
    appbuilder_menu_items = [
        {
            "name": "Monitoring Dashboard",
            "category": "DataSight",
            "href": "/datasight/",
        },
        {
            "name": "Incidents",
            "category": "DataSight",
            "href": "/datasight/incidents",
        },
    ]
