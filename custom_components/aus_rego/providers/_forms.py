"""Read HTML forms so stateful portals can be driven correctly.

The WA and ACT services are Apache Wicket applications and the Queensland one
is JSF/PrimeFaces. All three put per-session state into the form action URL and
into hidden fields, so a working request has to start by reading the real form
off the page rather than by hard-coding a URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin


@dataclass(slots=True)
class Form:
    """A parsed HTML form."""

    action: str
    method: str = "post"
    fields: dict[str, str] = field(default_factory=dict)
    form_id: str = ""
    form_name: str = ""

    def absolute_action(self, page_url: str) -> str:
        """Resolve the form action against the page it was found on."""
        return urljoin(page_url, self.action) if self.action else page_url

    def payload(self, **overrides: str) -> dict[str, str]:
        """Return the form's fields with the given overrides applied."""
        data = dict(self.fields)
        data.update(overrides)
        return data


class _FormParser(HTMLParser):
    """Collect every form on a page along with its submittable fields."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[Form] = []
        self._current: Form | None = None
        self._select_name: str | None = None
        self._select_has_value = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            self._current = Form(
                action=attr.get("action", ""),
                method=(attr.get("method") or "get").lower(),
                form_id=attr.get("id", ""),
                form_name=attr.get("name", ""),
            )
            return
        if self._current is None:
            return

        if tag == "input":
            name = attr.get("name")
            if not name:
                return
            input_type = (attr.get("type") or "text").lower()
            if input_type in ("submit", "button", "image", "reset"):
                # Submit buttons are only sent when clicked; providers add the
                # one they mean explicitly.
                return
            if input_type in ("checkbox", "radio"):
                if "checked" in attr:
                    self._current.fields[name] = attr.get("value", "on")
                elif name not in self._current.fields:
                    self._current.fields.setdefault(name, "")
                return
            self._current.fields[name] = attr.get("value", "")
        elif tag == "select":
            self._select_name = attr.get("name")
            self._select_has_value = False
            if self._select_name:
                self._current.fields.setdefault(self._select_name, "")
        elif tag == "option" and self._select_name:
            if "selected" in attr:
                self._current.fields[self._select_name] = attr.get("value", "")
                self._select_has_value = True
            elif not self._select_has_value:
                # Fall back to the first option, as a browser would.
                self._current.fields[self._select_name] = attr.get("value", "")
        elif tag == "textarea":
            name = attr.get("name")
            if name:
                self._current.fields.setdefault(name, "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._current is not None:
            self.forms.append(self._current)
            self._current = None
        elif tag == "select":
            self._select_name = None


def parse_forms(html: str) -> list[Form]:
    """Return every form on the page."""
    parser = _FormParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    # An unclosed <form> still carries usable state.
    if parser._current is not None:
        parser.forms.append(parser._current)
    return parser.forms


def find_form(
    html: str,
    *,
    form_id: str | None = None,
    name: str | None = None,
    contains_field: str | None = None,
    action_contains: str | None = None,
) -> Form | None:
    """Find the form matching every supplied criterion."""
    for form in parse_forms(html):
        if form_id and form.form_id != form_id:
            continue
        if name and form.form_name != name:
            continue
        if contains_field and contains_field not in form.fields:
            continue
        if action_contains and action_contains not in form.action:
            continue
        return form
    return None


def find_field_name(html: str, *substrings: str) -> str | None:
    """Find an input whose name or id contains one of ``substrings``.

    Wicket rewrites component paths between releases, so matching on a stable
    fragment such as ``plateField`` is more durable than a full path.
    """
    lowered = [s.lower() for s in substrings]
    for form in parse_forms(html):
        for field_name in form.fields:
            low = field_name.lower()
            if any(s in low for s in lowered):
                return field_name
    return None
