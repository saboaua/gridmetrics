# Tiered / Time-of-Use Electricity Rate Calculator

**HACS custom integration for Home Assistant**

Calculate accurate electricity costs for **fixed-rate tiered (block) and/or Time-of-Use plans** — the billing structures used by the majority of utilities in North America, the Caribbean, Latin America, Asia and Africa.

Unlike the many excellent dynamic/spot-price integrations (Nord Pool, Tibber, ENTSO-E, Octopus Agile…), this component targets the far larger group of households on classic increasing-block tariffs and scheduled TOU rates.

## Why this exists

- Most of the world is **not** on hourly spot markets.
- Home Assistant’s Energy Dashboard already tracks kWh beautifully; it just needs the correct cost layer for non-flat billing.
- The previous “recommended” approach was hand-written `input_number` helpers + nested template sensors. This replaces that with a proper config-flow integration.

## Features (v0.1)

| Feature | Description |
|---------|-------------|
| **Tiered / IBT** | Arbitrary number of increasing-block tiers (e.g. Aruba 0-500 / 501-1000 / >1000) |
| **Time-of-Use** | Named periods with start/end times, optional weekdays-only flag |
| **Combined** | Both structures at once (common in real utility tariffs) |
| **Marginal rate sensor** | Live “what does the next kWh cost right now?” |
| **Estimated bill to date** | Running cost for the current billing cycle (energy + fixed charge + tax) |
| **Forecast bill** | Simple linear projection to cycle end |
| **Cycle consumption** | kWh used since the billing-cycle start day |
| **Prepaid support** | Balance tracking + services to add/set credit after buying power (Aruba, many Caribbean, African & Asian prepaid meters) |
| **Config flow** | No YAML required for basic setup |
| **Energy Dashboard ready** | Use the marginal-rate sensor as the price entity |

## Supported regions / example utilities

The component is region-agnostic; you simply enter your utility’s published rates. Tested design targets:

- **Caribbean**: Aruba (Elmar), Jamaica (JPS), Barbados, Bonaire, etc.
- **Latin America**: Mexico (CFE 1/1A–1F + DAC), many IBT utilities
- **North America**: US/Canada tiered + TOU plans
- **Asia / Africa**: Common increasing-block residential tariffs + prepaid

### Aruba (Elmar) example

```
Fixed charge: Afl. 12.50 / month
Tiers:
  0–500 kWh   → 0.3431 Afl/kWh
  501–1000    → 0.3531 Afl/kWh
  >1000       → 0.4645 Afl/kWh
```

Config-flow tiers string: `500:0.3431,1000:0.3531,99999:0.4645`

### Mexico (CFE-style) example

```
75:1.12,140:1.37,99999:4.00
```

(Adjust numbers to the current published basic / intermediate / excess rates for your tariff class.)

### Jamaica (JPS) TOU example

```
peak|18:00|22:00|0.35|true;partial|06:00|18:00|0.28|true;offpeak|22:00|06:00|0.22|false
```

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add this repository URL as category **Integration**
3. Search for “Tiered TOU” and install
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → “Tiered / Time-of-Use Electricity Rate Calculator”

### Manual

Copy `custom_components/tiered_tou_energy_cost/` into your HA `config/custom_components/` folder and restart.

## Usage with Energy Dashboard

1. Create the integration and point it at your total-energy sensor (kWh).
2. In the Energy Dashboard configuration for the grid consumption source, choose **“Use an entity with the current price”** and select the **Marginal Rate** sensor created by this integration.

## Prepaid meters (Aruba & similar)

Enable “prepaid balance tracking” during setup. After you buy power:

```yaml
service: tiered_tou_energy_cost.set_prepaid_balance
data:
  entry_id: <your config entry id>
  amount: 50.00
```

or

```yaml
service: tiered_tou_energy_cost.add_prepaid_credit
data:
  entry_id: <your config entry id>
  amount: 25.00
```

An event `tiered_tou_energy_cost_prepaid_topup` is fired so you can create notifications / automations.

## Services

| Service | Description |
|---------|-------------|
| `tiered_tou_energy_cost.add_prepaid_credit` | Add to balance |
| `tiered_tou_energy_cost.set_prepaid_balance` | Set absolute balance |
| `tiered_tou_energy_cost.reset_billing_cycle` | Force cycle reset |

## Future roadmap (architecture already prepared)

- Seasonal rate profiles
- Fuel-clause / PP adjustment multiplier
- Demand (kW) charges
- Period-split energy tracking for accurate TOU cost accumulation
- Automatic low-balance notifications for prepaid
- Utility-specific presets (Elmar, CFE, JPS, etc.)
- Export / feed-in rates

## Development & QA

See `tests/` for unit tests of the tier and TOU calculation engines.

```bash
# Run the pure-logic tests (no HA required)
python -m pytest tests/ -q
```

## License

MIT
