"""Write icons.json: the icon set every engine firmware embeds, by name.

Usage: gen_icons.py <materialdesignicons-webfont.ttf> <out icons.json>

Each icon has a code point and the icon-set level that added it. Level 1 is
the list of contract version 1, level 2 the icons version 2 adds. A later
contract adds icons at a higher level; it never removes or renumbers one.
The tablet reports the level it has; Home Assistant sends the fallback glyph
for icons above that level.
"""

import json
import struct
import sys

LEVEL_1 = """
home sofa bed silverware-fork-knife shower lightbulb thermometer shield-home speaker
television garage flower desk baby-face-outline washing-machine weather-partly-cloudy
cctv lightning-bolt music star view-dashboard
lightbulb-on lightbulb-outline lightbulb-group fan blinds lock lock-open lock-outline
thermostat gauge chart-line palette account account-multiple shield-off shield-lock
arrow-up arrow-down arrow-left arrow-right stop play pause play-pause skip-next
skip-previous music-note volume-high volume-medium volume-off plus minus power
check close chevron-left chevron-right chevron-up chevron-down
alert-circle-outline help-circle-outline image-outline image-off-outline
wifi-off lan-disconnect home-assistant tablet tablet-dashboard cog information-outline
weather-sunny weather-night weather-cloudy weather-fog weather-hail weather-lightning
weather-lightning-rainy weather-pouring weather-rainy weather-snowy weather-snowy-rainy
weather-windy weather-windy-variant weather-cloudy-alert
door door-open window-closed window-open garage-open water-percent water fire snowflake
motion-sensor bell robot-vacuum ceiling-light floor-lamp lamp led-strip-variant
power-plug toggle-switch car calendar clock-outline
""".split()

LEVEL_2 = """
home-thermometer home-floor-g home-floor-0 home-floor-1 home-floor-2
wall-sconce-flat desk-lamp outdoor-lamp string-lights track-light
lightbulb-off lightbulb-multiple light-switch brightness-6 palette-outline
creation white-balance-sunny movie-open spa leaf book-open-variant
moon-waning-crescent sleep weather-sunset coffee-maker dishwasher
tumble-dryer fridge-outline stove pot-steam kettle sprinkler flash
solar-power ev-station car-electric transmission-tower molecule-co2
air-filter air-purifier air-humidifier air-conditioner radiator
water-boiler water-pump fan-off autorenew rocket-launch home-export-outline
thermometer-low thermometer-high blinds-open window-shutter
window-shutter-open gate gate-open garage-alert door-closed angle-acute
lock-alert shield-check shield-alert shield-outline bell-ring bell-off
smoke-detector pipe-leak walk umbrella alarm timer-outline calendar-today
check-circle toggle-switch-off gesture-tap-button script-text-outline
numeric dots-horizontal map-marker shuffle repeat volume-mute volume-low
speaker-multiple cast television-play battery battery-50 battery-20
battery-charging battery-alert
""".split()

LEVELS = ((1, LEVEL_1), (2, LEVEL_2))

