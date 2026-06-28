"""
    Tuya Devices: https://xzetsubou.github.io/hass-localtuya/auto_configure/

    This functionality is similar to HA Tuya, as it retrieves the category and searches for the corresponding categories. 
    The categories data has been improved & modified to work seamlessly with localtuya

    Device Data: You can obtain all the data for your device from Home Assistant by directly downloading the diagnostics or using entry diagnostics.
        Alternative: Use Tuya IoT.

    Add a new device or modify an existing one:
        1. Make sure the device category doesn't already exist. If you are creating a new one, you can modify existing categories.
        2. In order to add a device, you need to specify the category of the device you want to add inside the entity type dictionary.
    
    Add entities to devices:
        1. Open the file with the name of the entity type on which you want to make changes [e.g. switches.py] and search for your device category.
        2. You can add entities inside the tuple value of the dictionary by including LocalTuyaEntity and passing the parameters for the entity configurations.
        3. These configurations include "id" (required), "icon" (optional), "device_class" (optional), "state_class" (optional), and "name" (optional) [Using COVERS as an example]
            Example: "3 ( code: percent_state , value: 0 )" - Refer to the Device Data section above for more details.
                current_state_dp = DPCode.PERCENT_STATE < This maps the "percent_state" code DP to the current_state_dp configuration.

            If the configuration is not DPS, it will be inserted through "custom_configs". This is used to inject any configuration into the entity configuration
                Example: custom_configs={"positioning_mode": "position"}. I hope that clarifies the concept
                
        Check URL above for more details. 
"""

import json
from .base import LocalTuyaEntity, CONF_DPS_STRINGS, CLOUD_VALUE, DPType
from enum import Enum
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ENTITY_CATEGORY,
    CONF_FRIENDLY_NAME,
    CONF_ID,
    CONF_PLATFORM,
    CONF_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    Platform,
    UnitOfTemperature,
)

import logging

# Supported files
from .alarm_control_panels import ALARMS  # not added yet
from .binary_sensors import BINARY_SENSORS
from .buttons import BUTTONS
from .climates import CLIMATES
from .covers import COVERS
from .fans import FANS
from .humidifiers import HUMIDIFIERS
from .lights import LIGHTS
from .numbers import NUMBERS
from .remotes import REMOTES
from .selects import SELECTS
from .sensors import SENSORS
from .sirens import SIRENS
from .switches import SWITCHES
from .vacuums import VACUUMS
from .locks import LOCKS
from .water_heaters import WATER_HEATERS
from ...const import CONF_MAX_VALUE, CONF_MIN_VALUE, CONF_OPTIONS, CONF_SCALING, CONF_STATE_CLASS, CONF_STEPSIZE

# The supported PLATFORMS [ Platform: Data ]
DATA_PLATFORMS = {
    Platform.ALARM_CONTROL_PANEL: ALARMS,
    Platform.BINARY_SENSOR: BINARY_SENSORS,
    Platform.BUTTON: BUTTONS,
    Platform.CLIMATE: CLIMATES,
    Platform.COVER: COVERS,
    Platform.FAN: FANS,
    Platform.HUMIDIFIER: HUMIDIFIERS,
    Platform.LIGHT: LIGHTS,
    Platform.LOCK: LOCKS,
    Platform.NUMBER: NUMBERS,
    Platform.REMOTE: REMOTES,
    Platform.SELECT: SELECTS,
    Platform.SENSOR: SENSORS,
    Platform.SIREN: SIRENS,
    Platform.SWITCH: SWITCHES,
    Platform.VACUUM: VACUUMS,
    Platform.WATER_HEATER: WATER_HEATERS,
}

_LOGGER = logging.getLogger(__name__)

TUYA_CATEGORY = "category"
DEVICE_CLOUD_DATA = "device_cloud_data"


