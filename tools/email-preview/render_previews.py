#!/usr/bin/env python3
"""Every email template, rendered as it would be sent (WO-105 §7).

Writes one HTML file per (template, language) to
`modules/notification/previews/`, from the ONE set of sample values in
`email_design.preview_samples()`. `tools/email-preview/screenshot.js` then
photographs each at 600px and 375px; `tests/test_email_design.py` fails when
the wrapper changes and these were not regenerated, so a reviewer always
sees the email in the diff.

    services/platform-core/.venv/bin/python tools/email-preview/render_previews.py
    services/platform-core/.venv/bin/python tools/email-preview/render_previews.py --check
"""

from __future__ import annotations

import pathlib
import sys
import uuid

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/platform-core/src"))
OUT = REPO / "services/platform-core/src/platform_core/modules/notification/previews"


def rendered_previews() -> dict[str, str]:
    from platform_core.modules.notification.email_design import (
        SAMPLE_SENDER,
        email_parts,
        preview_samples,
    )
    from platform_core.modules.notification.providers import OutboundMessage, email_html
    from platform_core.modules.notification.templates import TEMPLATES, render

    pages: dict[str, str] = {}
    for template in TEMPLATES:
        if template.channel != "email":
            continue
        variables, secrets = preview_samples(template.key)
        # `render` refuses a value nobody displays (DEMO-032 §8); the samples
        # carry a few for the design (organisation, portal), so the text is
        # rendered from what THIS template knows.
        known = set(template.variables) | set(template.optional_variables)
        message = render(
            template, {k: v for k, v in {**variables, **secrets}.items() if k in known}
        )
        pages[f"{template.key}.{template.language}.html"] = email_html(
            OutboundMessage(
                channel="email",
                recipient="preview@example.invalid",
                title=message.title,
                body=message.body,
                language=template.language,
                template_key=template.key,
                notification_id=uuid.UUID(int=0),
                highlight=next(iter(secrets.values())) if len(secrets) == 1 else None,
                presentation=email_parts(
                    template.key, template.language, variables, secrets, SAMPLE_SENDER
                ),
            )
        )
    return pages


def main(argv: list[str]) -> int:
    pages = rendered_previews()
    if "--check" in argv:
        stale = [
            name
            for name, html in pages.items()
            if not (OUT / name).exists() or (OUT / name).read_text() != html
        ]
        if stale:
            print("stale previews: " + ", ".join(stale))  # noqa: T201
            return 1
        print(f"{len(pages)} previews current")  # noqa: T201
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, html in pages.items():
        (OUT / name).write_text(html)
    print(f"wrote {len(pages)} previews to {OUT.relative_to(REPO)}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
