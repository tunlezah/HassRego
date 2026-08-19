# Australian Vehicle Registration for Home Assistant

Track the registration status of any number of vehicles across all eight
Australian states and territories, check them on a schedule (7:00 am daily by
default), and drive automations off a clear yes/no answer.

Built for Home Assistant **2026.1 and later**.

---

## What you get, per vehicle

Each vehicle becomes a device with these entities:

| Entity | Type | What it tells you |
| --- | --- | --- |
| `binary_sensor.<vehicle>_registered` | binary | **on** = registered, **off** = not registered |
| `binary_sensor.<vehicle>_expiring_soon` | binary (problem) | on when inside the warning window, or already expired |
| `binary_sensor.<vehicle>_check_failing` | binary (problem, diagnostic) | on when the check itself could not get an answer |
| `sensor.<vehicle>_registration_status` | enum | `registered`, `expired`, `suspended`, `cancelled`, `unregistered`, `not_found`, `unknown` |
| `sensor.<vehicle>_registration_expires` | timestamp | expiry date |
| `sensor.<vehicle>_days_until_expiry` | number | days remaining, negative once expired |
| `sensor.<vehicle>_last_checked` | timestamp (diagnostic) | when the last successful check ran |
| `button.<vehicle>_check_now` | button | check immediately |

### The one rule that shapes the whole design

**A failed check is never reported as "not registered".**

If a government site is down, geo-blocked, rate-limiting, or has been restyled,
`binary_sensor.<vehicle>_registered` goes **unavailable** — it does not go
*off*. An automation triggering on `to: "off"` therefore cannot fire because a
website had a bad morning. Use `binary_sensor.<vehicle>_check_failing` (or the
`aus_rego_check_failed` event) if you want to know about those separately.

---

## Jurisdiction support — read this before you install

There is no official public registration-check API in any Australian
jurisdiction. Every state runs a free public *website*, and several of them
protect it against automated use. This integration does **not** attempt to
defeat those protections.

| Jurisdiction | Automatic checks | Why |
| --- | --- | --- |
| **Queensland** | ✅ Working | Public form; verified end to end against the live service |
| **South Australia** | ✅ Expected to work | Plain form POST. Only answers requests from an Australian IP address |
| **Western Australia** | ✅ Expected to work | Public Wicket form; form handling verified against the live page |
| **ACT** | ✅ Expected to work | Public Wicket form; form handling verified against the live page |
| **New South Wales** | ❌ Blocked | Service NSW guards the free check with reCAPTCHA Enterprise |
| **Victoria** | ❌ Blocked | Service Victoria guards the check with reCAPTCHA |
| **Tasmania** | ⚠️ May work | Behind Cloudflare bot protection; often fine from a home connection |
| **Northern Territory** | ⚠️ May work | Behind Cloudflare bot protection; often fine from a home connection |

"Expected to work" means the request flow and the page parsing were built and
tested against the real pages, but the final lookup could not be exercised from
the machine this was developed on, because SA, NT, TAS and VIC geo-block or
challenge non-Australian addresses. From an Australian connection they should
behave as described — please open an issue if one does not.

### Every jurisdiction still works, via one of two fallbacks

**Manual mode** — you enter the expiry date once, from your renewal notice or
an official check. Home Assistant counts down from it. Every entity, event and
automation above behaves identically; only the automatic refresh is missing.
This is the recommended choice for NSW and Victoria.

**Custom REST API** — point the integration at any registration API you are
entitled to use (a commercial data provider, a fleet system, or your own script
in front of a state website). You supply the URL, and dotted JSON paths for the
status, expiry date and/or a registered boolean.

---

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/tunlezah/hassrego` as an **Integration**
3. Install **Australian Vehicle Registration**, then restart Home Assistant

### Manual

Copy `custom_components/aus_rego` into your `config/custom_components/`
directory and restart Home Assistant.

## Adding vehicles

**Settings → Devices & Services → Add Integration → Australian Vehicle
Registration.**

Enter the state or territory, the plate, and optionally a friendly name. The
integration performs one test lookup during setup so problems surface then
rather than at 7am — if the plate is not found, or the jurisdiction blocks
automated checks, it tells you and lets you decide.

**Add the integration again for each additional vehicle.** Each one gets its own
device, its own schedule and its own entities.

## Scheduling

Per vehicle, under **Configure**:

| Option | Default | Notes |
| --- | --- | --- |
| Check at | `07:00:00` | Local time |
| Check every (days) | `1` | 1 = daily, 7 = weekly |
| Warn this many days before expiry | `14` | Drives `expiring_soon` and the `aus_rego_expiring` event |
| Also check shortly after startup | on | Runs one minute after Home Assistant starts |
| Spread checks over (seconds) | `300` | A small stable per-vehicle offset so several vehicles do not hit the site at the same instant |

The stagger is derived from the plate, so it is the same every day rather than
random — predictable, and still polite to the upstream service.

## Automations

### The easy way: use the blueprint

`blueprints/automation/aus_rego/registration_alert.yaml` handles notification,
light flashing, expiry warnings and (optionally) check failures. Copy it into
`config/blueprints/automation/` and create an automation from it.

### Yes/no, by hand

```yaml
automation:
  - alias: "Rego lapsed - notify and flash the hallway light"
    triggers:
      - trigger: state
        entity_id: binary_sensor.corolla_registered
        to: "off"          # only fires on a definite "no"
    actions:
      - action: notify.mobile_app_pixel
        data:
          title: "Registration problem"
          message: >-
            {{ state_attr('binary_sensor.corolla_registered', 'status') }}
            (expired {{ state_attr('binary_sensor.corolla_registered', 'expiry') }})
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