def gen_localtuya_entities(localtuya_data: dict, tuya_category: str) -> list[dict]:
    """Return localtuya entities using the data that provided from TUYA"""
    detected_dps: list = localtuya_data.get(CONF_DPS_STRINGS) or []
    device_name: str = localtuya_data.get(CONF_FRIENDLY_NAME).strip()
    device_cloud_data: dict = localtuya_data.get(DEVICE_CLOUD_DATA, {})
    dps_data = device_cloud_data.get("dps_data", {})
    original_detected_dps = list(detected_dps)
    _LOGGER.warning(
        "[LOCALTUYA_DPS_DEBUG] entity_gen start device=%s category=%s original_detected_dps=%s cloud_dps_keys=%s cloud_codes=%s cloud_category=%s",
        device_name,
        tuya_category,
        original_detected_dps,
        sorted((dps_data or {}).keys(), key=str),
        {
            str(dp_id): dp_data.get("code")
            for dp_id, dp_data in (dps_data or {}).items()
            if isinstance(dp_data, dict)
        },
        device_cloud_data.get(TUYA_CATEGORY),
    )
    detected_dps = extend_detected_dps_with_cloud_data(detected_dps, dps_data)
    _LOGGER.warning(
        "[LOCALTUYA_DPS_DEBUG] entity_gen extended device=%s category=%s extended_detected_dps=%s",
        device_name,
        tuya_category,
        detected_dps,
    )

    if not tuya_category or not detected_dps:
        _LOGGER.warning(
            "[LOCALTUYA_DPS_DEBUG] entity_gen missing_input device=%s category=%s detected_dps=%s",
            device_name,
            tuya_category,
            detected_dps,
        )
        _LOGGER.debug(f"Missing category: {tuya_category} or DPS: {detected_dps}")
        return

    entities = {}
    platforms_with_category = [
        str(platform)
        for platform, tuya_data in DATA_PLATFORMS.items()
        if tuya_category in tuya_data
    ]
    _LOGGER.warning(
        "[LOCALTUYA_DPS_DEBUG] entity_gen category_lookup device=%s category=%s platforms_with_category=%s all_cloud_codes=%s",
        device_name,
        tuya_category,
        platforms_with_category,
        sorted(
            {
                str(dp_data.get("code"))
                for dp_data in (dps_data or {}).values()
                if isinstance(dp_data, dict) and dp_data.get("code")
            }
        ),
    )

    for platform, tuya_data in DATA_PLATFORMS.items():
        # TODO: Refactor needed here.
        if cat_data := tuya_data.get(tuya_category):
            _LOGGER.warning(
                "[LOCALTUYA_DPS_DEBUG] entity_gen platform_candidates device=%s category=%s platform=%s candidate_count=%s",
                device_name,
                tuya_category,
                platform,
                len(cat_data),
            )
            for ent_data in cat_data:
                main_confs = ent_data.data
                localtuya_conf = ent_data.localtuya_conf
                localtuya_entity_configs = ent_data.entity_configs
                # Conditions
                contains_any: list[str] = ent_data.contains_any
                entity = {}

                # used_dp = 0
                for k, code in localtuya_conf.items():
                    if type(code) == Enum:
                        code = code.value

                    # If there's multi possible codes.
                    if isinstance(code, tuple):
                        for _code in code:
                            if any(_code in dp.lower().split() for dp in detected_dps):
                                code = parse_enum(_code)
                                break
                            else:
                                code = None

                    for dp_data in detected_dps:
                        dp_data: str = dp_data.lower()
                        # Same method we use in config_flow to get dp.
                        dp_id = dp_data.split(" ")[0]

                        if k in entity:
                            # if the k already configured break the loop!.
                            _LOGGER.debug(f"{k} Already configured with: {entity[k]}.")
                            break

                        if contains_any is not None:
                            if not any(cond in dp_data for cond in contains_any):
                                continue

                        if code and code.lower() in dp_data.split():
                            entity[k] = dp_id

                # Pull dp values from cloud. still unsure to apply this to all.
                # This is due to the fact that some local values may not same with the values provided from cloud.
                # For now, this is applied only to numbers values.
                for k, v in localtuya_entity_configs.items():
                    if isinstance(v, CLOUD_VALUE):
                        config_dp = entity.get(v.dp_config)
                        dp_values = get_dp_values(config_dp, dps_data, v) or {}

                        # special case for lights
                        # if v.value_key in dp_values and "kelvin" in k:
                        #     value = dp_values.get(v.value_key)
                        #     dp_values[v.value_key] = convert_to_kelvin(value)

                        entity[k] = dp_values.get(v.value_key, v.default_value)
                    else:
                        entity[k] = v

                if entity:
                    # Entity most contains ID
                    if not entity.get(CONF_ID):
                        _LOGGER.warning(
                            "[LOCALTUYA_DPS_DEBUG] entity_gen candidate_without_id device=%s category=%s platform=%s entity=%s localtuya_conf=%s",
                            device_name,
                            tuya_category,
                            platform,
                            entity,
                            localtuya_conf,
                        )
                        continue
                    # Workaround to Prevent duplicated id.
                    if entity[CONF_ID] in entities:
                        _LOGGER.warning(
                            "[LOCALTUYA_DPS_DEBUG] entity_gen duplicate_id device=%s category=%s platform=%s entity=%s existing=%s",
                            device_name,
                            tuya_category,
                            platform,
                            entity,
                            entities.get(entity[CONF_ID]),
                        )
                        _LOGGER.debug(f"{device_name}: Duplicated ID: {entity}")
                        continue

                    entity.update(main_confs)
                    entity[CONF_PLATFORM] = platform
                    apply_cloud_entity_defaults(entity, dps_data)
                    entities[entity.get(CONF_ID)] = entity
                    _LOGGER.warning(
                        "[LOCALTUYA_DPS_DEBUG] entity_gen configured device=%s category=%s platform=%s entity=%s",
                        device_name,
                        tuya_category,
                        platform,
                        entity,
                    )
                    _LOGGER.debug(f"{device_name}: Entity configured: {entity}")
                else:
                    _LOGGER.warning(
                        "[LOCALTUYA_DPS_DEBUG] entity_gen no_match device=%s category=%s platform=%s localtuya_conf=%s contains_any=%s detected_dps=%s",
                        device_name,
                        tuya_category,
                        platform,
                        localtuya_conf,
                        contains_any,
                        detected_dps,
                    )

    add_cloud_fallback_entities(entities, dps_data, device_name, tuya_category)

    # sort entities by id
    sorted_ids = sorted(entities, key=int)

    # convert to list of configs
    list_entities = [entities.get(id) for id in sorted_ids]

    cloud_ids = {str(dp_id) for dp_id in (dps_data or {})}
    configured_ids = {str(entity.get(CONF_ID)) for entity in list_entities}
    unmatched_cloud_ids = sorted(cloud_ids - configured_ids, key=str)
    _LOGGER.warning(
        "[LOCALTUYA_DPS_DEBUG] entity_gen final device=%s category=%s configured_ids=%s unmatched_cloud_ids=%s unmatched_cloud_codes=%s entities=%s",
        device_name,
        tuya_category,
        sorted(configured_ids, key=str),
        unmatched_cloud_ids,
        {
            str(dp_id): dps_data.get(str(dp_id), {}).get("code")
            for dp_id in unmatched_cloud_ids
            if isinstance(dps_data.get(str(dp_id)), dict)
        },
        list_entities,
    )
    _LOGGER.debug(f"{device_name}: Configured entities: {list_entities}")
    # return []
    return list_entities



