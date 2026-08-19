[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.][hacs-repo-badge]][hacs-repo]

# Australian Vehicle Registration

[![GitHub release][releases-shield]][releases]
[![Build status][build-shield]][build]
[![License][license-shield]](LICENSE)
[![Home Assistant minimum version][hamin-shield]][hamin]
[![hacs][hacs-shield]][hacs]
[![Ruff][ruff-shield]][ruff]

_Home Assistant integration that checks Australian vehicle registration on a schedule and lets your automations act on the result._

Add each of your vehicles by registration number and state or territory. Home
Assistant checks them at 7:00 am every day — or on whatever schedule you
choose — and gives you a plain yes or no to drive a notification, a light, or
anything else you like.

**This integration sets up the following platforms.**

| Platform | Description |
| -- | -- |
| `binary_sensor` | Whether the vehicle is registered, whether it expires soon, and whether the check itself is failing. |
| `sensor` | Registration status, expiry date, days until expiry, and when the vehicle was last checked. |
| `button` | Check this vehicle now, without waiting for the schedule. |

## Before you install: jurisdiction support

No Australian jurisdiction offers a public registration-check API. Each state
and territory runs a free public *website*, and several of them protect that
website against automated use. This integration does **not** attempt to defeat
those protections.

| Jurisdiction | Automatic checks | Notes |
| -- | -- | -- |
| Queensland | Yes | Verified end to end against the live service |
| South Australia | Yes | Answers only requests from an Australian IP address |
| Western Australia | Yes | Request flow and parsing built against the live page |
| Australian Capital Territory | Yes | Request flow and parsing built against the live page |
| New South Wales | No | Service NSW protects the free check with reCAPTCHA Enterprise |
| Victoria | No | Service Victoria protects the check with reCAPTCHA |
| Tasmania | Sometimes | Behind Cloudflare bot protection; often works from a home connection |
| Northern Territory | Sometimes | Behind Cloudflare bot protection; often works from a home connection |

Only Queensland has been exercised against the live service from end to end.
South Australia, Western Australia and the Australian Capital Territory have
their request flows and page parsing built and tested against the real pages,
but their final lookup could not be run during development, because those
services block or challenge connections from outside Australia. From an
Australian connection they should behave as described. Please
[open an issue][issues] if one does not.

### Every jurisdiction is still usable

Two providers work everywhere, and give you identical entities, events and
automations:

- **Manual** — enter the expiry date once, from your renewal notice or an
  official check. Home Assistant counts down from it. This is the recommended
  choice for New South Wales and Victoria.
- **Custom REST API** — point the integration at any registration API you are
  entitled to use, such as a commercial data provider, a fleet system, or your
  own script in front of a state website. You supply the URL and the JSON paths
  to the status, expiry date, or a registered true/false value.

## A failed check is never reported as "not registered"

This rule shapes the whole integration. If a website is down, geo-blocked,
rate-limiting, or has been redesigned, `binary_sensor.<vehicle>_registered`
becomes **unavailable**. It does not become **off**.

An automation that triggers on `to: "off"` therefore cannot fire because a
government website had a bad morning. If you want to know about those failures,
use `binary_sensor.<vehicle>_check_failing` or the `aus_rego_check_failed`
event instead.

## Installation

### HACS

1. Open HACS in Home Assistant.
1. Select the three-dot menu, then **Custom repositories**.
1. Add `https://github.com/tunlezah/hassrego` with the category **Integration**.
1. Search for **Australian Vehicle Registration** and download it.
1. Restart Home Assistant.

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.][hacs-repo-badge]][hacs-repo]

### Manual installation

1. Download the latest release from the [releases page][releases].
1. Copy the `custom_components/aus_rego` directory into the
   `custom_components` directory of your Home Assistant configuration.
1. Restart Home Assistant.

## Configuration

Configuration is done in the user interface.

Go to **Settings** > **Devices & services** > **Add integration** and search for
**Australian Vehicle Registration**.

[![Open your Home Assistant instance and start setting up a new integration.][config-flow-badge]][config-flow]

Enter the state or territory, the registration number, and optionally a name for
the vehicle. Spaces and dashes in the plate are ignored.

The integration runs one test lookup while you set the vehicle up, so problems
appear then rather than at 7:00 am. If the plate cannot be found, or the
jurisdiction blocks automated checks, it tells you and lets you decide whether
to continue.

