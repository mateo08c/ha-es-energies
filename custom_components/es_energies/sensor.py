"""Sensor platform for ES Énergies integration."""

import logging
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EsEnergiesCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ES Énergies sensors from config entry."""
    coordinator: EsEnergiesCoordinator = hass.data[DOMAIN][entry.entry_id]

    site_id = coordinator.client.site_id
    summary = coordinator.data.get("account_summary") or coordinator.client.get_account_summary()
    pdl = summary.get("pdl", site_id)
    meter_type = summary.get("meter_type", "Linky")

    device_info = DeviceInfo(
        identifiers={(DOMAIN, site_id)},
        name=f"Linky ({pdl})",
        manufacturer="Électricité de Strasbourg / Enedis",
        model=f"Compteur communicant {meter_type}",
        configuration_url="https://suiviconso.es.fr/",
    )

    entities = [
        # Diagnostic & Account
        EsEnergyAccountHolderSensor(coordinator, entry, device_info),
        EsEnergyPDLSensor(coordinator, entry, device_info),
        EsEnergyAddressSensor(coordinator, entry, device_info),
        EsEnergySubscribedPowerSensor(coordinator, entry, device_info),
        EsEnergyQualitySensor(coordinator, entry, device_info),
        EsEnergyLastUpdateSensor(coordinator, entry, device_info),

        # Consumption & Index
        EsEnergyTotalIndexSensor(coordinator, entry, device_info),
        EsEnergyDailySensor(coordinator, entry, device_info),
        EsEnergyDailyCostSensor(coordinator, entry, device_info),
        EsEnergyMonthlySensor(coordinator, entry, device_info),
        EsEnergyMonthlyCostSensor(coordinator, entry, device_info),
        EsEnergyForecastSensor(coordinator, entry, device_info),
        EsEnergyForecastCostSensor(coordinator, entry, device_info),
        EsEnergyPeakPowerSensor(coordinator, entry, device_info),
        EsEnergyLoadCurveSensor(coordinator, entry, device_info),

        # Weather & Climate
        EsEnergyOutdoorTempSensor(coordinator, entry, device_info),
        EsEnergyHDDSensor(coordinator, entry, device_info),

        # Environmental & Analytics
        EsEnergyCarbonSensor(coordinator, entry, device_info),
        EsEnergyStandbyEnergySensor(coordinator, entry, device_info),
    ]

    # Dynamically expose tariff-specific indexes (Heures Creuses / Heures Pleines) if present
    indexes_data = coordinator.data.get("indexes", {}).get("indexes", [])
    if indexes_data:
        headings = indexes_data[-1].get("indexesByTariffHeading", {})
        if "HC" in headings or "HP" in headings:
            if "HC" in headings:
                entities.append(EsEnergyTariffHeadingIndexSensor(coordinator, entry, device_info, "HC", "Index heures creuses"))
            if "HP" in headings:
                entities.append(EsEnergyTariffHeadingIndexSensor(coordinator, entry, device_info, "HP", "Index heures pleines"))
        for k in headings:
            if k not in ("BASE", "HC", "HP"):
                label = f"Index {k.lower()}"
                entities.append(EsEnergyTariffHeadingIndexSensor(coordinator, entry, device_info, k, label))

    # Gas sensors only if customer has an active gas contract and valid gas data
    has_gas_data = bool(coordinator.data.get("gas_indexes") or coordinator.data.get("gas_daily") or coordinator.data.get("gas_monthly"))
    if summary.get("has_gas") and has_gas_data:
        gas_pdl = summary.get("gas_pdl") or site_id
        gas_meter_type = summary.get("gas_meter_type") or "Gaz"
        gas_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{site_id}_gas")},
            name=f"Compteur Gaz ({gas_pdl})",
            manufacturer="Gaz de Strasbourg / GRDF",
            model=f"Compteur gaz ({gas_meter_type})",
            configuration_url="https://suiviconso.es.fr/",
        )
        entities.extend([
            EsGasIndexSensor(coordinator, entry, gas_device_info),
            EsEnergyLastUpdateSensor(coordinator, entry, gas_device_info, unique_id_suffix="gas_last_sync"),
        ])

        if coordinator.data.get("gas_daily"):
            entities.extend([
                EsGasDailySensor(coordinator, entry, gas_device_info),
                EsGasDailyCostSensor(coordinator, entry, gas_device_info),
            ])
        if coordinator.data.get("gas_monthly"):
            entities.append(EsGasMonthlySensor(coordinator, entry, gas_device_info))

    async_add_entities(entities)


class EsEnergyBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for ES Énergies sensors with clean HA entity naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EsEnergiesCoordinator, entry: ConfigEntry, device_info: DeviceInfo):
        super().__init__(coordinator)
        self._entry = entry
        self._site_id = coordinator.client.site_id
        self._attr_device_info = device_info

    def _get_latest_valid_daily(self) -> dict:
        """Return the most recent non-empty daily consumption item."""
        consumptions = self.coordinator.data.get("daily", {}).get("consumptions", [])
        if not consumptions:
            return {}
        for item in reversed(consumptions):
            if item.get("nature") != "EMPTY" and item.get("status") != "EMPTY" and item.get("energyMeter", {}).get("total", 0.0) > 0:
                return item
        for item in reversed(consumptions):
            if item.get("nature") != "EMPTY" and item.get("status") != "EMPTY":
                return item
        return consumptions[-1]


# =========================================================================
# Diagnostic & Account Information Sensors
# =========================================================================

class EsEnergyAccountHolderSensor(EsEnergyBaseSensor):
    """Account holder name and global contract metadata."""

    _attr_name = "Titulaire du compte"
    _attr_icon = "mdi:account-badge-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_titulaire"

    @property
    def native_value(self):
        summary = self.coordinator.data.get("account_summary") or self.coordinator.client.get_account_summary()
        return summary.get("customer_name")

    @property
    def extra_state_attributes(self):
        summary = self.coordinator.data.get("account_summary") or self.coordinator.client.get_account_summary()
        return {
            "titulaire": summary.get("customer_name"),
            "email": summary.get("email"),
            "numero_client": summary.get("person_id"),
            "identifiant_site": summary.get("site_id"),
            "pdl": summary.get("pdl"),
            "adresse": summary.get("address"),
            "code_postal": summary.get("zip_code"),
            "ville": summary.get("city"),
            "type_compteur": summary.get("meter_type"),
            "mise_en_service_compteur": summary.get("first_com_date"),
            "option_tarifaire": summary.get("tariff_option"),
            "tarif": summary.get("tariff"),
            "puissance_souscrite_kva": summary.get("subscribed_power"),
            "gaz_actif": summary.get("has_gas"),
        }


class EsEnergyPDLSensor(EsEnergyBaseSensor):
    """Linky Point de Livraison (PDL) identifier."""

    _attr_name = "Point de livraison"
    _attr_icon = "mdi:identifier"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_pdl_id"

    @property
    def native_value(self):
        summary = self.coordinator.data.get("account_summary") or self.coordinator.client.get_account_summary()
        return summary.get("pdl")


class EsEnergyAddressSensor(EsEnergyBaseSensor):
    """Physical address of the meter."""

    _attr_name = "Adresse de raccordement"
    _attr_icon = "mdi:map-marker-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_meter_address"

    @property
    def native_value(self):
        summary = self.coordinator.data.get("account_summary") or self.coordinator.client.get_account_summary()
        return summary.get("address")


class EsEnergySubscribedPowerSensor(EsEnergyBaseSensor):
    """Subscribed power in kVA."""

    _attr_name = "Puissance souscrite"
    _attr_native_unit_of_measurement = "kVA"
    _attr_icon = "mdi:flash-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_power_sub"

    @property
    def native_value(self):
        contracts = self.coordinator.data.get("contract", {}).get("contracts", [])
        if not contracts:
            return 6
        p = contracts[-1].get("supplyContractParameters", {})
        power = p.get("SUBSCRIBED_POWER")
        try:
            return int(power) if power else 6
        except (ValueError, TypeError):
            return 6

    @property
    def extra_state_attributes(self):
        contracts = self.coordinator.data.get("contract", {}).get("contracts", [])
        if not contracts:
            return {}
        p = contracts[-1].get("supplyContractParameters", {})
        return {
            "option_tarifaire": p.get("TARIFF_OPTION", "BASE"),
            "tarif": p.get("TARIFF", "BLEU"),
            "puissance_souscrite_kva": p.get("SUBSCRIBED_POWER", "6"),
        }


class EsEnergyQualitySensor(EsEnergyBaseSensor):
    """Telemetry data quality percentage."""

    _attr_name = "Qualité de télérelève"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:signal-cellular-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_quality_percent"

    @property
    def native_value(self):
        item = self._get_latest_valid_daily()
        if not item:
            return 100
        return int(item.get("quality", 1.0) * 100)


class EsEnergyLastUpdateSensor(EsEnergyBaseSensor):
    """Last successful synchronization with ÉS Énergies servers."""

    _attr_name = "Dernière synchronisation"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator, entry, device_info, unique_id_suffix: str = "last_sync"):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_{unique_id_suffix}"

    @property
    def native_value(self):
        return self.coordinator.data.get("last_updated")


# =========================================================================
# Energy Consumption & Meter Index Sensors (HA Energy Dashboard Compatible)
# =========================================================================

class EsEnergyTotalIndexSensor(EsEnergyBaseSensor):
    """Cumulative meter index (Linky Base or Total)."""

    _attr_name = "Index de consommation"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_total_index"

    @property
    def native_value(self):
        indexes = self.coordinator.data.get("indexes", {}).get("indexes", [])
        if not indexes:
            return None
        latest = indexes[-1]
        headings = latest.get("indexesByTariffHeading", {})
        if "BASE" in headings:
            return round(headings["BASE"] / 1000.0, 3)
        total_wh = sum(headings.values())
        return round(total_wh / 1000.0, 3) if total_wh > 0 else None

    @property
    def extra_state_attributes(self):
        indexes = self.coordinator.data.get("indexes", {}).get("indexes", [])
        if not indexes:
            return {}
        latest = indexes[-1]
        return {
            "date": latest.get("ts"),
            "nature": latest.get("nature"),
            "type": latest.get("type"),
        }


class EsEnergyTariffHeadingIndexSensor(EsEnergyBaseSensor):
    """Specific tariff index (HC, HP, etc.) for HA Energy Dashboard."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, entry, device_info, heading_key: str, label: str):
        super().__init__(coordinator, entry, device_info)
        self._heading_key = heading_key
        self._attr_name = label
        self._attr_unique_id = f"{self._site_id}_index_{heading_key.lower()}"

    @property
    def native_value(self):
        indexes = self.coordinator.data.get("indexes", {}).get("indexes", [])
        if not indexes:
            return None
        latest = indexes[-1]
        headings = latest.get("indexesByTariffHeading", {})
        val = headings.get(self._heading_key)
        return round(val / 1000.0, 3) if val is not None else None


