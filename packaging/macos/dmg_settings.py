# Settings of dmgbuild for the disk image of Audiotext (see make_dmg.sh), which passes
# the app and the folder of this file with -D. The layout is the one of the background.
import os.path
import sys

# The -D values, which dmgbuild sets before running this file
defines: dict[str, str] = globals()["defines"]

sys.path.insert(0, defines["here"])
from make_dmg_background import (  # type: ignore[import-not-found]  # noqa: E402
    APP_POS,
    APPS_POS,
    ICON_SIZE,
    H,
    W,
)

format = "UDZO"
files = [(defines["app"], "Audiotext.app")]
symlinks = {"Applications": "/Applications"}
# Without hide_extensions: the flag it sets on the app breaks its signature

# dmgbuild combines it with dmg-background@2x.png for Retina displays
background = os.path.join(defines["here"], "dmg-background.png")
window_rect = ((200, 120), (W, H))
icon_size = ICON_SIZE
text_size = 13
icon_locations = {"Audiotext.app": APP_POS, "Applications": APPS_POS}