**Add the integration again for each additional vehicle.** Every vehicle gets
its own device, its own schedule, and its own entities.

### Options

Select **Configure** on any vehicle to change these.

| Option | Default | Description |
| -- | -- | -- |
| Check at | `07:00:00` | Time of day the check runs, in your local time zone. |
| Check every (days) | `1` | `1` checks daily, `7` checks weekly. |
| Warn this many days before expiry | `14` | Controls the expiring-soon sensor and the `aus_rego_expiring` event. |
| Also check shortly after startup | Enabled | Runs one minute after Home Assistant starts. |
| Spread checks over (seconds) | `300` | A small per-vehicle offset so several vehicles do not contact a website at the same instant. |

The offset is derived from the registration number rather than randomly
generated, so it stays the same every day.

## Entities

Each vehicle becomes a device with the following entities, named after the
vehicle. A vehicle named `Corolla` produces `binary_sensor.corolla_registered`,
and so on.

| Entity | Description |
| -- | -- |
| `binary_sensor.<vehicle>_registered` | **On** when the vehicle is registered, **off** when it is not. Unavailable when the last check could not get an answer. |
| `binary_sensor.<vehicle>_expiring_soon` | **On** when registration has expired or falls inside the warning window. |
| `binary_sensor.<vehicle>_check_failing` | **On** when the last check could not get an answer. Attributes carry the reason. |
| `sensor.<vehicle>_registration_status` | One of `registered`, `expired`, `suspended`, `cancelled`, `unregistered`, `not_found` or `unknown`. |
| `sensor.<vehicle>_registration_expires` | The expiry date, as a timestamp. |
| `sensor.<vehicle>_days_until_expiry` | Days remaining, negative once expired. |
| `sensor.<vehicle>_last_checked` | When the last successful check ran. |
| `button.<vehicle>_check_now` | Runs a check immediately. |

The `registered` binary sensor also carries the status, plate, jurisdiction,
expiry date, days remaining and vehicle details as attributes.

## Automations

### Using the blueprint

The repository includes a blueprint at
`blueprints/automation/aus_rego/registration_alert.yaml` that handles
notifications, flashing a light, expiry warnings and, if you want them, check
failures. Copy it into the `blueprints/automation` directory of your
configuration and create an automation from it.

### Notify and flash a light when registration lapses

```yaml
automation:
  - alias: "Registration lapsed"
    triggers:
      - trigger: state
        entity_id: binary_sensor.corolla_registered
        to: "off"
    actions:
      - action: notify.mobile_app_pixel
        data:
          title: "Registration problem"
          message: >-
            {{ state_attr('binary_sensor.corolla_registered', 'status') }},
            expired {{ state_attr('binary_sensor.corolla_registered', 'expiry') }}
      - repeat:
          count: 3
          sequence:
            - action: light.turn_on
              target:
                entity_id: light.hallway
              data:
                flash: long
            - delay:
                seconds: 2
```

### Confirm registration is current

```yaml
automation:
  - alias: "Registration is current"
    triggers:
      - trigger: state
        entity_id: binary_sensor.corolla_registered
        to: "on"
    actions:
      - action: light.turn_on
        target:
          entity_id: light.hallway
        data:
          color_name: green
          flash: short
```

### Warn before registration expires

```yaml
automation:
  - alias: "Registration expiring soon"
    triggers:
      - trigger: event
        event_type: aus_rego_expiring
    actions:
      - action: persistent_notification.create
        data:
          title: "{{ trigger.event.data.vehicle_name }} registration expires soon"
          message: >-
            {{ trigger.event.data.days_remaining }} days remaining,
            expires {{ trigger.event.data.expiry }}.
```

### Notice when the check itself keeps failing

```yaml
automation:
  - alias: "Registration check is failing"
    triggers:
      - trigger: state
        entity_id: binary_sensor.corolla_check_failing
        to: "on"
        for: "24:00:00"
    actions:
      - action: persistent_notification.create
        data:
          title: "Registration check failing"
          message: >-
            {{ state_attr('binary_sensor.corolla_check_failing', 'error') }}
```

## Events

