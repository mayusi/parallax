<!-- reference for the parallax-ui route card; verbatim from the skill page (2026-10-16) -->

## Fonts
The preview draws Roblox's faces for real: `kit/ui/fonts.json` maps every Enum.Font to its Google Fonts family
(OFL / Apache / UFL only, sha256-pinned in `fonts.lock.json`, fetched by `kit ui fonts`). Roblox's proprietary
faces (Gotham, Builder Sans) and its renamed ones (Garamond = Guru, Bodoni = Accanthis…) draw with their
nearest free twin and say so. Roblox cannot take a custom TTF (2026): pick from Enum.Font.
Baked pieces (`render`, `letter`) take the UPRIGHT file of a family unless the fonts.json entry says `"italic": true`
(Name-Italic[wght].ttf sorts before Name[wght].ttf: until 2026-10-16 13 faces baked slanted, YOU DIED among them).
