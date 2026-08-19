"""Constants for the Australian Vehicle Registration integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "aus_rego"

# --- Config entry keys -------------------------------------------------------
CONF_JURISDICTION: Final = "jurisdiction"
CONF_PLATE: Final = "plate"
CONF_VEHICLE_NAME: Final = "vehicle_name"
CONF_VEHICLE_TYPE: Final = "vehicle_type"

# --- Options keys ------------------------------------------------------------
CONF_CHECK_TIME: Final = "check_time"
CONF_INTERVAL_DAYS: Final = "interval_days"
CONF_EXPIRY_WARNING_DAYS: Final = "expiry_warning_days"
CONF_CHECK_ON_START: Final = "check_on_start"
CONF_JITTER_SECONDS: Final = "jitter_seconds"
CONF_MANUAL_EXPIRY: Final = "manual_expiry"

# --- Generic REST provider keys ---------------------------------------------
CONF_REST_URL: Final = "rest_url"
CONF_REST_METHOD: Final = "rest_method"
CONF_REST_HEADERS: Final = "rest_headers"
CONF_REST_BODY: Final = "rest_body"
CONF_REST_STATUS_PATH: Final = "rest_status_path"
CONF_REST_EXPIRY_PATH: Final = "rest_expiry_path"
CONF_REST_REGISTERED_PATH: Final = "rest_registered_path"

# --- Defaults ----------------------------------------------------------------
DEFAULT_CHECK_TIME: Final = "07:00:00"
DEFAULT_INTERVAL_DAYS: Final = 1
DEFAULT_EXPIRY_WARNING_DAYS: Final = 14
DEFAULT_CHECK_ON_START: Final = True
# Requests are spread over this many seconds so that several vehicles (or
# several Home Assistant installations) never hit a government site in lockstep.
DEFAULT_JITTER_SECONDS: Final = 300

# Delay after Home Assistant start before the initial check runs, so that a
# restart storm does not translate into an upstream request storm.
STARTUP_CHECK_DELAY: Final = 60

# --- Events ------------------------------------------------------------------
EVENT_CHECKED: Final = f"{DOMAIN}_checked"
EVENT_STATUS_CHANGED: Final = f"{DOMAIN}_status_changed"
EVENT_EXPIRING: Final = f"{DOMAIN}_expiring"
EVENT_CHECK_FAILED: Final = f"{DOMAIN}_check_failed"

# --- Services ----------------------------------------------------------------
SERVICE_CHECK_NOW: Final = "check_now"
SERVICE_CHECK_PLATE: Final = "check_plate"

# --- Attributes --------------------------------------------------------------
ATTR_PLATE: Final = "plate"
ATTR_JURISDICTION: Final = "jurisdiction"
ATTR_STATUS: Final = "status"
ATTR_REGISTERED: Final = "registered"
ATTR_EXPIRY: Final = "expiry"
ATTR_DAYS_REMAINING: Final = "days_remaining"
ATTR_VEHICLE_NAME: Final = "vehicle_name"
ATTR_PREVIOUS_STATUS: Final = "previous_status"
ATTR_ERROR: Final = "error"

MANUFACTURER: Final = "Australian Vehicle Registration"