```yaml
  - alias: "Rego is fine - green light"
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

### Expiry warning

```yaml
  - alias: "Rego expiring soon"
    triggers:
      - trigger: event
        event_type: aus_rego_expiring
    actions:
      - action: notify.persistent_notification
        data:
          title: "{{ trigger.event.data.vehicle_name }} rego expires soon"
          message: >-
            {{ trigger.event.data.days_remaining }} days left
            (expires {{ trigger.event.data.expiry }}).
```

### Knowing when a check failed

```yaml
  - alias: "Rego check is failing"
    triggers:
      - trigger: state
        entity_id: binary_sensor.corolla_check_failing
        to: "on"
        for: "24:00:00"     # ignore a one-off blip
    actions:
      - action: notify.persistent_notification
        data:
          message: >-
            Could not check the rego for a day:
            {{ state_attr('binary_sensor.corolla_check_failing', 'error') }}
```

## Events

| Event | When |
| --- | --- |
| `aus_rego_checked` | after every successful check |
| `aus_rego_status_changed` | when the status differs from last time (includes `previous_status`) |
| `aus_rego_expiring` | when expiry is within the warning window |
| `aus_rego_check_failed` | when a check could not get an answer (includes `reason`, `error`, `consecutive_failures`) |

Successful-check events carry `vehicle_name`, `plate`, `jurisdiction`,
`status`, `registered`, `expiry`, `days_remaining` and the vehicle details the
service returned.

## Services

**`aus_rego.check_now`** — re-check now. Target specific vehicles with
`entry_id`/`device_id`, or omit both to check all of them.

**`aus_rego.check_plate`** — look up any plate once, without adding a vehicle.
Returns the result to the caller:

```yaml
actions:
  - action: aus_rego.check_plate
    data:
      jurisdiction: qld
      plate: ABC123
    response_variable: rego
  - action: notify.persistent_notification
    data:
      message: "{{ rego.status }} until {{ rego.expiry }}"
```

## Fair use

This integration drives the same free public services you would use in a
browser, on your own vehicles. Please keep it that way:

- The default of one check per vehicle per day is deliberate. Checking every
  few minutes adds nothing — registration status changes yearly — and is rude
  to a public service.
- Queensland's check requires accepting TMR's terms of use. The setup flow asks
  you to accept them explicitly, because each check accepts them on your behalf.
- Nothing here bypasses CAPTCHAs, bot protection or logins. Where a jurisdiction
  has chosen to block automation, the integration reports that and offers manual
  mode instead.

## Troubleshooting

**Status is `unknown` and entities are unavailable** — the check could not get
an answer. Check `binary_sensor.<vehicle>_check_failing` for the reason, or
download diagnostics from the device page.

**`geo_blocked`** — that state only answers from an Australian IP. If Home
Assistant runs on a VPS or through a VPN that exits overseas, the check will
fail; use manual mode or route it through an Australian connection.

**`blocked`** — bot protection challenged the request. Try again later; if it
persists, switch to manual mode.

**`parse_error`** — the site loaded but no longer looks the way the provider
expects, which usually means it was redesigned. Please open an issue.

**Plate not found at setup** — nearly always a typo, or the vehicle is
registered in a different state.

## Development

```bash
python3 -m pytest tests/ -q      # 90 tests, no Home Assistant needed
python3 -m ruff check custom_components tests
```

Parsing, status derivation and scheduling deliberately have no Home Assistant
imports, so the logic that decides whether your automation fires is directly
testable. Adding a jurisdiction means adding one file under
`custom_components/aus_rego/providers/` and registering it in that package's
`__init__.py`.

## Disclaimer

Information comes from each jurisdiction's own public service and may be cached
or briefly out of date. For anything that matters legally, check the official
website directly. This project is not affiliated with any Australian government
agency.

## Licence

MIT — see [LICENSE](LICENSE).
