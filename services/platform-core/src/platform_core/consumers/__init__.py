"""Platform event consumers (SPRINT-008B).

Every module in this package self-registers its consumers on import;
`discover_consumers()` imports them all at startup. Consumers are
COMPLETELY independent from business modules: business code never imports
from here, and nothing here is imported by business code.
"""
