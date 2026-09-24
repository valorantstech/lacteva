"""The product modules an organisation has turned on (D-31 · WO-85).

Owner decision D-31, 2026-09-25, verbatim: "we are doing these changes for
dairy retail shops, dont remove what we have created earlier i mean earlier
dairy firm logic is also required where farmer is delivering milk in the
firm, some dairy firm also have retail, they sell and purchase both. so make
everything customizable."

So an organisation is not a dairy OR a shop — a binary would force the dairy
firm that also runs a retail counter, a common shape in India, to lose half
the product. It has a LIST of modules, exactly as `supported_languages` is a
list on the same model, and the navigation is the union of what the enabled
modules contribute:

  * `collection` — milk coming IN from suppliers: centres, suppliers,
    transactions, day book, rate cards, matrices, playground, settlements,
    supplier payments and receipts.
  * `sales` — milk going OUT to customers: customers, deliveries, routes and
    runs, billing, who owes money, and the product catalogue.

Three shapes, all first-class: `["collection", "sales"]` is a dairy firm
that also retails and is the product as it is today; `["collection"]` is a
classic dairy firm; `["sales"]` is a milk shop that buys from a tabela and
delivers to four hundred flats. None is a cut-down mode of another. An
organisation with NEITHER is refused — a tenant with no modules has no
product.

**This is a PRESENTATION fact and nothing else.** Enabling or disabling a
module hides its navigation. It deletes no row, archives nothing, closes no
period, and makes no URL or API refuse. No permission, no policy and no
business rule may branch on it — `test_modules.py` greps this package for a
branch on `modules` outside the places that only SAY what is enabled, so
that this flag cannot grow teeth quietly.

A registry, in code, so that a third module later is one entry here and one
entry in the portal's registry rather than a search through the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    key: str
    #: What the settings screen calls the switch, in the owner's own words.
    label: str
    #: One sentence a person reads before flipping it.
    description: str


MODULES: dict[str, Module] = {
    "collection": Module(
        key="collection",
        label="This organisation collects milk from suppliers",
        description=(
            "Centres, suppliers, intake, rate cards, settlements and supplier payments. "
            "Farmers deliver milk; the organisation pays them."
        ),
    ),
    "sales": Module(
        key="sales",
        label="This organisation sells milk to customers",
        description=(
            "Customers, deliveries, routes, bills and who owes money. "
            "Households and shops take milk; the organisation bills them."
        ),
    ),
}

#: What every organisation that exists when this lands has, and what a new
#: one gets when nobody says otherwise: everything. D-31 §2 — "dont remove
#: what we have created earlier".
DEFAULT_MODULES: tuple[str, ...] = tuple(MODULES)


def validate_modules(value: list[str] | tuple[str, ...] | None) -> list[str]:
    """The canonical list: known keys, de-duplicated, in registry order,
    never empty. `None` means the default.

    Raises `ValueError` — the boundary that knows about HTTP turns it into
    the caller's 422.
    """
    if value is None:
        return list(DEFAULT_MODULES)
    cleaned = {str(key).strip().lower() for key in value}
    unknown = sorted(cleaned - set(MODULES))
    if unknown:
        raise ValueError(
            f"unknown module(s) {', '.join(unknown)} — the modules are {', '.join(MODULES)}"
        )
    ordered = [key for key in MODULES if key in cleaned]
    if not ordered:
        raise ValueError(
            "an organisation needs at least one module — collecting milk from suppliers, "
            "selling milk to customers, or both"
        )
    return ordered


def module_choices() -> list[dict[str, str]]:
    """The registry as the settings screen lists it."""
    return [
        {"key": module.key, "label": module.label, "description": module.description}
        for module in MODULES.values()
    ]
