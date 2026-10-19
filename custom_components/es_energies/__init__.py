"""The ES Énergies integration setup."""

import datetime
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import EsEnergiesClient
from .coordinator import EsEnergiesCoordinator
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SITE_ID,
    CONF_PERSON_ID,
    CONF_DEVICE_COOKIES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ES Énergies from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass, verify_ssl=False)
    device_cookies = entry.data.get(CONF_DEVICE_COOKIES, {})
    expires_at = None
    if entry.data.get("expires_at"):
        try:
            expires_at = datetime.datetime.fromisoformat(entry.data["expires_at"])
        except ValueError:
            expires_at = None

    saved_name = entry.data.get("customer_name")
    saved_token = entry.data.get("access_token")

    client = EsEnergiesClient(
        session,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        device_cookies=device_cookies,
        access_token=saved_token,
        expires_at=expires_at,
        site_id=entry.data.get(CONF_SITE_ID),
        person_id=entry.data.get(CONF_PERSON_ID),
        customer_name=saved_name,
    )

    coordinator = EsEnergiesCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    # Update saved cookies and enrich entry title with account details
    new_title = client.get_entry_title()
    new_data = {
        **entry.data,
        CONF_SITE_ID: client.site_id,
        CONF_PERSON_ID: client.person_id,
        CONF_DEVICE_COOKIES: client.device_cookies,
        "access_token": client.access_token,
        "expires_at": client.expires_at.isoformat() if client.expires_at else None,
        "customer_name": client.customer_name,
    }
    if new_data != entry.data or entry.title != new_title:
        hass.config_entries.async_update_entry(entry, title=new_title, data=new_data)

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: "dr.DeviceEntry"
) -> bool:
    """Allow removing obsolete or deleted devices."""
    return True

