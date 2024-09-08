"""Support for OpenTelemetry metrics export."""

import logging
from typing import Any, Sequence, Optional

from opentelemetry.metrics import Counter, ObservableGauge, Instrument, Meter, UpDownCounter, CallbackT, Observation

from homeassistant import core as hacore
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODES,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    HVACAction,
)
from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
)
from homeassistant.components.fan import (
    ATTR_DIRECTION,
    ATTR_OSCILLATING,
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
)
from homeassistant.components.humidifier import ATTR_AVAILABLE_MODES, ATTR_HUMIDITY
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_MODE,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_CUSTOM_BYPASS,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMED_NIGHT,
    STATE_ALARM_ARMED_VACATION,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_DISARMING,
    STATE_ALARM_PENDING,
    STATE_ALARM_TRIGGERED,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_ON,
    STATE_OPEN,
    STATE_OPENING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import Event, EventStateChangedData, State
from homeassistant.helpers.entity_registry import EventEntityRegistryUpdatedData

_LOGGER = logging.getLogger(__name__)


class OpenTelemetryMetrics:
    def __init__(
        self,
        meter: Meter,
    ) -> None:
        self._meter = meter
        self._metrics: dict[str, Instrument] = {}

    def handle_event_state_changed(self, event: Event[EventStateChangedData]) -> None:
        _LOGGER.info("handle_event_state_changed\n" + event)

        if (state := event.data.get("new_state")) is None:
            return

    def handle_state(self, state: State) -> None:
        """Add/update a state in OpenTelemetry."""

        entity_id = state.entity_id
        _LOGGER.debug("Handling state update for %s", entity_id)
        domain, _ = hacore.split_entity_id(entity_id)

        ignored_states = (STATE_UNAVAILABLE, STATE_UNKNOWN)

        handler = f"_handle_{domain}"

        if hasattr(self, handler) and state.state not in ignored_states:
            getattr(self, handler)(state)

        # TODO define attributes type somewhere if needed
        attributes = self._default_attributes(state)

        state_changed = self._counter(
            "state_change", None, "The number of state changes"
        )
        state_changed.add(1, attributes)

        # state_change = self._metric(
        #     "state_change", OpenTelemetryMetricType.COUNTER, "The number of state changes"
        # )
        # state_change.labels(**attributes).inc()

        # TODO this is basically an up metric, this is not how it's usually done in OTel
        def entity_available_callback():
            yield Observation(float(state.state not in ignored_states), attributes)

        entity_available = self._observable_gauge(
            "entity_available",
            [entity_available_callback],
            None,
            "Entity is available (not in the unavailable or unknown state)",
        )
        entity_available.set(float(state.state not in ignored_states))
        entity_available.labels(**attributes).set(
            float(state.state not in ignored_states)
        )

        # TODO is this helpful? Seems like were sending timestamps...
        # last_updated_time_seconds = self._metric(
        #     "last_updated_time_seconds",
        #     prometheus_client.Gauge,
        #     "The last_updated timestamp",
        # )
        # last_updated_time_seconds.labels(**attributes).set(state.last_updated.timestamp())
        # pass

    # def _remove_labelsets(
    #     self, entity_id: str, friendly_name: str | None = None
    # ) -> None:
    #     """Remove labelsets matching the given entity id from all metrics."""
    #     for metric in list(self._metrics.values()):
    #         for sample in cast(list[prometheus_client.Metric], metric.collect())[
    #             0
    #         ].samples:
    #             if sample.labels["entity"] == entity_id and (
    #                 not friendly_name or sample.labels["friendly_name"] == friendly_name
    #             ):
    #                 _LOGGER.debug(
    #                     "Removing labelset from %s for entity_id: %s",
    #                     sample.name,
    #                     entity_id,
    #                 )
    #                 with suppress(KeyError):
    #                     metric.remove(*sample.labels.values())

    # def _handle_attributes(self, state: State) -> None:
    #     for key, value in state.attributes.items():
    #         metric = self._metric(
    #             f"{state.domain}_attr_{key.lower()}",
    #             prometheus_client.Gauge,
    #             f"{key} attribute of {state.domain} entity",
    #         )
    #
    #         try:
    #             value = float(value)
    #             metric.labels(**self._labels(state)).set(value)
    #         except (ValueError, TypeError):
    #             pass

    def _counter(
        self,
        metric_name: str,
        unit: str = None,
        description: str = None,
    ) -> Counter:
        sanitized_name = self._sanitize_metric_name(metric_name)
        if sanitized_name not in self._metrics:
            self._metrics[sanitized_name] = self._meter.create_counter(
                metric_name, unit, description
            )

        return self._metrics[sanitized_name]

    def _up_down_counter(
        self,
        metric_name: str,
        unit: str = None,
        description: str = None,
    ) -> UpDownCounter:
        sanitized_name = self._sanitize_metric_name(metric_name)
        if sanitized_name not in self._metrics:
            self._metrics[sanitized_name] = self._meter.create_up_down_counter(
                metric_name, unit, description
            )

        return self._metrics[sanitized_name]

    # TODO figure this out
    def _observable_gauge(
            self,
            metric_name: str,
            callbacks: Optional[Sequence[CallbackT]] = None,
            unit: str = None,
            description: str = None,
    ) -> ObservableGauge:
        sanitized_name = self._sanitize_metric_name(metric_name)
        if sanitized_name not in self._metrics:
            # self._meter.create_gauge()
            self._metrics[sanitized_name] = self._meter.create_observable_gauge(metric_name, callbacks, unit, description)
            # self._metrics[sanitized_name] = self._meter.create_gauge(metric_name, description, unit)

        return self._metrics[sanitized_name]

    # def _gauge(
    #     self,
    #     metric_name: str,
    #     unit: str = None,
    #     description: str = None,
    # ) -> ObservableGauge:
    #     sanitized_name = self._sanitize_metric_name(metric_name)
    #     if sanitized_name not in self._metrics:
    #         self._metrics[sanitized_name] = self._meter.create_gauge(
    #             metric_name, unit, description
    #         )
    #
    #     return self._metrics[sanitized_name]

    # def _metric(
    #         self,
    #         metric_name: str,
    #         description: str,
    #         # TODO unit
    #         extra_labels: list[str] | None = None,
    # ) -> Counter:
    #     labels = ["entity", "friendly_name", "domain"]
    #     if extra_labels is not None:
    #         labels.extend(extra_labels)
    #
    #     try:
    #         return cast(_MetricBaseT, self._metrics[metric_name])
    #     except KeyError:
    #         full_metric_name = self._sanitize_metric_name(
    #             f"{self.metrics_prefix}{metric_name}"
    #         )
    #         self._metrics[metric_name] = factory(
    #             full_metric_name,
    #             description,
    #             labels,
    #             registry=prometheus_client.REGISTRY,
    #         )
    #         return cast(_MetricBaseT, self._metrics[metric_name])

    # @staticmethod
    # def _sanitize_metric_name(metric: str) -> str:
    #     return "".join(
    #         [
    #             c
    #             if c in string.ascii_letters + string.digits + "_:"
    #             else f"u{hex(ord(c))}"
    #             for c in metric
    #         ]
    #     )
    #
    # @staticmethod
    # def state_as_number(state: State) -> float:
    #     """Return a state casted to a float."""
    #     try:
    #         if state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.TIMESTAMP:
    #             value = as_timestamp(state.state)
    #         else:
    #             value = state_helper.state_as_number(state)
    #     except ValueError:
    #         _LOGGER.debug("Could not convert %s to float", state)
    #         value = 0
    #     return value
    #
    # @staticmethod
    # def _default_attributes(state: State) -> dict[str, Any]:
    #     return {
    #         "entity": state.entity_id,
    #         "domain": state.domain,
    #         "friendly_name": state.attributes.get(ATTR_FRIENDLY_NAME),
    #     }
    #
    # def handle_entity_registry_updated(
    #     self, event: Event[EventEntityRegistryUpdatedData]
    # ) -> None:
    #     pass
    #
    # def _battery(self, state: State) -> None:
    #     if (battery_level := state.attributes.get(ATTR_BATTERY_LEVEL)) is not None:
    #         metric = self._metric(
    #             "battery_level_percent",
    #             prometheus_client.Gauge,
    #             "Battery level as a percentage of its capacity",
    #         )
    #         try:
    #             value = float(battery_level)
    #             metric.labels(**self._default_attributes(state)).set(value)
    #         except ValueError:
    #             pass
    #
    # def _handle_binary_sensor(self, state: State) -> None:
    #     metric = self._metric(
    #         "binary_sensor_state",
    #         prometheus_client.Gauge,
    #         "State of the binary sensor (0/1)",
    #     )
    #     value = self.state_as_number(state)
    #     metric.labels(**self._default_attributes(state)).set(value)
    #
    # def _handle_input_boolean(self, state: State) -> None:
    #     metric = self._metric(
    #         "input_boolean_state",
    #         prometheus_client.Gauge,
    #         "State of the input boolean (0/1)",
    #     )
    #     value = self.state_as_number(state)
    #     metric.labels(**self._default_attributes(state)).set(value)
    #
    # def _numeric_handler(self, state: State, domain: str, title: str) -> None:
    #     if unit := self._unit_string(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)):
    #         metric = self._metric(
    #             f"{domain}_state_{unit}",
    #             prometheus_client.Gauge,
    #             f"State of the {title} measured in {unit}",
    #         )
    #     else:
    #         metric = self._metric(
    #             f"{domain}_state",
    #             prometheus_client.Gauge,
    #             f"State of the {title}",
    #         )
    #
    #     with suppress(ValueError):
    #         value = self.state_as_number(state)
    #         if (
    #             state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    #             == UnitOfTemperature.FAHRENHEIT
    #         ):
    #             value = TemperatureConverter.convert(
    #                 value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
    #             )
    #         metric.labels(**self._default_attributes(state)).set(value)
    #
    # def _handle_input_number(self, state: State) -> None:
    #     self._numeric_handler(state, "input_number", "input number")
    #
    # def _handle_number(self, state: State) -> None:
    #     self._numeric_handler(state, "number", "number")
    #
    # def _handle_device_tracker(self, state: State) -> None:
    #     metric = self._metric(
    #         "device_tracker_state",
    #         prometheus_client.Gauge,
    #         "State of the device tracker (0/1)",
    #     )
    #     value = self.state_as_number(state)
    #     metric.labels(**self._default_attributes(state)).set(value)
    #
    # def _handle_person(self, state: State) -> None:
    #     metric = self._metric(
    #         "person_state", prometheus_client.Gauge, "State of the person (0/1)"
    #     )
    #     value = self.state_as_number(state)
    #     metric.labels(**self._default_attributes(state)).set(value)
    #
    # def _handle_cover(self, state: State) -> None:
    #     metric = self._metric(
    #         "cover_state",
    #         prometheus_client.Gauge,
    #         "State of the cover (0/1)",
    #         ["state"],
    #     )
    #
    #     cover_states = [STATE_CLOSED, STATE_CLOSING, STATE_OPEN, STATE_OPENING]
    #     for cover_state in cover_states:
    #         metric.labels(
    #             **dict(self._default_attributes(state), state=cover_state)
    #         ).set(float(cover_state == state.state))
    #
    #     position = state.attributes.get(ATTR_CURRENT_POSITION)
    #     if position is not None:
    #         position_metric = self._metric(
    #             "cover_position",
    #             prometheus_client.Gauge,
    #             "Position of the cover (0-100)",
    #         )
    #         position_metric.labels(**self._default_attributes(state)).set(
    #             float(position)
    #         )
    #
    #     tilt_position = state.attributes.get(ATTR_CURRENT_TILT_POSITION)
    #     if tilt_position is not None:
    #         tilt_position_metric = self._metric(
    #             "cover_tilt_position",
    #             prometheus_client.Gauge,
    #             "Tilt Position of the cover (0-100)",
    #         )
    #         tilt_position_metric.labels(**self._default_attributes(state)).set(
    #             float(tilt_position)
    #         )
    #
    # def _handle_light(self, state: State) -> None:
    #     metric = self._metric(
    #         "light_brightness_percent",
    #         prometheus_client.Gauge,
    #         "Light brightness percentage (0..100)",
    #     )
    #
    #     try:
    #         brightness = state.attributes.get(ATTR_BRIGHTNESS)
    #         if state.state == STATE_ON and brightness is not None:
    #             value = brightness / 255.0
    #         else:
    #             value = self.state_as_number(state)
    #         value = value * 100
    #         metric.labels(**self._default_attributes(state)).set(value)
    #     except ValueError:
    #         pass
    #
    # def _handle_lock(self, state: State) -> None:
    #     metric = self._metric(
    #         "lock_state", prometheus_client.Gauge, "State of the lock (0/1)"
    #     )
    #     value = self.state_as_number(state)
    #     metric.labels(**self._default_attributes(state)).set(value)
    #
    # def _handle_climate_temp(
    #     self, state: State, attr: str, metric_name: str, metric_description: str
    # ) -> None:
    #     if (temp := state.attributes.get(attr)) is not None:
    #         if self._climate_units == UnitOfTemperature.FAHRENHEIT:
    #             temp = TemperatureConverter.convert(
    #                 temp, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
    #             )
    #         metric = self._metric(
    #             metric_name,
    #             prometheus_client.Gauge,
    #             metric_description,
    #         )
    #         metric.labels(**self._default_attributes(state)).set(temp)
    #
    # def _handle_climate(self, state: State) -> None:
    #     self._handle_climate_temp(
    #         state,
    #         ATTR_TEMPERATURE,
    #         "climate_target_temperature_celsius",
    #         "Target temperature in degrees Celsius",
    #     )
    #     self._handle_climate_temp(
    #         state,
    #         ATTR_TARGET_TEMP_HIGH,
    #         "climate_target_temperature_high_celsius",
    #         "Target high temperature in degrees Celsius",
    #     )
    #     self._handle_climate_temp(
    #         state,
    #         ATTR_TARGET_TEMP_LOW,
    #         "climate_target_temperature_low_celsius",
    #         "Target low temperature in degrees Celsius",
    #     )
    #     self._handle_climate_temp(
    #         state,
    #         ATTR_CURRENT_TEMPERATURE,
    #         "climate_current_temperature_celsius",
    #         "Current temperature in degrees Celsius",
    #     )
    #
    #     if current_action := state.attributes.get(ATTR_HVAC_ACTION):
    #         metric = self._metric(
    #             "climate_action",
    #             prometheus_client.Gauge,
    #             "HVAC action",
    #             ["action"],
    #         )
    #         for action in HVACAction:
    #             metric.labels(
    #                 **dict(self._default_attributes(state), action=action.value)
    #             ).set(float(action == current_action))
    #
    #     current_mode = state.state
    #     available_modes = state.attributes.get(ATTR_HVAC_MODES)
    #     if current_mode and available_modes:
    #         metric = self._metric(
    #             "climate_mode",
    #             prometheus_client.Gauge,
    #             "HVAC mode",
    #             ["mode"],
    #         )
    #         for mode in available_modes:
    #             metric.labels(**dict(self._default_attributes(state), mode=mode)).set(
    #                 float(mode == current_mode)
    #             )
    #
    #     preset_mode = state.attributes.get(ATTR_PRESET_MODE)
    #     available_preset_modes = state.attributes.get(ATTR_PRESET_MODES)
    #     if preset_mode and available_preset_modes:
    #         preset_metric = self._metric(
    #             "climate_preset_mode",
    #             prometheus_client.Gauge,
    #             "Preset mode enum",
    #             ["mode"],
    #         )
    #         for mode in available_preset_modes:
    #             preset_metric.labels(
    #                 **dict(self._default_attributes(state), mode=mode)
    #             ).set(float(mode == preset_mode))
    #
    #     fan_mode = state.attributes.get(ATTR_FAN_MODE)
    #     available_fan_modes = state.attributes.get(ATTR_FAN_MODES)
    #     if fan_mode and available_fan_modes:
    #         fan_mode_metric = self._metric(
    #             "climate_fan_mode",
    #             prometheus_client.Gauge,
    #             "Fan mode enum",
    #             ["mode"],
    #         )
    #         for mode in available_fan_modes:
    #             fan_mode_metric.labels(
    #                 **dict(self._default_attributes(state), mode=mode)
    #             ).set(float(mode == fan_mode))
    #
    # def _handle_humidifier(self, state: State) -> None:
    #     humidifier_target_humidity_percent = state.attributes.get(ATTR_HUMIDITY)
    #     if humidifier_target_humidity_percent:
    #         metric = self._metric(
    #             "humidifier_target_humidity_percent",
    #             prometheus_client.Gauge,
    #             "Target Relative Humidity",
    #         )
    #         metric.labels(**self._default_attributes(state)).set(
    #             humidifier_target_humidity_percent
    #         )
    #
    #     metric = self._metric(
    #         "humidifier_state",
    #         prometheus_client.Gauge,
    #         "State of the humidifier (0/1)",
    #     )
    #     try:
    #         value = self.state_as_number(state)
    #         metric.labels(**self._default_attributes(state)).set(value)
    #     except ValueError:
    #         pass
    #
    #     current_mode = state.attributes.get(ATTR_MODE)
    #     available_modes = state.attributes.get(ATTR_AVAILABLE_MODES)
    #     if current_mode and available_modes:
    #         metric = self._metric(
    #             "humidifier_mode",
    #             prometheus_client.Gauge,
    #             "Humidifier Mode",
    #             ["mode"],
    #         )
    #         for mode in available_modes:
    #             metric.labels(**dict(self._default_attributes(state), mode=mode)).set(
    #                 float(mode == current_mode)
    #             )
    #
    # def _handle_sensor(self, state: State) -> None:
    #     unit = self._unit_string(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT))
    #
    #     for metric_handler in self._sensor_metric_handlers:
    #         metric = metric_handler(state, unit)
    #         if metric is not None:
    #             break
    #
    #     if metric is not None:
    #         documentation = "State of the sensor"
    #         if unit:
    #             documentation = f"Sensor data measured in {unit}"
    #
    #         _metric = self._metric(metric, prometheus_client.Gauge, documentation)
    #
    #         try:
    #             value = self.state_as_number(state)
    #             if (
    #                 state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    #                 == UnitOfTemperature.FAHRENHEIT
    #             ):
    #                 value = TemperatureConverter.convert(
    #                     value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
    #                 )
    #             _metric.labels(**self._default_attributes(state)).set(value)
    #         except ValueError:
    #             pass
    #
    #     self._battery(state)
    #
    # def _sensor_default_metric(self, state: State, unit: str | None) -> str | None:
    #     """Get default metric."""
    #     return self._default_metric
    #
    # @staticmethod
    # def _sensor_attribute_metric(state: State, unit: str | None) -> str | None:
    #     """Get metric based on device class attribute."""
    #     metric = state.attributes.get(ATTR_DEVICE_CLASS)
    #     if metric is not None:
    #         return f"sensor_{metric}_{unit}"
    #     return None
    #
    # @staticmethod
    # def _sensor_timestamp_metric(state: State, unit: str | None) -> str | None:
    #     """Get metric for timestamp sensors, which have no unit of measurement attribute."""
    #     metric = state.attributes.get(ATTR_DEVICE_CLASS)
    #     if metric == SensorDeviceClass.TIMESTAMP:
    #         return f"sensor_{metric}_seconds"
    #     return None
    #
    # def _sensor_override_metric(self, state: State, unit: str | None) -> str | None:
    #     """Get metric from override in configuration."""
    #     if self._override_metric:
    #         return self._override_metric
    #     return None
    #
    # def _sensor_override_component_metric(
    #     self, state: State, unit: str | None
    # ) -> str | None:
    #     """Get metric from override in component confioguration."""
    #     return self._component_config.get(state.entity_id).get(CONF_OVERRIDE_METRIC)
    #
    # @staticmethod
    # def _sensor_fallback_metric(state: State, unit: str | None) -> str | None:
    #     """Get metric from fallback logic for compatibility."""
    #     if unit in (None, ""):
    #         try:
    #             state_helper.state_as_number(state)
    #         except ValueError:
    #             _LOGGER.debug("Unsupported sensor: %s", state.entity_id)
    #             return None
    #         return "sensor_state"
    #     return f"sensor_unit_{unit}"
    #
    # @staticmethod
    # def _unit_string(unit: str | None) -> str | None:
    #     """Get a formatted string of the unit."""
    #     if unit is None:
    #         return None
    #
    #     units = {
    #         UnitOfTemperature.CELSIUS: "celsius",
    #         UnitOfTemperature.FAHRENHEIT: "celsius",  # F should go into C metric
    #         PERCENTAGE: "percent",
    #     }
    #     default = unit.replace("/", "_per_")
    #     default = default.lower()
    #     return units.get(unit, default)
    #
    # def _handle_switch(self, state: State) -> None:
    #     metric = self._metric(
    #         "switch_state", prometheus_client.Gauge, "State of the switch (0/1)"
    #     )
    #
    #     try:
    #         value = self.state_as_number(state)
    #         metric.labels(**self._default_attributes(state)).set(value)
    #     except ValueError:
    #         pass
    #
    #     self._handle_attributes(state)
    #
    # def _handle_fan(self, state: State) -> None:
    #     metric = self._metric(
    #         "fan_state", prometheus_client.Gauge, "State of the fan (0/1)"
    #     )
    #
    #     try:
    #         value = self.state_as_number(state)
    #         metric.labels(**self._default_attributes(state)).set(value)
    #     except ValueError:
    #         pass
    #
    #     fan_speed_percent = state.attributes.get(ATTR_PERCENTAGE)
    #     if fan_speed_percent is not None:
    #         fan_speed_metric = self._metric(
    #             "fan_speed_percent",
    #             prometheus_client.Gauge,
    #             "Fan speed percent (0-100)",
    #         )
    #         fan_speed_metric.labels(**self._default_attributes(state)).set(
    #             float(fan_speed_percent)
    #         )
    #
    #     fan_is_oscillating = state.attributes.get(ATTR_OSCILLATING)
    #     if fan_is_oscillating is not None:
    #         fan_oscillating_metric = self._metric(
    #             "fan_is_oscillating",
    #             prometheus_client.Gauge,
    #             "Whether the fan is oscillating (0/1)",
    #         )
    #         fan_oscillating_metric.labels(**self._default_attributes(state)).set(
    #             float(fan_is_oscillating)
    #         )
    #
    #     fan_preset_mode = state.attributes.get(ATTR_PRESET_MODE)
    #     available_modes = state.attributes.get(ATTR_PRESET_MODES)
    #     if fan_preset_mode and available_modes:
    #         fan_preset_metric = self._metric(
    #             "fan_preset_mode",
    #             prometheus_client.Gauge,
    #             "Fan preset mode enum",
    #             ["mode"],
    #         )
    #         for mode in available_modes:
    #             fan_preset_metric.labels(
    #                 **dict(self._default_attributes(state), mode=mode)
    #             ).set(float(mode == fan_preset_mode))
    #
    #     fan_direction = state.attributes.get(ATTR_DIRECTION)
    #     if fan_direction is not None:
    #         fan_direction_metric = self._metric(
    #             "fan_direction_reversed",
    #             prometheus_client.Gauge,
    #             "Fan direction reversed (bool)",
    #         )
    #         if fan_direction == DIRECTION_FORWARD:
    #             fan_direction_metric.labels(**self._default_attributes(state)).set(0)
    #         elif fan_direction == DIRECTION_REVERSE:
    #             fan_direction_metric.labels(**self._default_attributes(state)).set(1)
    #
    # def _handle_zwave(self, state: State) -> None:
    #     self._battery(state)
    #
    # def _handle_automation(self, state: State) -> None:
    #     metric = self._metric(
    #         "automation_triggered_count",
    #         prometheus_client.Counter,
    #         "Count of times an automation has been triggered",
    #     )
    #
    #     metric.labels(**self._default_attributes(state)).inc()
    #
    # def _handle_counter(self, state: State) -> None:
    #     metric = self._metric(
    #         "counter_value",
    #         prometheus_client.Gauge,
    #         "Value of counter entities",
    #     )
    #
    #     metric.labels(**self._default_attributes(state)).set(
    #         self.state_as_number(state)
    #     )
    #
    # def _handle_update(self, state: State) -> None:
    #     metric = self._metric(
    #         "update_state",
    #         prometheus_client.Gauge,
    #         "Update state, indicating if an update is available (0/1)",
    #     )
    #     value = self.state_as_number(state)
    #     metric.labels(**self._default_attributes(state)).set(value)
    #
    # def _handle_alarm_control_panel(self, state: State) -> None:
    #     current_state = state.state
    #
    #     if current_state:
    #         metric = self._metric(
    #             "alarm_control_panel_state",
    #             prometheus_client.Gauge,
    #             "State of the alarm control panel (0/1)",
    #             ["state"],
    #         )
    #
    #         alarm_states = [
    #             STATE_ALARM_ARMED_AWAY,
    #             STATE_ALARM_ARMED_CUSTOM_BYPASS,
    #             STATE_ALARM_ARMED_HOME,
    #             STATE_ALARM_ARMED_NIGHT,
    #             STATE_ALARM_ARMED_VACATION,
    #             STATE_ALARM_DISARMED,
    #             STATE_ALARM_TRIGGERED,
    #             STATE_ALARM_PENDING,
    #             STATE_ALARM_ARMING,
    #             STATE_ALARM_DISARMING,
    #         ]
    #
    #         for alarm_state in alarm_states:
    #             metric.labels(
    #                 **dict(self._default_attributes(state), state=alarm_state)
    #             ).set(float(alarm_state == current_state))