class EsEnergyDailySensor(EsEnergyBaseSensor):
    """Daily consumption for the latest complete day."""

    _attr_name = "Consommation d'hier"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_conso_hier"

    @property
    def native_value(self):
        item = self._get_latest_valid_daily()
        if not item:
            return None
        return round(item.get("energyMeter", {}).get("total", 0.0), 3)

    @property
    def extra_state_attributes(self):
        item = self._get_latest_valid_daily()
        if not item:
            return {}
        return {
            "date": item.get("period", {}).get("startTime"),
            "quality": f"{int(item.get('quality', 1.0) * 100)}%",
            "nature": item.get("nature"),
        }


class EsEnergyDailyCostSensor(EsEnergyBaseSensor):
    """Cost for the latest complete day."""

    _attr_name = "Coût d'hier"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_cost_hier"

    @property
    def native_value(self):
        item = self._get_latest_valid_daily()
        if not item:
            return None
        return round(item.get("cost", {}).get("total", 0.0), 2)


class EsEnergyMonthlySensor(EsEnergyBaseSensor):
    """Monthly electricity consumption."""

    _attr_name = "Consommation du mois"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_conso_mois"

    @property
    def native_value(self):
        consumptions = self.coordinator.data.get("monthly", {}).get("consumptions", [])
        if not consumptions:
            return None
        item = consumptions[-1]
        return round(item.get("energyMeter", {}).get("total", 0.0), 2)


