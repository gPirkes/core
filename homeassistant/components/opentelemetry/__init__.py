"""The otlp-export integration."""

from __future__ import annotations

from typing import Any

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import (
    CallbackOptions,
    Meter,
    Observation,
    get_meter_provider,
    set_meter_provider,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry_metrics import OpenTelemetryMetrics
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_STATE_CHANGED,
    Platform,
    )
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED
from homeassistant.helpers.typing import ConfigType

DOMAIN = "opentelemetry"

CONF_ENDPOINT = "endpoint"
CONF_OTLP_HEADERS = "headers"
CONF_OTLP_SCOPE_NAME = "scope_name"

DEFAULT_ENDPOINT = "localhost:4318"
DEFAULT_NAMESPACE = "homeassistant"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            {
                # TODO: hass cv validation does not allow the url type to not have the protocol specified. (used for gRPC export without protocol)
                vol.Optional(CONF_ENDPOINT, default=DEFAULT_ENDPOINT): cv.string,
                vol.Optional(CONF_OTLP_SCOPE_NAME, default=DEFAULT_NAMESPACE): cv.string,
                # TODO maybe add full SDK config at some point
                # TODO export interval
                # TODO temporality preference
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    conf: dict[str, Any] = config[DOMAIN]
    endpoint = conf[CONF_ENDPOINT]

    exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
    reader = PeriodicExportingMetricReader(exporter, 3000)
    provider = MeterProvider(metric_readers=[reader])
    set_meter_provider(provider)

    # TODO get version directly from HomeAssistant
    version = "2024.9.1"
    meter = get_meter_provider().get_meter(DEFAULT_NAMESPACE, version)

    metrics = OpenTelemetryMetrics(meter)

    # TODO check if there is a way to do this async
    hass.bus.listen(EVENT_STATE_CHANGED, metrics.handle_state_changed_event)
    hass.bus.listen(
        EVENT_ENTITY_REGISTRY_UPDATED,
        metrics.handle_entity_registry_updated,
    )

    for state in hass.states.all():
        # TODO set up entity filter (not all types are useful)
        # if entity_filter(state.entity_id):
        metrics.handle_state(state)

    return True


# TODO Remove if the integration does not have an options flow
async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, (Platform.SENSOR,))
