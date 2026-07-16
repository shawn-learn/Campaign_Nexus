"""Fix Windows-1252 smart quotes / dashes in equipment module files."""
import pathlib

BAD_BYTES = {
    b'\x97': b'-',   # em-dash
    b'\x96': b'-',   # en-dash
    b'\x93': b'"',   # left double quote
    b'\x94': b'"',   # right double quote
    b'\x91': b"'",   # left single quote
    b'\x92': b"'",   # right single quote
}

files = [
    'app/modules/equipment/service.py',
    'app/modules/equipment/projectors.py',
    'app/modules/equipment/router.py',
    'app/modules/equipment/schemas.py',
    'app/main.py',
]

for fname in files:
    p = pathlib.Path(fname)
    data = p.read_bytes()
    for bad, good in BAD_BYTES.items():
        data = data.replace(bad, good)
    p.write_bytes(data)
    print(f'fixed {fname}')
