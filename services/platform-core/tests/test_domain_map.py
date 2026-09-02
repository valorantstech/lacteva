"""The URL map, as a contract (WO-63 · LACTEVA-DEPLOY-004 · D-20).

Four names, one address, one certificate:

    lacteva.com, www.lacteva.com   the marketing site
    app.lacteva.com                the admin portal
    api.lacteva.com                the API — what the mobile app calls
    dev.phoenixsoft.in             unchanged: portal AND API

Two of these are load-bearing in a way a reader cannot see from the config
alone, so they are asserted here.

**`dev.phoenixsoft.in` must keep serving the API.** Every demo handset in the
field was built against it, and `LACTEVA_API_URL` is a compile-time constant
in `main.dart` — a name that stops answering is a store release, not a config
change, and the installs in between are simply broken.

**An unrecognised name must be refused, not served.** nginx makes the FIRST
matching server block the default when none is marked, so without a deliberate
default the marketing site would answer for every stale record and every scan
of the IP address — and would look, to anyone reading the config, like it had
been meant.
"""

import re

import pytest

from tests.test_deployment import REPO, _location_blocks, _vhost_conf


def _server_blocks() -> list[tuple[str, str]]:
    """Every `server { }` block in the vhost config, as (server_name, body)."""
    conf = (REPO / "infra/nginx/conf.d/lacteva.conf").read_text()
    blocks = []
    for match in re.finditer(r"^server\s*\{", conf, re.MULTILINE):
        start = match.start()
        brace = conf.find("{", start)
        depth, j = 0, brace
        while j < len(conf):
            if conf[j] == "{":
                depth += 1
            elif conf[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = conf[brace : j + 1]
        name = re.search(r"server_name\s+([^;]+);", body)
        blocks.append((name.group(1).strip() if name else "", body))
    return blocks


def _tls_blocks() -> list[tuple[str, str]]:
    return [(n, b) for n, b in _server_blocks() if "listen 443" in b]


@pytest.mark.parametrize(
    "hostname",
    ["lacteva.com", "www.lacteva.com", "app.lacteva.com", "api.lacteva.com", "dev.phoenixsoft.in"],
)
def test_every_name_in_the_map_has_a_server_block(hostname):
    served = {name for names, _ in _tls_blocks() for name in names.split()}
    assert hostname in served, f"{hostname} is in the URL map and in no server block"


def test_dev_phoenixsoft_still_serves_the_api_the_handsets_were_built_against():
    """The one that costs a store release to get wrong."""
    block = next(b for n, b in _tls_blocks() if "dev.phoenixsoft.in" in n.split())
    assert "locations-api.inc" in block, (
        "dev.phoenixsoft.in no longer serves /v1/ — every installed demo handset "
        "carries this name as a build-time constant and would lose its server"
    )
    assert "locations-portal.inc" in block, "dev.phoenixsoft.in stopped serving the portal"


def test_the_api_name_serves_the_api():
    block = next(b for n, b in _tls_blocks() if n.split() == ["api.lacteva.com"])
    assert "locations-api.inc" in block
    assert "locations-portal.inc" not in block, (
        "api.lacteva.com serves the portal — the API host answers machines, and a "
        "browser page here would be an accident waiting to be depended on"
    )
    assert "locations-marketing.inc" not in block


def test_the_marketing_site_is_served_only_on_the_public_names():
    marketing = [n for n, b in _tls_blocks() if "locations-marketing.inc" in b]
    assert marketing, "the marketing site is in the stack and served nowhere"
    for names in marketing:
        assert set(names.split()) == {"lacteva.com", "www.lacteva.com"}, (
            f"the marketing site answers on {names} — it holds no session and no "
            "tenant data, and it must not stand in front of anything that does"
        )
    # And the converse: the product names must not reach the website upstream.
    for names, body in _tls_blocks():
        if "app.lacteva.com" in names or "api.lacteva.com" in names:
            assert "lacteva_marketing" not in body


def test_an_unrecognised_name_is_refused_rather_than_given_a_site():
    defaults = [(n, b) for n, b in _tls_blocks() if "default_server" in b]
    assert len(defaults) == 1, (
        "exactly one TLS block must be the default, or nginx picks the first one "
        f"it parsed and the choice is made by file order: {[n for n, _ in defaults]}"
    )
    _name, body = defaults[0]
    assert "return 421" in body, "the default server serves something instead of refusing"
    for include in ("locations-marketing.inc", "locations-portal.inc", "locations-api.inc"):
        assert include not in body, f"the default server serves {include} to any name at all"


def test_the_refusal_says_where_to_go_instead():
    """A refusal a person cannot act on is a refusal they will report as an
    outage. 444 closes the connection and reads as a network fault; this one
    names the hosts that do work."""
    _name, body = next((n, b) for n, b in _tls_blocks() if "default_server" in b)
    for hostname in ("lacteva.com", "app.lacteva.com", "api.lacteva.com"):
        assert hostname in body


def test_the_acme_challenge_still_answers_for_every_name():
    """Renewal is http-01 on port 80 for all five names. The port-80 block is
    deliberately still a catch-all: a name that cannot answer a challenge
    cannot be renewed, and the certificate covers all five."""
    port80 = [b for n, b in _server_blocks() if "listen 80" in b]
    assert len(port80) == 1 and "server_name _;" in port80[0]
    assert "/.well-known/acme-challenge/" in port80[0]


def test_every_tls_block_terminates_on_the_same_terms():
    """One certificate, one protocol floor, one cipher list — from one file.
    Four copies of a cipher list is three chances to update only some."""
    for names, body in _tls_blocks():
        assert "include /etc/nginx/conf.d/tls.inc;" in body, f"{names} terminates TLS its own way"
        assert "ssl_ciphers" not in body, f"{names} carries its own cipher list"


def test_the_stack_serves_the_marketing_site_and_it_depends_on_nothing():
    import yaml

    compose = yaml.safe_load((REPO / "docker-compose.production.yml").read_text())
    assert "marketing" in compose["services"], "MARKETING-001: the site is served from nowhere"
    site = compose["services"]["marketing"]
    assert "depends_on" not in site, (
        "the website waits on the platform — a database outage would then take the "
        "public site down with it, and the site needs neither"
    )
    assert "healthcheck" in site
    assert "marketing" in compose["services"]["nginx"]["depends_on"], (
        "nginx fronts the site without waiting for it: the first request after a "
        "restart is a 502 on the company's front page"
    )


def test_the_marketing_image_is_pinned_to_the_deployed_tag():
    """Never `:latest`, and never a tag of its own: the site ships from the
    same commit as everything else, so one deploy moves one platform."""
    import yaml

    image = yaml.safe_load((REPO / "docker-compose.production.yml").read_text())["services"][
        "marketing"
    ]["image"]
    # Split on the FIRST colon after the repository: the pin's own error
    # message contains the word ":latest", so `rsplit` lands inside it.
    tag = image.split("}:", 1)[1]
    assert tag.startswith("marketing-${LACTEVA_IMAGE_TAG"), (
        f"the site is not pinned to the deploy's tag: {tag}"
    )
    assert "${LACTEVA_IMAGE_TAG:?" in tag, "an unset tag must refuse to start, not default"


def test_the_website_and_the_product_are_different_upstreams():
    conf = (REPO / "infra/nginx/conf.d/lacteva.conf").read_text()
    assert "upstream lacteva_marketing" in conf
    marketing = (REPO / "infra/nginx/conf.d/locations-marketing.inc").read_text()
    for forbidden in ("lacteva_portal", "lacteva_api"):
        assert forbidden not in marketing, (
            f"the public website proxies to {forbidden} — nothing on it should be "
            "able to reach a dairy's data"
        )


def test_the_privacy_policy_is_a_page_on_the_public_site():
    """The Play Console listing points at it, so it must be reachable without
    a session, on a name a stranger can resolve, forever."""
    page = REPO / "apps/marketing-site/src/app/privacy-policy/page.tsx"
    assert page.exists(), "no privacy policy page — the Play listing has nowhere to point"
    marketing = [n for n, b in _tls_blocks() if "locations-marketing.inc" in b]
    assert any("lacteva.com" in n for n in marketing)
    # Nothing in the way of it: the site's locations carry no auth guard.
    body = (REPO / "infra/nginx/conf.d/locations-marketing.inc").read_text()
    for guard in ("auth_basic", "auth_request", "deny all"):
        assert guard not in body, f"the public site is behind {guard}"


def test_no_location_that_serves_the_site_forgets_the_security_headers():
    conf = _vhost_conf()
    offenders = [
        name
        for name, body in _location_blocks(conf)
        if "lacteva_marketing" in body
        and "include /etc/nginx/conf.d/security-headers.inc;" not in body
    ]
    assert not offenders, offenders


# --- the outage this batch caused, and the guard that would have caught it ---
#
# The first deploy of the marketing site failed at `compose up`, AFTER the
# release tree had been staged and `current` repointed: `MARKETING_IMAGE` was
# unset on the host, so its default — a BARE repository name — was resolved
# against Docker Hub, where it does not exist. The automatic rollback then put
# the previous image tag back beside the NEW nginx configuration, which
# referenced an upstream container that no longer existed, and nginx refused
# to start. Five minutes of total outage, caused by the recovery path.
#
# Two things were wrong and both are pinned here: the deploy pulled only ONE
# of the three images it runs, and the example environment documented only one
# of the variables that name them.


def test_the_deploy_pulls_every_image_before_it_stages_anything():
    """A missing image must fail where a missing tag fails: before the release
    tree is staged, while the old version is still serving."""
    script = (REPO / "infra/deploy/deploy.sh").read_text()
    pull_step = script.split("--- 2. pre-flight backup")[0]
    for variable in ("LACTEVA_IMAGE", "PORTAL_IMAGE", "MARKETING_IMAGE"):
        assert variable in pull_step, (
            f"{variable} is not read in step 1 — a deploy that cannot fetch its "
            "image discovers this after the stack has been changed"
        )
    # One pull per image the stack runs, and the marketing one carries its
    # prefix: pulling `:${TAG}` from that repository would fetch the PORTAL.
    assert pull_step.count("docker pull") >= 3, "not every image is pulled up front"
    assert "marketing-${TAG}" in pull_step


def test_every_image_the_stack_runs_is_named_by_a_documented_variable():
    """A bare default resolves against Docker Hub. Every deployment that uses a
    private registry must therefore SET each of these, so each must be in the
    example — the file an operator fills in."""
    import re

    compose = (REPO / "docker-compose.production.yml").read_text()
    example = (REPO / ".env.production.example").read_text()
    # Image variables of our own: `${X_IMAGE:-lacteva/...}`.
    variables = set(re.findall(r"\$\{([A-Z_]*IMAGE)(?::-lacteva/[^}]*)?\}", compose))
    ours = {v for v in variables if v.endswith("IMAGE") and not v.endswith("IMAGE_TAG")}
    assert ours, "no image variables found — the pattern this test guards has changed"
    for variable in sorted(ours):
        assert f"\n{variable}=" in example, (
            f"{variable} names an image the stack runs and the example environment "
            "does not set it, so a deployment on a private registry will look for "
            "it on Docker Hub"
        )