def add_cloud_fallback_entities(
    entities: dict[str, dict],
    dps_data: dict,
    device_name: str,
    tuya_category: str,
) -> None:
    """Create entities directly from cloud model for unmapped DP definitions."""
    if not dps_data:
        return

    for dp_id in sorted(dps_data, key=lambda value: int(value) if str(value).isdigit() else str(value)):
        dp_id = str(dp_id)
        if dp_id in entities:
            continue

        dp_data = dps_data.get(dp_id)
        if not isinstance(dp_data, dict):
            continue

        code = dp_data.get("code")
        if not code:
            continue

        dp_type = get_cloud_dp_type(dp_data)
        if dp_type not in {"value", "enum"}:
            continue

        access_mode = str(dp_data.get("accessMode") or dp_data.get("access_mode") or "").lower()
        platform = cloud_platform_for_dp(code, dp_type, access_mode)
        if platform is None:
            continue

        entity = {
            CONF_ID: dp_id,
            CONF_FRIENDLY_NAME: cloud_friendly_name(code),
            CONF_PLATFORM: platform,
            CONF_ENTITY_CATEGORY: cloud_entity_category(code, platform),
        }
        apply_cloud_entity_defaults(entity, dps_data)
        entities[dp_id] = entity
        _LOGGER.warning(
            "[LOCALTUYA_DPS_DEBUG] entity_gen cloud_fallback device=%s category=%s platform=%s entity=%s cloud_data=%s",
            device_name,
            tuya_category,
            platform,
            entity,
            dp_data,
        )