| Event | Fired when |
| -- | -- |
| `aus_rego_checked` | A check completed successfully. |
| `aus_rego_status_changed` | The status differs from the previous check. Includes `previous_status`. |
| `aus_rego_expiring` | Expiry falls inside the warning window. |
| `aus_rego_check_failed` | A check could not get an answer. Includes `reason`, `error` and `consecutive_failures`. |

Successful checks carry `vehicle_name`, `plate`, `jurisdiction`, `status`,
`registered`, `expiry`, `days_remaining` and the vehicle details the service
returned.

## Actions

### `aus_rego.check_now`

Checks vehicles immediately. Target specific vehicles with `entry_id` or
`device_id`, or omit both to check every vehicle.

### `aus_rego.check_plate`

Looks up any registration number once and returns the result to the caller,
without adding a vehicle.

```yaml
actions:
  - action: aus_rego.check_plate
    data:
      jurisdiction: qld
      plate: ABC123
    response_variable: rego
  - action: persistent_notification.create
    data:
      title: "Registration check"
      message: "{{ rego.status }}, expires {{ rego.expiry }}"
```

## Fair use

This integration uses the same free public services you would use in a browser,
for your own vehicles. Please keep it that way.

- One check per vehicle per day is the default on purpose. Registration status
  changes yearly, so checking more often gains you nothing and is discourteous
  to a public service.
- The Queensland check requires accepting the Department of Transport and Main
  Roads terms of use. Setup asks you to accept them explicitly, because each
  check accepts them on your behalf.
- Nothing here bypasses a CAPTCHA, bot protection or a login. Where a
  jurisdiction has chosen to block automation, the integration reports that and
  offers manual mode instead.

## Troubleshooting

Download diagnostics from the device page for the full picture. The
registration number is redacted.

| Symptom | Meaning |
| -- | -- |
| Status is `unknown` and entities are unavailable | The check could not get an answer. Check `binary_sensor.<vehicle>_check_failing` for the reason. |
| Reason is `geo_blocked` | That jurisdiction answers only Australian IP addresses. If Home Assistant runs on a virtual private server or behind a VPN that exits overseas, use manual mode instead. |
| Reason is `blocked` | Bot protection challenged the request. Try again later, and switch to manual mode if it persists. |
| Reason is `parse_error` | The website loaded but no longer looks the way the integration expects, which usually means it was redesigned. Please [open an issue][issues]. |
| The plate was not found during setup | Almost always a typo, or the vehicle is registered in a different state. |

## Contributions are welcome

Run the checks before opening a pull request:

```bash
python3 -m pytest tests/ -q
python3 -m ruff check custom_components tests
```

The tests need no Home Assistant installation. Parsing, status derivation and
scheduling deliberately have no Home Assistant imports, so the logic that
decides whether your automation fires can be tested on its own.

Adding a jurisdiction means adding one file under
`custom_components/aus_rego/providers/` and registering it in that package's
`__init__.py`.

## Disclaimer

Registration information comes from each jurisdiction's own public service and
may be cached or briefly out of date. For anything that matters legally, check
the official website directly. This project is not affiliated with, endorsed by,
or connected to any Australian government agency.

## License

MIT — see [LICENSE](LICENSE).

<!-- Badges -->
[build-shield]: https://img.shields.io/github/actions/workflow/status/tunlezah/hassrego/validate.yml?branch=main&style=for-the-badge
[build]: https://github.com/tunlezah/hassrego/actions/workflows/validate.yml
[config-flow-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
[config-flow]: https://my.home-assistant.io/redirect/config_flow_start/?domain=aus_rego
[hacs-repo-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacs-repo]: https://my.home-assistant.io/redirect/hacs_repository/?owner=tunlezah&repository=hassrego&category=integration
[hacs-shield]: https://img.shields.io/badge/HACS-custom-orange.svg?style=for-the-badge
[hacs]: https://hacs.xyz
[hamin-shield]: https://img.shields.io/badge/home%20assistant-2026.1%2B-blue.svg?style=for-the-badge
[hamin]: https://www.home-assistant.io
[issues]: https://github.com/tunlezah/hassrego/issues
[license-shield]: https://img.shields.io/github/license/tunlezah/hassrego.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/tunlezah/hassrego.svg?style=for-the-badge
[releases]: https://github.com/tunlezah/hassrego/releases
[ruff-shield]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge
[ruff]: https://github.com/astral-sh/ruff
