"""Coordinator for ES Énergies integration in Home Assistant."""

import datetime
import logging
from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import EsEnergiesClient
from .const import DOMAIN, SCAN_INTERVAL_MINUTES, CONF_DEVICE_COOKIES, CONF_SITE_ID, CONF_PERSON_ID

_LOGGER = logging.getLogger(__name__)


class EsEnergiesCoordinator(DataUpdateCoordinator):
    """Coordinator to poll ES Énergies API periodically."""

    def __init__(self, hass: HomeAssistant, client: EsEnergiesClient, entry: ConfigEntry = None):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self) -> dict:
        """Fetch data from ES Énergies API."""
        try:
            data = await self.client.async_get_data()
            data["last_updated"] = datetime.datetime.now(datetime.timezone.utc)
            if self.entry is not None:
                new_data = {
                    **self.entry.data,
                    CONF_SITE_ID: self.client.site_id,
                    CONF_PERSON_ID: self.client.person_id,
                    CONF_DEVICE_COOKIES: self.client.device_cookies,
                    "access_token": self.client.access_token,
                    "expires_at": self.client.expires_at.isoformat() if self.client.expires_at else None,
                    "customer_name": self.client.customer_name,
                }
                if new_data != self.entry.data:
                    self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return data
        except Exception as err:
            _LOGGER.exception("Error communicating with ES Énergies API: %s", err)
            raise UpdateFailed(f"Error communicating with ES Énergies API: {err}") from err

