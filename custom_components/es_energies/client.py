"""API Client for ES Énergies (Strasbourg SuiviConso)."""

import asyncio
import datetime
import html
import json
import logging
import re
import urllib.parse
from aiohttp import ClientSession, CookieJar
from yarl import URL

_LOGGER = logging.getLogger(__name__)

SSO_COOKIE_URL = "https://espaceclient.es.fr/"
SSO_AUTH_URL = "https://espaceclient.es.fr/auth/realms/espace-client-sso/protocol/openid-connect/auth"
SITES_URL = "https://suiviconso.es.fr/authentication-oidc/openid/sites"
TOKEN_URL = "https://suiviconso.es.fr/authorization-server/oauth/token"
REDIRECT_URI = "https://suiviconso.es.fr/openid"
BASE_API_URL = "https://suiviconso.es.fr/api"

KEYCLOAK_CLIENT_ID = "MjFmMGQ3YThk"
API_CLIENT_ID = "phoo3ohgeiquu7xeevah7Oogh8Queidei5iechahc3phaidipoo5rio0AiLai3jaigohvai4pheet7poo8ui5eengu3eLeiphoh3"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class TwoFactorRequiredException(Exception):
    """Raised when Keycloak requires a 2FA verification email code."""
    def __init__(self, action_url: str):
        super().__init__("Two-factor authentication code required")
        self.action_url = action_url


class AuthenticationFailedException(Exception):
    """Raised when authentication fails."""
    pass


