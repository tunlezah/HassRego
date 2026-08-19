# Tests

These cover the layers that decide whether your automation fires:

* **`test_parsing.py`** — each jurisdiction's result layout, including the
  Queensland fixture captured from the live service (identifying values
  replaced with synthetic data).
* **`test_safety.py`** — the invariant that a failed check is never reported as
  "not registered": bot walls, geo-blocks and broken pages must raise rather
  than parse.
* **`test_not_found_tiers.py`** — "no record of that plate" is detected, while
  outage pages and help text that merely mention the words are not.
* **`test_schedule.py`** — "7am every day" and every variation of it.
* **`test_providers.py`** — provider behaviour through a fake HTTP client.
* **`test_flows.py`** — the multi-step request sequences (Queensland's terms
  acceptance, the WA and ACT Wicket forms).

They run without Home Assistant installed:

```bash
python3 -m pytest tests/ -q
```