def apply_cloud_entity_defaults(entity: dict, dps_data: dict) -> None:
    """Apply unit, scaling and options from cloud model to an entity config."""
    dp_id = str(entity.get(CONF_ID))
    dp_data = dps_data.get(dp_id)
    if not isinstance(dp_data, dict):
        return

    type_spec = get_cloud_type_spec(dp_data)
    dp_type = get_cloud_dp_type(dp_data, type_spec)
    code = str(dp_data.get("code") or "")
    platform = entity.get(CONF_PLATFORM)

    if platform == Platform.SENSOR:
        if dp_type == "enum":
            entity.pop(CONF_DEVICE_CLASS, None)
            entity.pop(CONF_STATE_CLASS, None)
            entity.pop(CONF_UNIT_OF_MEASUREMENT, None)
            if entity.get(CONF_ENTITY_CATEGORY) in (None, "None"):
                entity[CONF_ENTITY_CATEGORY] = cloud_entity_category(code, platform)
            return

        if dp_type == "value":
            apply_cloud_unit(entity, type_spec, code)
            apply_cloud_scale(entity, type_spec)
            if CONF_STATE_CLASS not in entity:
                entity[CONF_STATE_CLASS] = SensorStateClass.MEASUREMENT
            if CONF_DEVICE_CLASS not in entity:
                device_class = cloud_sensor_device_class(code, type_spec)
                if device_class:
                    entity[CONF_DEVICE_CLASS] = device_class
            if entity.get(CONF_ENTITY_CATEGORY) in (None, "None"):
                entity[CONF_ENTITY_CATEGORY] = cloud_entity_category(code, platform)

    elif platform == Platform.NUMBER:
        apply_cloud_unit(entity, type_spec, code)
        apply_cloud_scale(entity, type_spec)
        if "min" in type_spec and CONF_MIN_VALUE not in entity:
            entity[CONF_MIN_VALUE] = type_spec.get("min")
        if "max" in type_spec and CONF_MAX_VALUE not in entity:
            entity[CONF_MAX_VALUE] = type_spec.get("max")
        if "step" in type_spec and CONF_STEPSIZE not in entity:
            entity[CONF_STEPSIZE] = type_spec.get("step")
        if entity.get(CONF_ENTITY_CATEGORY) in (None, "None"):
            entity[CONF_ENTITY_CATEGORY] = cloud_entity_category(code, platform)

    elif platform == Platform.SELECT:
        options = type_spec.get("range")
        if isinstance(options, list) and CONF_OPTIONS not in entity:
            entity[CONF_OPTIONS] = {str(option): cloud_option_name(option) for option in options}
        if entity.get(CONF_ENTITY_CATEGORY) in (None, "None"):
            entity[CONF_ENTITY_CATEGORY] = cloud_entity_category(code, platform)


def get_cloud_type_spec(dp_data: dict) -> dict:
    """Return parsed type specification from cloud DP data."""
    values = dp_data.get("values") or dp_data.get("typeSpec") or {}
    if isinstance(values, dict):
        return values
    if not isinstance(values, str) or not values:
        return {}
    try:
        return json.loads(values)
    except (TypeError, ValueError):
        try:
            return json.loads(values.replace("'", '"'))
        except (TypeError, ValueError):
            return {}


def get_cloud_dp_type(dp_data: dict, type_spec: dict | None = None) -> str:
    """Return normalized cloud DP type."""
    type_spec = type_spec if type_spec is not None else get_cloud_type_spec(dp_data)
    dp_type = str(dp_data.get("type") or type_spec.get("type") or "").lower()
    if dp_type == "integer":
        return "value"
    return dp_type


def cloud_platform_for_dp(code: str, dp_type: str, access_mode: str):
    """Choose Home Assistant platform for a cloud DP definition."""
    if dp_type == "enum":
        if "w" in access_mode:
            return Platform.SELECT
        return Platform.SENSOR

    if dp_type == "value":
        if "w" in access_mode and not is_measurement_code(code):
            return Platform.NUMBER
        return Platform.SENSOR

    return None


