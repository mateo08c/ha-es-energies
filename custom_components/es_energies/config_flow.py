"""Config flow for ES Énergies integration."""

import logging
import voluptuous as vol
from aiohttp import ClientSession
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import (
    EsEnergiesClient,
    TwoFactorRequiredException,
    AuthenticationFailedException,
)
from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_2FA_CODE,
    CONF_SITE_ID,
    CONF_PERSON_ID,
    CONF_DEVICE_COOKIES,
)

_LOGGER = logging.getLogger(__name__)


class EsEnergiesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ES Énergies."""

    VERSION = 1

    def __init__(self):
        self._email = None
        self._password = None
        self._client = None
        self._action_url_2fa = None

    async def async_step_user(self, user_input=None):
        """Step 1: User enters email and password."""
        errors = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]

            # Check if site is already configured
            await self.async_set_unique_id(self._email.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass, verify_ssl=False)
            self._client = EsEnergiesClient(session, self._email, self._password)

            try:
                await self._client.authenticate()
                # If authentication succeeded without 2FA, show account summary
                return await self.async_step_account_info()
            except TwoFactorRequiredException as exc:
                # Need 2FA code step
                self._action_url_2fa = exc.action_url
                return await self.async_step_2fa()
            except AuthenticationFailedException as err:
                _LOGGER.warning("Authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception("Unexpected exception during login: %s", err)
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_2fa(self, user_input=None):
        """Step 2: User enters the 6-digit email code."""
        errors = {}

        if user_input is not None:
            code = user_input[CONF_2FA_CODE]
            try:
                await self._client.submit_2fa(self._action_url_2fa, code)
                return await self.async_step_account_info()
            except AuthenticationFailedException as err:
                _LOGGER.warning("2FA submission failed: %s", err)
                errors["base"] = "invalid_2fa"
            except Exception as err:
                _LOGGER.exception("Unexpected error during 2FA: %s", err)
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_2FA_CODE): str,
            }
        )

        return self.async_show_form(
            step_id="2fa",
            data_schema=schema,
            errors=errors,
            description_placeholders={"email": self._email},
        )

    async def async_step_account_info(self, user_input=None):
        """Step 3: Display retrieved account & Linky meter summary before finalizing."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._client.get_entry_title(),
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_SITE_ID: self._client.site_id,
                    CONF_PERSON_ID: self._client.person_id,
                    CONF_DEVICE_COOKIES: self._client.device_cookies,
                    "access_token": self._client.access_token,
                    "expires_at": self._client.expires_at.isoformat() if self._client.expires_at else None,
                    "customer_name": self._client.customer_name,
                },
            )

        info = self._client.get_account_summary()
        return self.async_show_form(
            step_id="account_info",
            data_schema=vol.Schema({}),
            description_placeholders={
                "customer_name": str(info["customer_name"]),
                "email": str(info["email"]),
                "person_id": str(info["person_id"]),
                "site_id": str(info["site_id"]),
                "pdl": str(info["pdl"]),
                "address": str(info["address"]),
                "meter_type": str(info["meter_type"]),
                "tariff_option": str(info["tariff_option"]),
                "subscribed_power": str(info["subscribed_power"]),
                "gas_status": "Oui" if info["has_gas"] else "Non",
            },
        )

