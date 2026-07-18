"""Convert 5etools JSON entries into Campaign_Nexus documents.

Pure, data-free converters shared by ``scripts/import_5etools.py`` and the tests. This
package ships **no game content** — it only knows how to reshape entries the caller reads
from a local 5etools checkout. 5etools text is largely copyrighted; nothing here is
committed with data, and the importer writes rows only into the local database.

See ``docs`` / the import plan for the field mappings. Entry point functions:

- :func:`import5e.monsters.to_monster_doc`  -> ``dnd5e`` monster ``doc``
- :func:`import5e.items.to_library_entry`   -> equipment ``LibraryEntry`` fields
- :func:`import5e.spells.to_spell`          -> spell catalog fields
"""

from __future__ import annotations
