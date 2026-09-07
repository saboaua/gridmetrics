<p align="center">
  <img src="custom_components/gridmetrics/brand/logo.png" alt="GridMetrics" width="480">
</p>

<p align="center">
Tiered / Time-of-Use Electricity Rate Calculator for Home Assistant
</p>

[![release](https://img.shields.io/badge/release-v0.2.4-2c3e50)](https://github.com/your-github-handle/ha-gridmetrics/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)
[![HA](https://img.shields.io/badge/HA-2024.1%2B-41BDF5)](https://www.home-assistant.io)
[![Buy Me a Coffee](https://img.shields.io/badge/%E2%98%95-Buy%20me%20a%20coffee-FF813F)](https://ko-fi.com/patrickgfortin)
[![issues](https://img.shields.io/github/issues/your-github-handle/ha-gridmetrics)](https://github.com/your-github-handle/ha-gridmetrics/issues)

Calculate accurate electricity costs for **fixed-rate tiered (block) and/or Time-of-Use plans**, with **guided solar / net-metering onboarding**.

Designed for the majority of households in North America, the Caribbean, Latin America, Asia and Africa that are **not** on dynamic spot-market tariffs.

---

## What's new in 0.2.4

| Change | Description |
|---|---|
| **Config entry version fix** | Fixed a bug where an entry stamped from a newer build (`version: 2`) would fail to load against older code ("has version 2 which is higher than the current version 1"). The integration now migrates entries automatically via `async_migrate_entry`. |
| **Reliable options reload** | Saving **Configure** settings now uses Home Assistant's built-in `async_reload()` instead of a hand-rolled unload/setup, so it can no longer hang or throw during reload. |
| **Missing translations fixed** | Added `translations/en.json`. Config and Options dialogs now show friendly field labels instead of raw keys like `fixed_charge`. |
| **Filtered entity pickers** | Solar/grid sensor pickers in the config flow now filter to `power`/`energy` device classes instead of listing every sensor in the house. |
| **Hardened sensors** | `Marginal Rate`, `Cycle Consumption`, and `Prepaid Balance` sensors no longer raise during the brief window right after a reload. |

---

## The problem this solves

With solar you typically have:

- Solar inverter (Enphase, SolarEdge…) → production
- Grid meter (Shelly 3EM, etc.) → import/export, often reported per phase

A non-expert user then has to build template helpers to answer:

> "If panels produce 5,414 W and the meter shows −3,850 W (export), how much is the house actually using?"

**GridMetrics calculates this for you:**

```
Home Consumption = Solar Production + Grid Import − Grid Export
                 ≈ 5,414 W + 0 − 3,850 W ≈ 1,564 W
```

You get ready-to-use power and energy sensors for the Energy Dashboard, plus a cost engine on top of them.

---

## Features

- **Tiered / IBT** — arbitrary increasing-block tiers (Aruba, CFE, JPS lifeline…)
- **Time-of-Use** — named periods, optional weekdays-only
- **Combined** — both structures at once
- **Marginal rate** — "what does the next kWh cost right now?"
- **Estimated bill to date** + **forecast to cycle end**
- **Prepaid balance** + services (Caribbean / Africa / Asia prepaid meters)
- **Solar net-metering** — single- or multi-phase (Shelly 3EM) grid measurement, with derived Home Consumption / Grid Import / Grid Export / Solar Production sensors
- **Currency** — selectable at setup and in **Configure** (options flow)
- **Config flow only** — no YAML required

---

## Quick start – solar home (Enphase + Shelly 3EM)

1. Install the integration (HACS or manual — see below).
2. **Settings → Devices & Services → Add Integration → GridMetrics.**
3. **What do you want to set up?** → *Solar + Grid*
4. **Basics** → name, rate type (tiered / TOU / combined), currency, billing cycle day, fixed charge, tax, prepaid toggle.
5. **Solar production sensor** → pick your Enphase (or other) power sensor.
6. **How is the grid measured?** → *Multiple phases* (Shelly 3EM) or *One single grid sensor*.
7. If multi-phase: **Phase sensors** → pick Phase A, B, C individually (leave unused phases empty; at least one is required). Set the import/export sign and optional feed-in rate.
8. **Tiers / TOU** → enter your rate structure.
9. Done. You now have:

| Sensor | Use |
|---|---|
| Solar Production | Power (W) |
| Grid Import | Power (W) |
| Grid Export | Power (W) |
| **Home Consumption** | Power (W) — what the house is actually using |
| …Energy variants | kWh, for the Energy Dashboard |
| Marginal Rate | Current price per kWh |
| Estimated Bill to Date | Running cost this billing cycle |
| Forecast Bill | Projected cost by cycle end |

**Grid-only homes** (no solar) follow the same flow but choose *Grid only* at step 3, then point GridMetrics at your utility's cumulative billed-energy (kWh) sensor.

---

## Currency

Choose from the dropdown at setup (AWG, USD, MXN, JMD, BBD, TTD, CAD, BRL, COP, ARS, CLP, PEN, INR, ZAR, NGN, KES, PHP, THB, EUR, GBP). You can change it later from **Configure** on the integration entry.

---

## Prepaid (Aruba & similar)

Enable prepaid tracking in the **Basics** step. After buying power:

```yaml
service: gridmetrics.set_prepaid_balance
data:
  entry_id: <config_entry_id>
  amount: 50.00
```

`gridmetrics.add_prepaid_credit` and `gridmetrics.reset_billing_cycle` are also available. Event `gridmetrics_prepaid_topup` fires on any balance change, for notifications/automations.

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

**HACS:** Custom repository → add this repo as an Integration → install → restart Home Assistant.
**Manual:** copy `custom_components/gridmetrics/` into your `config/custom_components/` and restart.

Minimum supported Home Assistant version: **2024.1.0**.

**Brand assets:** icon/logo images ship inside the integration at `custom_components/gridmetrics/brand/` (`icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`). HA 2024.1+ has always been able to fall back to the community `home-assistant/brands` repo for these, but as of HA 2026.3 custom integrations can ship brand images locally and HA serves them directly — no external PR needed, and it also clears HACS's brand-assets validation check.

---

## Roadmap

- Utility presets (Elmar, CFE, JPS…)
- Period-split TOU cost accumulation
- Seasonal profiles & fuel-clause multiplier
- Demand (kW) charges
- Stronger Energy Dashboard cost-entity integration

---

## Support the Project

If you find GridMetrics helpful and want to support its continued development, feel free to buy me a coffee!

<a href="https://ko-fi.com/patrickgfortin" target="_blank"><img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" height="36" alt="Buy Me a Coffee at ko-fi.com" /></a>

---

## License

MIT
