"""How a household reaches its own bill (WO-86).

Two doors, both opened by the dairy from the customer's page and both bound
to ONE customer before anything can be read:

* a **login** — an invitation that carries the customer id, so the account
  it creates is customer-scoped from its first request (DEMO-012 closed the
  read side; this closes the way in);
* a **bill link** — a capability URL for the household that will never
  install an app, carrying a random token whose hash is the only thing
  stored.

The module owns the bill token. Logins stay where accounts live
(`organization.Invitation`, `identity.User`); this module composes those
services and adds no second copy of either.
"""
