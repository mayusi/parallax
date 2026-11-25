# field — where every piece came from

| file | source |
| --- | --- |
| icon_rifle | kit ui ink --mode icon from build/renders/arp_ref_side_shaded.png (the kit's own ARP build, 3D lane) — outline + TEED interior lines + faint fill + dark halo |
| icon_rifle_small | the same render, --lines none --outline-px 7 (an outline that survives 54 px in the kill feed) |
| icon_pistol | kit ui ink --mode icon from build/renders/glock17_p_side.png (the kit's own Glock 17 build, owner-rated 85) |
| icon_frag | kit ui ink --mode icon from a GENERATED studio photo (kit vision concept, FLUX.2 klein, seed 3: build/vision/field_frag.png) |
| icon_flash | kit ui ink --mode icon from a GENERATED studio photo (kit vision concept, FLUX.2 klein, seed 5: build/vision/field_flash.png) |
| minimap, compass_strip, view_cone | drawn by script: _scratch/ui_field/make_field_art.py (an original town, a 360-degree strip in Roboto Condensed, a soft wedge) |
| mag_outline, mag_fill | drawn by script: _scratch/ui_field/make_field_art.py `magazine()` — a curved rifle magazine, outline + solid (the HUD clips the solid one to how full a magazine feels) |
| chevron_down | drawn by script: _scratch/ui_field/make_field_art.py `chevron()` — a teammate marker over the head |