def is_measurement_code(code: str) -> bool:
    """Return whether a value code is a measurement even if cloud marks it writable."""
    code = code.lower()
    return any(
        token in code
        for token in (
            "current",
            "humidity",
            "temperature",
            "temp_current",
            "battery_percentage",
            "battery_value",
            "illuminance",
            "lux",
            "moisture",
            "ph_current",
            "ec_current",
        )
    ) and not code.endswith("_set")


def cloud_entity_category(code: str, platform) -> str | None:
    """Return entity category for cloud-generated entity."""
    code = code.lower()
    if platform in (Platform.NUMBER, Platform.SELECT):
        return "config"
    if any(token in code for token in ("battery", "alarm", "fault", "status")):
        return "diagnostic"
    return "None"


def cloud_sensor_device_class(code: str, type_spec: dict):
    """Infer sensor device class from code and unit."""
    code = code.lower()
    unit = normalize_cloud_unit(type_spec.get("unit"))
    if unit in (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT) or "temp" in code:
        return SensorDeviceClass.TEMPERATURE
    if unit == PERCENTAGE and any(token in code for token in ("hum", "humidity", "moisture")):
        return SensorDeviceClass.HUMIDITY
    if "battery" in code and unit == PERCENTAGE:
        return SensorDeviceClass.BATTERY
    return None


def apply_cloud_unit(entity: dict, type_spec: dict, code: str) -> None:
    """Apply unit from cloud metadata."""
    unit = normalize_cloud_unit(type_spec.get("unit"))
    if not unit:
        return
    entity[CONF_UNIT_OF_MEASUREMENT] = unit


def apply_cloud_scale(entity: dict, type_spec: dict) -> None:
    """Apply scale factor from cloud metadata."""
    if "scale" not in type_spec:
        return
    try:
        entity[CONF_SCALING] = 1 / (10 ** int(type_spec.get("scale") or 0))
    except (TypeError, ValueError):
        return


def normalize_cloud_unit(unit):
    """Normalize Tuya cloud units to Home Assistant units."""
    if unit is None:
        return None
    unit = str(unit).strip()
    if unit in {"℃", "˚C", "°C", "C"}:
        return UnitOfTemperature.CELSIUS
    if unit in {"℉", "˚F", "°F", "F"}:
        return UnitOfTemperature.FAHRENHEIT
    if unit == "%":
        return PERCENTAGE
    return unit


def cloud_friendly_name(code: str) -> str:
    """Return readable entity name from cloud DP code."""
    overrides = {
        "temp_current": "Temperature",
        "temp_current_f": "Temperature F",
        "humidity": "Humidity",
        "battery_state": "Battery Level",
        "battery_percentage": "Battery",
        "temp_unit_convert": "Temperature Unit",
        "temp_alarm": "Temperature Alarm",
        "hum_alarm": "Humidity Alarm",
        "maxtemp_set": "Max Temperature",
        "minitemp_set": "Min Temperature",
        "maxhum_set": "Max Humidity",
        "minihum_set": "Min Humidity",
        "temp_sensitivity": "Temperature Sensitivity",
        "hum_sensitivity": "Humidity Sensitivity",
        "report_sensitivity": "Report Period",
    }
    return overrides.get(code, code.replace("_", " ").title())


def cloud_option_name(option) -> str:
    """Return readable option name."""
    option = str(option)
    overrides = {
        "c": "Celsius",
        "f": "Fahrenheit",
        "low": "Low",
        "middle": "Middle",
        "high": "High",
        "loweralarm": "Lower Alarm",
        "upperalarm": "Upper Alarm",
        "cancel": "Cancel",
    }
    return overrides.get(option, option.replace("_", " ").title())

def extend_detected_dps_with_cloud_data(detected_dps: list, dps_data: dict) -> list:
    """Add cloud-only DP definitions to detected DPS strings."""
    extended_dps = list(detected_dps)
    detected_ids = {str(dp_data).split(" ")[0] for dp_data in extended_dps}

    for dp_id, dp_data in dps_data.items():
        dp_id = str(dp_id)
        if dp_id in detected_ids or not isinstance(dp_data, dict):
            continue

        dp_code = dp_data.get("code")
        if not dp_code:
            continue

        extended_dps.append(format_cloud_dp(dp_id, dp_code, dp_data.get("value")))
        detected_ids.add(dp_id)

    return extended_dps


