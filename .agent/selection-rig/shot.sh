#!/bin/sh
# uso: shot.sh nome  → rig/nome.png (toglie il warning "Multiple displays" davanti al PNG)
D=$(dirname "$0"); adb exec-out screencap -p > "$D/$1.raw"
python3 - "$D/$1.raw" "$D/$1.png" <<'PY'
import sys; b=open(sys.argv[1],'rb').read(); i=b.find(b'\x89PNG'); open(sys.argv[2],'wb').write(b[i:] if i>=0 else b)
PY
rm -f "$D/$1.raw"; echo "$D/$1.png"