class EsEnergiesClient:
    """Async API client for ES Énergies."""

    PERSISTENT_COOKIE_KEYS = (
        "ESPACECLIENT.ES.FR_ID",
        "ESPACECLIENT.ES.FR_ID_LEGACY",
        "KEYCLOAK_REMEMBER_ME",
        "KEYCLOAK_IDENTITY",
        "KEYCLOAK_IDENTITY_LEGACY",
        "KEYCLOAK_SESSION",
        "KEYCLOAK_SESSION_LEGACY",
    )

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        device_cookies: dict = None,
        access_token: str = None,
        expires_at: datetime.datetime = None,
        site_id: str = None,
        person_id: str = None,
        customer_name: str = None,
    ):
        self.session = session
        self.email = email
        self.password = password
        self.device_cookies = dict(device_cookies) if device_cookies else {}
        self._transient_cookies = {}
        self.access_token = access_token
        self.id_token = None
        self.expires_at = expires_at
        self.site_id = site_id
        self.person_id = person_id
        self.customer_name = customer_name
        self.site_address_raw = None
        self.site_details = {}
        self.contract_details = {}

    def _headers(self, with_token=True) -> dict:
        h = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }
        if with_token and self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _sso_headers(self) -> dict:
        """Build headers for Keycloak SSO requests with explicit Cookie header."""
        h = self._headers(with_token=False)
        h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        merged = {**self.device_cookies, **self._transient_cookies}
        if merged:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in merged.items() if v)
        return h

    def _capture_cookies_from_response(self, resp) -> None:
        """Extract Set-Cookie headers directly to avoid aiohttp/SimpleCookie parsing issues."""
        if resp is None:
            return
        for header in resp.headers.getall("Set-Cookie", []):
            pair = header.split(";", 1)[0].strip()
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            k = k.strip()
            v = v.strip()
            if not v or v == '""' or "Max-Age=0" in header:
                self._transient_cookies.pop(k, None)
                continue
            self._transient_cookies[k] = v
            if k in self.PERSISTENT_COOKIE_KEYS:
                self.device_cookies[k] = v

    async def authenticate(self) -> None:
        """Authenticate against Keycloak, skipping 2FA if trusted-device cookie is present."""
        _LOGGER.debug("ES Énergies authenticate() starting with saved cookie keys: %s", list(self.device_cookies.keys()))
        self._transient_cookies = {}
        self.session.cookie_jar.clear_domain("espaceclient.es.fr")

        params = {
            "client_id": KEYCLOAK_CLIENT_ID,
            "response_type": "id_token",
            "scope": "openid edelia",
            "state": str(int(datetime.datetime.now().timestamp() * 1000)),
            "nonce": f"nonce-{int(datetime.datetime.now().timestamp() * 1000)}",
            "redirect_uri": REDIRECT_URI,
        }
        auth_url = f"{SSO_AUTH_URL}?{urllib.parse.urlencode(params)}"

        had_sso_identity = "KEYCLOAK_IDENTITY" in self.device_cookies or "KEYCLOAK_SESSION" in self.device_cookies

        async with self.session.get(auth_url, headers=self._sso_headers(), allow_redirects=False) as resp:
            self._capture_cookies_from_response(resp)
            if resp.status in (302, 303):
                location = resp.headers.get("Location", "")
                id_token = self._extract_id_token(location)
                if id_token:
                    await self._complete_login(id_token)
                    return

            html_text = await resp.text()

        # If silent SSO had an expired KEYCLOAK_IDENTITY and returned 200 instead of 302,
        # purge the expired KEYCLOAK_IDENTITY/SESSION cookies while keeping ESPACECLIENT.ES.FR_ID
        if had_sso_identity:
            for k in ("KEYCLOAK_IDENTITY", "KEYCLOAK_IDENTITY_LEGACY", "KEYCLOAK_SESSION", "KEYCLOAK_SESSION_LEGACY"):
                self.device_cookies.pop(k, None)
            self._transient_cookies = {}
            self.session.cookie_jar.clear_domain("espaceclient.es.fr")
            async with self.session.get(auth_url, headers=self._sso_headers(), allow_redirects=False) as resp2:
                self._capture_cookies_from_response(resp2)
                html_text = await resp2.text()

        # Parse login form
        m = re.search(r'action="([^"]+login-actions/authenticate[^"]+)"', html_text)
        if not m:
            raise AuthenticationFailedException("No authentication form action found on page")
        action_url = html.unescape(m.group(1))

        # Check if already on 2FA page
        if 'name="emailCode"' in html_text or 'id="emailCode"' in html_text:
            raise TwoFactorRequiredException(action_url)

        # Submit credentials with rememberMe=on
        form_data = {
            "username": self.email,
            "password": self.password,
            "rememberMe": "on",
            "login": "",
        }

        self.session.cookie_jar.clear_domain("espaceclient.es.fr")
        async with self.session.post(action_url, data=form_data, headers=self._sso_headers(), allow_redirects=False) as resp:
            self._capture_cookies_from_response(resp)

            if resp.status in (302, 303):
                location = resp.headers.get("Location", "")
                id_token = self._extract_id_token(location)
                if id_token:
                    await self._complete_login(id_token)
                    return

            post_text = await resp.text()
            if 'name="emailCode"' in post_text or 'id="emailCode"' in post_text:
                m_2fa = re.search(r'action="([^"]+login-actions/authenticate[^"]+)"', post_text)
                action_2fa = html.unescape(m_2fa.group(1)) if m_2fa else action_url
                raise TwoFactorRequiredException(action_2fa)

            if "kc-feedback-text" in post_text or "alert-error" in post_text:
                raise AuthenticationFailedException("Invalid username or password")

            raise AuthenticationFailedException(f"Unexpected response status: {resp.status}")

    async def submit_2fa(self, action_url: str, code: str) -> None:
        """Submit the 6-digit email verification code."""
        if self.id_token:
            await self._complete_login(self.id_token)
            return

        form_data = {
            "emailCode": code.strip(),
            "validate": "Valider",
        }
        self.session.cookie_jar.clear_domain("espaceclient.es.fr")
        async with self.session.post(action_url, data=form_data, headers=self._sso_headers(), allow_redirects=False) as resp:
            self._capture_cookies_from_response(resp)
            _LOGGER.debug("ES Énergies submit_2fa captured cookie keys: %s", list(self.device_cookies.keys()))
            if resp.status in (302, 303):
                location = resp.headers.get("Location", "")
                id_token = self._extract_id_token(location)
                if id_token:
                    await self._complete_login(id_token)
                    return
                await self.authenticate()
                if self.access_token:
                    return
            resp_text = await resp.text()
            if "emailCode" in resp_text:
                raise AuthenticationFailedException("Incorrect or expired 2FA verification code")
            raise AuthenticationFailedException(f"Unexpected 2FA response status: {resp.status}")

    def _extract_id_token(self, location: str) -> str:
        if not location or "#" not in location:
            return ""
        fragment = location.split("#", 1)[1]
        params = urllib.parse.parse_qs(fragment)
        return params.get("id_token", [""])[0]

    def _extract_name_from_id_token(self, id_token: str) -> str:
        """Decode JWT payload of id_token to extract family_name / given_name / name."""
        try:
            import base64
            parts = id_token.split(".")
            if len(parts) >= 2:
                payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
                claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                full = claims.get("name") or f"{claims.get('given_name', '')} {claims.get('family_name', '')}".strip()
                if full:
                    return full
        except Exception:
            pass
        return ""

    async def _complete_login(self, id_token: str) -> None:
        """Discover site and exchange id_token for API access_token."""
        self.id_token = id_token
        jwt_name = self._extract_name_from_id_token(id_token)

        # Discover sites
        payload = {"idToken": id_token, "offerFamily": "FO013"}
        sites_headers = self._headers(with_token=False)
        sites_headers["X-Skip-Interceptor"] = "true"
        async with self.session.post(SITES_URL, json=payload, headers=sites_headers) as resp:
            if resp.status != 200:
                raise AuthenticationFailedException(f"Site discovery failed: status {resp.status}")
            sites = await resp.json()
            if not sites:
                raise AuthenticationFailedException("No customer sites found on this account")
            primary = sites[0]
            self.site_id = primary["siteExternalId"]
            self.person_id = primary["personExternalId"]
            self.site_address_raw = primary.get("address", "")

        # Token exchange
        token_data = {
            "grant_type": "id_token",
            "id_token": id_token,
            "client_id": API_CLIENT_ID,
            "offerFamily": "FO013",
            "person_external_id": self.person_id,
            "site_external_id": self.site_id,
        }
        async with self.session.post(TOKEN_URL, data=token_data, headers=self._headers(with_token=False)) as resp:
            if resp.status != 200:
                raise AuthenticationFailedException(f"Token exchange failed: status {resp.status}")
            token_json = await resp.json()
            self.access_token = token_json["access_token"]
            token_name = token_json.get("name", "")
            if token_name and token_name != "es-portal-app":
                self.customer_name = token_name
            else:
                self.customer_name = jwt_name or self.email
            expires_in = token_json.get("expires_in", 1800)
            self.expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)

        # Fetch site & contract details immediately for account summary
        try:
            async with self.session.get(f"{BASE_API_URL}/v1/sites/-", headers=self._headers()) as resp:
                if resp.status == 200:
                    self.site_details = await resp.json()
            now = datetime.datetime.now()
            c_begin = (now - datetime.timedelta(days=365)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            c_end = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            async with self.session.get(
                f"{BASE_API_URL}/v2/sites/-/elec-contracts?beginDate={urllib.parse.quote(c_begin)}&endDate={urllib.parse.quote(c_end)}&withTariffCalendars=true",
                headers=self._headers(),
            ) as resp:
                if resp.status == 200:
                    self.contract_details = await resp.json()
        except Exception as err:
            _LOGGER.debug("Non-fatal error fetching initial site/contract summary: %s", err)

    def get_account_summary(self) -> dict:
        """Return structured account, meter, and contract information."""
        sd = self.site_details or {}
        addr = sd.get("address") or {}
        lines = [line.strip() for line in (addr.get("lines") or []) if line and line.strip()]
        zip_code = addr.get("zipCode", "")
        city = addr.get("city", "")
        street = ", ".join(lines)
        full_address = f"{street}, {zip_code} {city}".strip(", ") if (street or city) else (self.site_address_raw or "Non renseignée")

        params = sd.get("parameters") or {}
        pdl = sd.get("elecExternalId") or params.get("PRM_NUMBER") or "Non renseigné"
        meter_type = params.get("ELEC_METER_TYPE", "LINKY")
        first_com_date = params.get("METER_FIRST_COM_DATE", "")
        gas_ext_id = params.get("GAS_EXTERNAL_ID")
        has_gas = (bool(gas_ext_id) and gas_ext_id != "Non renseigné") or (params.get("isGas") == "true")
        gas_pdl = gas_ext_id if (gas_ext_id and gas_ext_id != "Non renseigné") else pdl
        gas_meter_type = params.get("GAS_METER_TYPE") or ("Gazpar" if params.get("isGas") == "true" else "Gaz")

        contracts = (self.contract_details or {}).get("contracts") or []
        c_params = contracts[-1].get("supplyContractParameters", {}) if contracts else {}
        tariff_option = c_params.get("TARIFF_OPTION", "BASE")
        tariff = c_params.get("TARIFF", "BLEU")
        subscribed_power = c_params.get("SUBSCRIBED_POWER", "6")

        cname = self.customer_name
        if not cname or cname == "es-portal-app":
            cname = self.email

        return {
            "customer_name": cname,
            "email": self.email,
            "person_id": self.person_id or "",
            "site_id": self.site_id or sd.get("externalId") or "",
            "pdl": pdl,
            "street": street,
            "zip_code": zip_code,
            "city": city,
            "address": full_address,
            "meter_type": meter_type,
            "first_com_date": first_com_date,
            "tariff_option": tariff_option,
            "tariff": tariff,
            "subscribed_power": subscribed_power,
            "has_gas": has_gas,
            "gas_pdl": gas_pdl,
            "gas_meter_type": gas_meter_type,
        }

    def get_entry_title(self) -> str:
        """Build a descriptive title for the Home Assistant config entry."""
        info = self.get_account_summary()
        name = info["customer_name"]
        pdl = info["pdl"]
        city = info["city"]
        if pdl and pdl != "Non renseigné" and city:
            return f"ES Énergies - {name} ({city} - PDL {pdl})"
        if pdl and pdl != "Non renseigné":
            return f"ES Énergies - {name} (PDL {pdl})"
        return f"ES Énergies ({self.site_id})"

    async def ensure_token_valid(self) -> None:
        """Check token expiry and refresh silently if expired."""
        if not self.access_token or not self.expires_at or datetime.datetime.now() >= self.expires_at - datetime.timedelta(minutes=2):
            await self.authenticate()

    async def async_get_data(self) -> dict:
        """Fetch all relevant sensor data in one go."""
        await self.ensure_token_valid()

        data = {}

        # 1. Site details (with automatic 401 refresh check)
        async with self.session.get(f"{BASE_API_URL}/v1/sites/-", headers=self._headers()) as resp:
            if resp.status == 401:
                await self.authenticate()
                async with self.session.get(f"{BASE_API_URL}/v1/sites/-", headers=self._headers()) as resp2:
                    if resp2.status == 200:
                        data["site_details"] = await resp2.json()
            elif resp.status == 200:
                data["site_details"] = await resp.json()

        if "site_details" in data:
            self.site_details = data["site_details"]

        # 2. Daily Consumptions (7 days)
        now = datetime.datetime.now()
        begin = (now - datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)

        # Local midnight ISO string
        begin_iso = begin.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_iso = end.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        daily_url = (
            f"{BASE_API_URL}/v2/sites/-/consumptions?"
            f"beginTs={urllib.parse.quote(begin_iso)}&endTs={urllib.parse.quote(end_iso)}&"
            f"stepUnit=DAYS&stepValue=1&withEstimated=SURROUNDING_ESTIMATED&withLoadCurveCompletion=true&isGlobalConsumptionWanted=true"
        )
        async with self.session.get(daily_url, headers=self._headers()) as resp:
            if resp.status == 200:
                data["daily"] = await resp.json()

        # 3. Monthly Consumptions (Current month)
        first_day_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first_day_next_month = (first_day_month + datetime.timedelta(days=32)).replace(day=1)
        month_begin_iso = first_day_month.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        month_end_iso = first_day_next_month.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        monthly_url = (
            f"{BASE_API_URL}/v2/sites/-/consumptions?"
            f"beginTs={urllib.parse.quote(month_begin_iso)}&endTs={urllib.parse.quote(month_end_iso)}&"
            f"stepUnit=MONTHS&stepValue=1&withEstimated=SURROUNDING_ESTIMATED&withLoadCurveCompletion=true&isGlobalConsumptionWanted=false"
        )
        async with self.session.get(monthly_url, headers=self._headers()) as resp:
            if resp.status == 200:
                data["monthly"] = await resp.json()

        # 4. Latest Meter Index Readings
        idx_begin = (now - datetime.timedelta(days=7)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        idx_end = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        idx_url = f"{BASE_API_URL}/v2/sites/-/elec-indexes?beginDate={urllib.parse.quote(idx_begin)}&endDate={urllib.parse.quote(idx_end)}&disableFilters=false&withActiveContract=false"
        async with self.session.get(idx_url, headers=self._headers()) as resp:
            if resp.status == 200:
                data["indexes"] = await resp.json()

        # 5. Billing Forecast
        fc_begin = first_day_month.strftime("%Y-%m-%d")
        fc_end = first_day_next_month.strftime("%Y-%m-%d")
        fc_url = f"{BASE_API_URL}/v2/sites/-/forecast-consumptions?beginDate={fc_begin}&endDate={fc_end}&fluid=ELEC&strategy=ESTIMATION_AFTER_REAL"
        async with self.session.get(fc_url, headers=self._headers()) as resp:
            if resp.status == 200:
                data["forecast"] = await resp.json()

        # 6. Peak Power Demand (Pmax)
        async with self.session.get(f"{BASE_API_URL}/v2/sites/-/elec-pmax", headers=self._headers()) as resp:
            if resp.status == 200:
                data["pmax"] = await resp.json()

        # 7. Gas Consumptions (only if account has active gas contract)
        params = data.get("site_details", {}).get("parameters", {})
        gas_ext_id = params.get("GAS_EXTERNAL_ID")
        has_gas = (bool(gas_ext_id) and gas_ext_id != "Non renseigné") or (params.get("isGas") == "true")
        if has_gas:
            gas_begin_str = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            gas_end_str = now.strftime("%Y-%m-%d")
            async with self.session.get(
                f"{BASE_API_URL}/v1/sites/-/smart-daily-gas-consumptions?begin-date={gas_begin_str}&end-date={gas_end_str}",
                headers=self._headers(),
            ) as resp:
                if resp.status == 200:
                    res_gas = await resp.json()
                    if isinstance(res_gas, dict):
                        data["gas_daily"] = res_gas
                if "gas_daily" not in data:
                    gas_v2_url = (
                        f"{BASE_API_URL}/v2/sites/-/consumptions?"
                        f"beginTs={urllib.parse.quote(begin_iso)}&endTs={urllib.parse.quote(end_iso)}&"
                        f"stepUnit=DAYS&stepValue=1&fluid=GAS&withEstimated=SURROUNDING_ESTIMATED"
                    )
                    async with self.session.get(gas_v2_url, headers=self._headers()) as resp2:
                        if resp2.status == 200:
                            res_gas2 = await resp2.json()
                            if isinstance(res_gas2, dict):
                                data["gas_daily"] = res_gas2

            # 8. Gas Monthly Consumptions
            m_begin = first_day_month.strftime("%Y-%m")
            m_end = first_day_next_month.strftime("%Y-%m")
            async with self.session.get(
                f"{BASE_API_URL}/v1/sites/-/compositions/monthly-gas-consumptions?begin-month={m_begin}&end-month={m_end}&ended=false",
                headers=self._headers(),
            ) as resp:
                if resp.status == 200:
                    res_gm = await resp.json()
                    if isinstance(res_gm, dict):
                        data["gas_monthly"] = res_gm

            # 9. Gas Indexes (look back 2 years to capture periodic/semi-annual billing indexes)
            idx_gas_begin = (now - datetime.timedelta(days=730)).strftime("%Y-%m-%d")
            async with self.session.get(
                f"{BASE_API_URL}/v1/sites/-/compositions/gas-indexes?begin-date={idx_gas_begin}&end-date={gas_end_str}",
                headers=self._headers(),
            ) as resp:
                if resp.status == 200:
                    res_gi = await resp.json()
                    if isinstance(res_gi, (list, dict)):
                        data["gas_indexes"] = res_gi

        # 10. Electricity Supply Contract (Tariff Option, Subscribed Power kVA)
        contract_begin = (now - datetime.timedelta(days=365)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        async with self.session.get(
            f"{BASE_API_URL}/v2/sites/-/elec-contracts?beginDate={urllib.parse.quote(contract_begin)}&endDate={urllib.parse.quote(idx_end)}&withTariffCalendars=true",
            headers=self._headers(),
        ) as resp:
            if resp.status == 200:
                data["contract"] = await resp.json()
                self.contract_details = data["contract"]

        # 11. 30-minute Load Curve (last 3 days so a complete 24h day is always available even right after midnight)
        lc_begin = (now - datetime.timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lc_end = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        async with self.session.get(
            f"{BASE_API_URL}/v2/sites/-/consumptions/load-curve?beginTs={urllib.parse.quote(lc_begin)}&endTs={urllib.parse.quote(lc_end)}&stepUnit=MINUTES&stepValue=30",
            headers=self._headers(),
        ) as resp:
            if resp.status == 200:
                data["load_curve"] = await resp.json()

        # 12. Local Weather & Heating Degree Days (HDD)
        w_begin = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        w_end = now.strftime("%Y-%m-%d")
        async with self.session.get(
            f"{BASE_API_URL}/v1/sites/-/daily-weathers?begin-day={w_begin}&end-day={w_end}",
            headers=self._headers(),
        ) as resp:
            if resp.status == 200:
                data["weather"] = await resp.json()

        # 13. Tariff Calendar (HP / HC & Tempo schedules)
        today_str = now.strftime("%Y-%m-%d")
        async with self.session.get(
            f"{BASE_API_URL}/v2/sites/-/elec-tariff-calendars?date={today_str}",
            headers=self._headers(),
        ) as resp:
            if resp.status == 200:
                data["tariff_calendar"] = await resp.json()

        # 14. Carbon Footprint (CO2 emissions)
        try:
            cf_begin = (now - datetime.timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            cf_end = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            async with self.session.get(
                f"{BASE_API_URL}/v1/sites/-/carbon-footprints?beginTs={urllib.parse.quote(cf_begin)}&endTs={urllib.parse.quote(cf_end)}&stepUnit=MONTHS",
                headers=self._headers(),
            ) as resp:
                if resp.status == 200:
                    data["carbon_footprint"] = await resp.json()
        except Exception as exc:
            _LOGGER.debug("Carbon footprint query ignored: %s", exc)

        # 15. Energy Usage Breakdown (Heating, hot water, appliances, standby)
        try:
            brk_ts = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            async with self.session.get(
                f"{BASE_API_URL}/v1/sites/-/usage-breakdowns?ts={urllib.parse.quote(brk_ts)}&fluid=ELEC",
                headers=self._headers(),
            ) as resp:
                if resp.status == 200:
                    data["usage_breakdown"] = await resp.json()
        except Exception as exc:
            _LOGGER.debug("Usage breakdown query ignored: %s", exc)

        data["account_summary"] = self.get_account_summary()
        return data