def format_cloud_dp(dp_id: str, dp_code: str, value) -> str:
    """Return a DPS string compatible with the existing entity matcher."""
    return f"{dp_id} ( code: {dp_code} , value: {value} )"


def parse_enum(dp_code: Enum) -> str:
    """Get enum value if code type is enum"""
    try:
        parsed_dp_code = dp_code.value
    except:
        parsed_dp_code = dp_code

    return parsed_dp_code


def get_dp_values(dp: str, dps_data: dict, req_info: CLOUD_VALUE = None) -> dict:
    """Get DP Values"""
    if not dp or not dps_data:
        return

    dp_data = dps_data.get(dp, {})
    dp_values = dp_data.get("values")
    dp_type = dp_data.get("type", "").capitalize()

    if not dp_values or not (dp_values := json.loads(dp_values)):
        return

    # Some DPS doesn't have the type, in high level data.
    if not dp_type and (_type := dp_values.get("type")):
        dp_type = _type.capitalize()
        # Fix type names.
        dp_type = DPType.INTEGER if dp_type == "Value" else dp_type

    # Integer values: min, max, scale, step
    if dp_values and dp_type == DPType.INTEGER:
        # We only need the scaling factor, other values will be scaled from via later on.
        # dp_values["min"] = scale(dp_values.get("min"), val_scale)
        valid_type = req_info.prefer_type and req_info.prefer_type in (str, float, int)
        pref_type = req_info.prefer_type if valid_type else int
        val_scale = dp_values.get("scale", 1)
        dp_values["min"] = pref_type(dp_values.get("min"))
        dp_values["max"] = pref_type(dp_values.get("max"))
        dp_values["step"] = pref_type(dp_values.get("step"))

        pref_type = req_info.prefer_type if valid_type else float
        dp_values["scale"] = pref_type(scale(1, val_scale, float))

        # Scale if requested.
        if req_info.scale:
            for v in ("min", "max", "step"):
                value = dp_values[v]
                dp_values[v] = pref_type(scale(value, val_scale))

        return dp_values

    # ENUM Values: range: list of values.
    if dp_values and dp_type == DPType.ENUM:
        range_values = dp_values.get("range", [])

        dp_values["min"] = range_values[0] if range_values else 0  # first value
        dp_values["max"] = range_values[-1] if range_values else 0  # Last value
        dp_values["range"] = convert_list(range_values, req_info)
        return dp_values

    # Sensors don't have type
    if dp_values and not dp_type:
        # we need scaling factor for sensors.
        if "scale" in dp_values:
            dp_values["scale"] = scale(1, dp_values["scale"], float)
            return dp_values


def scale(value: int, scale: int, _type: type = int) -> float:
    """Return scaled value."""
    value = _type(value) / (10**scale)
    if value.is_integer():
        value = int(value)
    return value


def convert_list(_list: list, req_info: CLOUD_VALUE):
    """Return list to dict values."""
    if not _list:
        return []

    prefer_type = req_info.prefer_type

    if prefer_type == str:
        # Return str "value1,value2,value3"
        to_str = ",".join(str(v) for v in _list)
        return to_str

    if prefer_type == dict:
        # Return dict {value_1: Value 1, value_2: Value 2, value_3: Value 3}
        to_dict = {}
        for k in _list:
            if k.lower() in req_info.remap_values:
                k_name = req_info.remap_values.get(k.lower())
            else:
                # k_name = k.replace("_", " ").capitalize()  # Default name
                k_name = k  # Default name
                if isinstance(req_info.default_value, dict):
                    k_name = req_info.default_value.get(k, k_name)

            if req_info.reverse_dict:
                to_dict.update({k_name: k})
            else:
                to_dict.update({k: k_name})
        return to_dict

    # otherwise return prefer type list
    return _list


def convert_to_kelvin(value):
    """Convert Tuya color temperature to kelvin"""
    # Given data points
    v0, k0 = 0, 2700  # (0, 2700)
    v1, k1 = 1000, 6500  # (1000, 6500)

    # Calculate slope (m) and y-intercept (b) using the given points
    m = (k1 - k0) / (v1 - v0)
    b = k0 - m * v0

    # Use the linear equation to calculate the color temperature (K)
    kelvin = m * value + b

    return kelvin