class EsEnergyMonthlyCostSensor(EsEnergyBaseSensor):
    """Monthly electricity cost."""

    _attr_name = "Coût du mois"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_cost_mois"

    @property
    def native_value(self):
        consumptions = self.coordinator.data.get("monthly", {}).get("consumptions", [])
        if not consumptions:
            return None
        item = consumptions[-1]
        return round(item.get("cost", {}).get("total", 0.0), 2)


class EsEnergyForecastSensor(EsEnergyBaseSensor):
    """Estimated consumption at month end."""

    _attr_name = "Estimation fin de mois"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_forecast_energy"

    @property
    def native_value(self):
        fc = self.coordinator.data.get("forecast", {})
        return round(fc.get("energy", 0.0), 1)


class EsEnergyForecastCostSensor(EsEnergyBaseSensor):
    """Estimated bill at month end."""

    _attr_name = "Facture estimée fin de mois"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_forecast_bill"

    @property
    def native_value(self):
        fc = self.coordinator.data.get("forecast", {})
        return round(fc.get("cost", 0.0), 2)


class EsEnergyPeakPowerSensor(EsEnergyBaseSensor):
    """Peak power reached (Pmax)."""

    _attr_name = "Puissance maximale"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_peak_power"

    @property
    def native_value(self):
        pmax_list = self.coordinator.data.get("pmax", [])
        if not pmax_list:
            return None
        latest = pmax_list[-1]
        return latest.get("value")

    @property
    def extra_state_attributes(self):
        pmax_list = self.coordinator.data.get("pmax", [])
        if not pmax_list:
            return {}
        latest = pmax_list[-1]
        return {"date": latest.get("date")}


