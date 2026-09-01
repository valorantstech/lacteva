"""The animals this platform knows milk can come from (WO-55, WO-56).

A vocabulary rather than a module's constant, because two modules now depend
on it agreeing: `milk_collection` records what arrived at a centre by type,
and `dispatch` records what left by the same type. A day book that subtracts
one from the other is arithmetic on a shared vocabulary — duplicating the
tuple in the second module would mean the day a seventh animal is added, one
side of the subtraction knows about it and the other does not.

`custom` is the deliberate escape hatch: the free-text name travels with the
transaction, and every aggregate reports it as `custom`. A dairy typing
"camel" gets its milk counted; it does not get a category the platform never
agreed to.
"""

from __future__ import annotations

#: WO-55 added `sheep`: the one common Indian dairy animal the vocabulary
#: omitted, which a dairy taking it had to record as `custom` — priced and
#: reported as "custom" rather than as itself.
MILK_TYPES = ("cow", "buffalo", "goat", "sheep", "mixed", "custom")
