#!/usr/bin/env python3
"""pptx のスライドを、measure-html.mjs と同じ物差しで数える（python-pptx が要る）。
  python3 measure-pptx.py <名前> <deck.pptx>
1 枚ごとに: 文字数、書体、太字の要素（見出しを除く）、角丸か影の付いた塗りの「箱」、絵文字、小さな画像（アイコン）。
"""
import json, re, sys
from pptx import Presentation
from pptx.util import Emu

EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿]')
name, path = sys.argv[1:3]
prs = Presentation(path)
W, H = prs.slide_width, prs.slide_height

def walk(shapes):
    for s in shapes:
        yield s
        if s.shape_type == 6:  # group
            yield from walk(s.shapes)

out = []
for i, slide in enumerate(prs.slides, 1):
    chars = emoji = emph = boxes = icons = 0
    fonts = set()
    for s in walk(slide.shapes):
        xml = s._element.xml
        if s.has_text_frame if hasattr(s, 'has_text_frame') else False:
            for p in s.text_frame.paragraphs:
                for r in p.runs:
                    t = re.sub(r'\s', '', r.text)
                    if not t: continue
                    chars += len(t); emoji += len(EMOJI.findall(t))
                    f = r.font.name or re.search(r'<a:latin typeface="([^"]+)"', xml) and re.search(r'<a:latin typeface="([^"]+)"', xml).group(1)
                    ea = re.search(r'<a:ea typeface="([^"]+)"', r._r.xml)
                    if ea: fonts.add(ea.group(1))
                    elif f: fonts.add(f)
                    size = r.font.size.pt if r.font.size else 18
                    if r.font.bold and size < 28: emph += 1
        if s.has_table if hasattr(s, 'has_table') else False:
            for row in s.table.rows:
                for c in row.cells:
                    chars += len(re.sub(r'\s', '', c.text))
        if s.width and s.height:
            a = (s.width * s.height) / (W * H)
            rounded = 'prst="roundRect"' in xml or 'outerShdw' in xml
            filled = '<a:solidFill>' in xml.split('<p:txBody>')[0]
            if 0.01 < a < 0.5 and rounded and filled: boxes += 1
            if s.shape_type == 13 and s.width < W * 0.08: icons += 1
    out.append(dict(n=i, chars=chars, emoji=emoji, emph=emph, boxes=boxes, icons=icons, fonts=sorted(fonts)))

med = sorted(x['chars'] for x in out)[len(out) // 2]
fonts = sorted({f for x in out for f in x['fonts'] if not re.search('mono|Courier|Consolas|Menlo', f, re.I)})
print(json.dumps(dict(name=name, slides=len(out), chars_median=med, chars_max=max(x['chars'] for x in out),
  over150=sum(x['chars'] > 150 for x in out), fonts=fonts, emoji=sum(x['emoji'] for x in out),
  emph=sum(x['emph'] for x in out), boxes=sum(x['boxes'] for x in out),
  slides_with_boxes=sum(x['boxes'] > 0 for x in out), icons=sum(x['icons'] for x in out), per_slide=out), ensure_ascii=False))