class EsEnergyLoadCurveSensor(EsEnergyBaseSensor):
    """Recent 30-minute load curve with detailed intervals."""

    _attr_name = "Courbe de charge"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_curve_recent"

    def _get_valid_points(self) -> list:
        curve = self.coordinator.data.get("load_curve", {}).get("consumptions", [])
        non_empty = [item for item in curve if item.get("nature") != "EMPTY" and item.get("status") != "EMPTY"]
        return non_empty[-48:] if len(non_empty) >= 48 else non_empty

    @property
    def native_value(self):
        points = self._get_valid_points()
        if not points:
            return None
        total = sum(item.get("energyMeter", {}).get("total", 0.0) for item in points)
        return round(total, 3)

    @property
    def extra_state_attributes(self):
        raw_points = self._get_valid_points()
        if not raw_points:
            return {}
        points = []
        for item in raw_points:
            points.append({
                "start": item.get("period", {}).get("startTime"),
                "end": item.get("period", {}).get("endTime"),
                "kwh": round(item.get("energyMeter", {}).get("total", 0.0), 3),
                "cost": round(item.get("cost", {}).get("total", 0.0), 3),
            })
        return {
            "points_count": len(points),
            "points_30min": points,
        }


# =========================================================================
# Weather & Heating Degree Days (DJU)
# =========================================================================

class EsEnergyOutdoorTempSensor(EsEnergyBaseSensor):
    """Average local outdoor temperature for heating analysis."""

    _attr_name = "Température extérieure moyenne"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_temp_out"

    @property
    def native_value(self):
        weathers = self.coordinator.data.get("weather", [])
        if not weathers:
            return None
        latest = weathers[-1]
        temp = latest.get("valueWithDecimal")
        if temp is None:
            temp = latest.get("averageTemp", latest.get("value", 0.0))
        return round(float(temp), 1)

    @property
    def extra_state_attributes(self):
        weathers = self.coordinator.data.get("weather", [])
        if not weathers:
            return {}
        latest = weathers[-1]
        temp = latest.get("valueWithDecimal", latest.get("averageTemp", 18.0))
        dju = latest.get("heatingDegreeDays")
        if dju is None and temp is not None:
            dju = round(max(0.0, 18.0 - float(temp)), 1)
        return {
            "date": latest.get("day"),
            "picto": latest.get("picto"),
            "dju": dju,
        }


class EsEnergyHDDSensor(EsEnergyBaseSensor):
    """Heating Degree Days (Degrés Jours Unifiés - DJU)."""

    _attr_name = "Degrés jours unifiés (DJU)"
    _attr_icon = "mdi:weather-snowy-heavy"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_dju_days"

    @property
    def native_value(self):
        weathers = self.coordinator.data.get("weather", [])
        if not weathers:
            return None
        latest = weathers[-1]
        dju = latest.get("heatingDegreeDays")
        if dju is not None:
            return round(float(dju), 1)
        temp = latest.get("valueWithDecimal", latest.get("averageTemp"))
        if temp is not None:
            return round(max(0.0, 18.0 - float(temp)), 1)
        return 0.0



class EsEnergyCarbonSensor(EsEnergyBaseSensor):
    """Monthly carbon footprint (kg CO2 equivalent) from official ÉS energy mix."""

    _attr_name = "Empreinte carbone du mois"
    _attr_native_unit_of_measurement = "kg"
    _attr_icon = "mdi:molecule-co2"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_carbon_footprint"

    @property
    def native_value(self):
        cfs = self.coordinator.data.get("carbon_footprint", {}).get("carbonFootprints", [])
        if not cfs:
            return None
        return round(float(cfs[-1].get("carbonFootprint", 0.0)), 2)

    @property
    def extra_state_attributes(self):
        cfs = self.coordinator.data.get("carbon_footprint", {}).get("carbonFootprints", [])
        if not cfs:
            return {}
        item = cfs[-1]
        mix = item.get("energyMix", {})
        return {
            "intensite_carbone_g_kwh": item.get("carbonCoefficient"),
            "mix_nucleaire_pourcent": mix.get("nuclear"),
            "mix_renouvelable_pourcent": mix.get("renewable"),
            "mix_fossile_pourcent": mix.get("fossil"),
            "periode_debut": item.get("period", {}).get("startTime"),
            "periode_fin": item.get("period", {}).get("endTime"),
        }



