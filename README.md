# Tiered / Time-of-Use Electricity Rate Calculator

**HACS custom integration for Home Assistant – v0.2.0**

Calculate accurate electricity costs for **fixed-rate tiered (block) and/or Time-of-Use plans**, with **easy solar / net-metering onboarding**.

Designed for the majority of households in North America, the Caribbean, Latin America, Asia and Africa that are **not** on dynamic spot-market tariffs.

---

## What’s new in 0.2

| Feature | Description |
|---------|-------------|
| **Currency selector** | Dropdown with AWG, USD, MXN, JMD, BBD, CAD, BRL, INR, ZAR, EUR… (and more) |
| **Solar / net-metering wizard** | One step: pick your Enphase (or other) production sensor + Shelly 3EM phases (or single grid sensor). Done. |
| **Auto-created sensors** | Solar Production, Grid Import, Grid Export, **Home Consumption** (power + energy) |
| **Feed-in rate** | Optional export credit (currency/kWh) |

### The problem this solves

With solar you typically have:

- Solar inverter (Enphase, SolarEdge…) → production
- Grid meter (Shelly 3EM, etc.) → import/export (often per phase)

A non-expert user then has to build helpers to answer:

> “If panels produce 5 414 W and the meter shows −3 850 W (export), how much is the house actually using?”

**Answer the integration now calculates for you:**

```
Home Consumption = Solar Production + Grid Import − Grid Export
                 ≈ 5 414 W + 0 − 3 850 W  ≈ 1 564 W
```

You get ready-to-use sensors for the Energy Dashboard and for the cost engine.

---

## Features

- **Tiered / IBT** – arbitrary increasing-block tiers (Aruba, CFE, JPS lifeline…)
- **Time-of-Use** – named periods, optional weekdays-only
- **Combined** – both structures at once
- **Marginal rate** – “what does the next kWh cost right now?”
- **Estimated bill to date** + **forecast** to cycle end
- **Prepaid balance** + services (Caribbean / Africa / Asia prepaid meters)
- **Solar net-metering** – Home Consumption / Grid Import / Grid Export / Solar Production
- **Currency** – selectable in config & options
- **Config flow** – no YAML required

---

## Quick start – solar home (Enphase + Shelly 3EM)

1. Install the integration (HACS or manual).
2. Add Integration → **Tiered / Time-of-Use Electricity Rate Calculator**.
3. Fill name, rate mode, **currency** (e.g. AWG), fixed charge, tax.
4. Enable **I have solar panels**.
5. Solar step:
   - Solar sensor → your Enphase production (prefer **W**)
   - Multi-phase → `sensor.shelly_phase_a_power,sensor.shelly_phase_b_power,sensor.shelly_phase_c_power`
   - Sign → usually “Positive = Import from grid”
   - Optional feed-in rate
6. Enter your tiers / TOU windows.
7. Done. You now have:

| Sensor | Use |
|--------|-----|
| Solar Production | Power (W) |
| Grid Import | Power (W) |
| Grid Export | Power (W) |
| **Home Consumption** | Power (W) – what the house uses |
| … Energy variants | kWh for Energy Dashboard |
| Marginal Rate | Price entity for Energy Dashboard |
| Estimated Bill to Date | Running cost |

---

## Currency

Choose from the dropdown (AWG, USD, MXN, JMD…). You can change it later in **Configure** (options flow).

---

## Prepaid (Aruba & similar)

Enable prepaid tracking. After buying power:

```yaml
service: tiered_tou_energy_cost.set_prepaid_balance
data:
  entry_id: <config_entry_id>
  amount: 50.00
```

Event `tiered_tou_energy_cost_prepaid_topup` is fired for notifications.

---

## Example rates

**Aruba (Elmar)**  
`500:0.3431,1000:0.3531,99999:0.4645` + fixed 12.50 AWG

**Mexico CFE-style**  
`75:1.12,140:1.37,99999:4.00`

**Jamaica JPS TOU**  
`peak|18:00|22:00|0.35|true;partial|06:00|18:00|0.28|true;offpeak|22:00|06:00|0.22|false`

---

## Installation

**HACS:** Custom repository → this repo → Integration  
**Manual:** copy `custom_components/tiered_tou_energy_cost/` into your config and restart.

---

## Roadmap

- Utility presets (Elmar, CFE, JPS…)
- Period-split TOU cost accumulation
- Seasonal profiles & fuel-clause multiplier
- Demand (kW) charges
- Stronger Energy Dashboard cost entity integration

---

## License

MIT