# The 258 standard Macintosh glyph names, in the order of the 'post' table. A
# format 2 table names a glyph by its index in this list, or from 258 up by a
# string of its own.
MAC_GLYPHS = """
.notdef .null nonmarkingreturn space exclam quotedbl numbersign dollar percent
ampersand quotesingle parenleft parenright asterisk plus comma hyphen period slash
zero one two three four five six seven eight nine colon semicolon less equal greater
question at A B C D E F G H I J K L M N O P Q R S T U V W X Y Z bracketleft backslash
bracketright asciicircum underscore grave a b c d e f g h i j k l m n o p q r s t u v
w x y z braceleft bar braceright asciitilde Adieresis Aring Ccedilla Eacute Ntilde
Odieresis Udieresis aacute agrave acircumflex adieresis atilde aring ccedilla eacute
egrave ecircumflex edieresis iacute igrave icircumflex idieresis ntilde oacute ograve
ocircumflex odieresis otilde uacute ugrave ucircumflex udieresis dagger degree cent
sterling section bullet paragraph germandbls registered copyright trademark acute
dieresis notequal AE Oslash infinity plusminus lessequal greaterequal yen mu
partialdiff summation product pi integral ordfeminine ordmasculine Omega ae oslash
questiondown exclamdown logicalnot radical florin approxequal Delta guillemotleft
guillemotright ellipsis nonbreakingspace Agrave Atilde Otilde OE oe endash emdash
quotedblleft quotedblright quoteleft quoteright divide lozenge ydieresis Ydieresis
fraction currency guilsinglleft guilsinglright fi fl daggerdbl periodcentered
quotesinglbase quotedblbase perthousand Acircumflex Ecircumflex Aacute Edieresis
Egrave Iacute Icircumflex Idieresis Igrave Oacute Ocircumflex apple Ograve Uacute
Ucircumflex Ugrave dotlessi circumflex tilde macron breve dotaccent ring cedilla
hungarumlaut ogonek caron Lslash lslash Scaron scaron Zcaron zcaron brokenbar Eth eth
Yacute yacute Thorn thorn minus multiply onesuperior twosuperior threesuperior onehalf
onequarter threequarters franc Gbreve gbreve Idotaccent Scedilla scedilla Cacute
cacute Ccaron ccaron dcroat
""".split()


def _tables(data):
    count = struct.unpack(">H", data[4:6])[0]
    out = {}
    for i in range(count):
        tag, _, off, length = struct.unpack(">4sIII", data[12 + 16 * i : 28 + 16 * i])
        out[tag.decode()] = (off, length)
    return out


def _cmap(data, tables):
    off, _ = tables["cmap"]
    count = struct.unpack(">H", data[off + 2 : off + 4])[0]
    best = None
    for i in range(count):
        _, _, sub = struct.unpack(">HHI", data[off + 4 + 8 * i : off + 12 + 8 * i])
        if struct.unpack(">H", data[off + sub : off + sub + 2])[0] == 12:
            best = off + sub
    if best is None:
        raise SystemExit("no format-12 cmap")
    groups = struct.unpack(">I", data[best + 12 : best + 16])[0]
    out = {}
    for i in range(groups):
        start, end, glyph = struct.unpack(
            ">III", data[best + 16 + 12 * i : best + 28 + 12 * i]
        )
        for code in range(start, end + 1):
            out[code] = glyph + code - start
    return out


def _names(data, tables):
    off, length = tables["post"]
    if struct.unpack(">I", data[off : off + 4])[0] != 0x00020000:
        raise SystemExit("post table is not format 2")
    count = struct.unpack(">H", data[off + 32 : off + 34])[0]
    index = struct.unpack(f">{count}H", data[off + 34 : off + 34 + 2 * count])
    pos = off + 34 + 2 * count
    strings = []
    while pos < off + length:
        size = data[pos]
        strings.append(data[pos + 1 : pos + 1 + size].decode("latin1"))
        pos += 1 + size
    return [strings[i - 258] if i >= 258 else MAC_GLYPHS[i] for i in index]


def main() -> None:
    data = open(sys.argv[1], "rb").read()
    tables = _tables(data)
    names = _names(data, tables)
    by_name = {
        names[glyph]: code
        for code, glyph in _cmap(data, tables).items()
        if glyph < len(names)
    }
    icons = {}
    missing = []
    for level, names_of_level in LEVELS:
        for name in names_of_level:
            if name not in by_name:
                missing.append(name)
                continue
            icons[f"mdi:{name}"] = [by_name[name], level]
    if missing:
        raise SystemExit("not in the font: " + " ".join(missing))
    out = {
        "version": LEVELS[-1][0],
        "fallback": "mdi:help-circle-outline",
        "placeholder": "mdi:image-outline",
        "icons": dict(sorted(icons.items())),
    }
    with open(sys.argv[2], "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=1, sort_keys=False)
        handle.write("\n")
    print(f"{len(icons)} icons")


if __name__ == "__main__":
    main()