class EsEnergyStandbyEnergySensor(EsEnergyBaseSensor):
    """Always-on standby background energy consumption (bruit de fond / talon de veille)."""

    _attr_name = "Consommation bruit de fond (Veille)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:power-sleep"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_standby_energy"

    def _get_always_on(self) -> dict:
        usages = self.coordinator.data.get("usage_breakdown", {}).get("usageBreakdowns", [])
        for u in usages:
            if "partialAlwaysOn" in u:
                return u["partialAlwaysOn"]
        return {}

    @property
    def native_value(self):
        ao = self._get_always_on()
        val = ao.get("energy")
        return round(float(val), 1) if val is not None else None

    @property
    def extra_state_attributes(self):
        ao = self._get_always_on()
        if not ao:
            return {}
        return {
            "cout_eur": ao.get("cost"),
            "pourcentage": ao.get("percent"),
        }


# =========================================================================
# Gas Sensors (when active contract is present)
# =========================================================================

class EsGasIndexSensor(EsEnergyBaseSensor):
    """Cumulative gas meter index for HA Energy Dashboard."""

    _attr_name = "Index de consommation"
    _attr_device_class = SensorDeviceClass.GAS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "m³"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_gas_index"

    def _get_latest_reading(self) -> dict:
        """Extract the most recent gas index item."""
        gas_idx = self.coordinator.data.get("gas_indexes")
        if isinstance(gas_idx, list) and gas_idx:
            return gas_idx[-1]
        if isinstance(gas_idx, dict):
            indexes = gas_idx.get("indexes", [])
            if indexes:
                return indexes[-1]
        return {}

    @property
    def native_value(self):
        latest = self._get_latest_reading()
        if latest:
            idx = latest.get("index") if "index" in latest else latest.get("volumeIndex")
            if idx is not None:
                return idx

        gas_daily = self.coordinator.data.get("gas_daily")
        if isinstance(gas_daily, dict):
            daily = gas_daily.get("consumptions", [])
            if daily:
                return daily[-1].get("volume")
        return None

    @property
    def extra_state_attributes(self):
        latest = self._get_latest_reading()
        if not latest:
            return {}
        attrs = {}
        if "date" in latest:
            attrs["date_releve"] = latest["date"]
        if "type" in latest:
            attrs["type_releve"] = latest["type"]
        if "conversionFactor" in latest:
            attrs["coefficient_conversion_kwh_m3"] = latest["conversionFactor"]
        if "index" in latest and "conversionFactor" in latest and latest["conversionFactor"]:
            attrs["energie_totale_kwh"] = round(latest["index"] * latest["conversionFactor"], 2)
        return attrs


class EsGasDailySensor(EsEnergyBaseSensor):
    """Daily gas consumption (yesterday)."""

    _attr_name = "Consommation d'hier"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_gas_kwh_hier"

    @property
    def native_value(self):
        gas_daily = self.coordinator.data.get("gas_daily")
        if not isinstance(gas_daily, dict):
            return None
        consumptions = gas_daily.get("consumptions", [])
        if not consumptions:
            return None
        item = consumptions[-1]
        return round(item.get("energyMeter", {}).get("total", 0.0), 2)


class EsGasDailyCostSensor(EsEnergyBaseSensor):
    """Daily gas cost (yesterday)."""

    _attr_name = "Coût d'hier"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_gas_cost_hier"

    @property
    def native_value(self):
        gas_daily = self.coordinator.data.get("gas_daily")
        if not isinstance(gas_daily, dict):
            return None
        consumptions = gas_daily.get("consumptions", [])
        if not consumptions:
            return None
        item = consumptions[-1]
        return round(item.get("cost", {}).get("total", 0.0), 2)


class EsGasMonthlySensor(EsEnergyBaseSensor):
    """Monthly gas consumption."""

    _attr_name = "Consommation du mois"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info)
        self._attr_unique_id = f"{self._site_id}_gas_kwh_mois"

    @property
    def native_value(self):
        gas_monthly = self.coordinator.data.get("gas_monthly")
        if not isinstance(gas_monthly, dict):
            return None
        consumptions = gas_monthly.get("consumptions", [])
        if not consumptions:
            return None
        item = consumptions[-1]
        return round(item.get("energyMeter", {}).get("total", 0.0), 2)
