#!/usr/bin/env python3

import gi
gi.require_version('Rsvg', '2.0')
from gi.repository import Rsvg
gi.require_version('Pango', '1.0')
from gi.repository import Pango
gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo
import cairo
import math
import re
import collections

POINTS_PER_MM = 2.8346457

PAGE_WIDTH = 297
PAGE_HEIGHT = PAGE_WIDTH * 768 // 1366

SVG_PX_PER_MM = 1.0 / 3.542087542087542

background = Rsvg.Handle.new_from_file('background.svg')

class RenderObject:
    pass

class LayoutRenderObject(RenderObject):
    def __init__(self, layout):
        self.layout = layout

    def get_height(self):
        return self.layout.get_pixel_extents()[1].height / POINTS_PER_MM

    def get_width(self):
        return self.layout.get_pixel_extents()[1].width / POINTS_PER_MM

    def render(self, cr, x_pos, y_pos):
        cr.save()
        cr.move_to(x_pos, y_pos)
        # Remove the mm scale
        cr.scale(1.0 / POINTS_PER_MM, 1.0 / POINTS_PER_MM)
        PangoCairo.show_layout(cr, self.layout)
        cr.restore()

class ImageRenderObject(RenderObject):
    def __init__(self, filename):
        self.image = Rsvg.Handle.new_from_file(filename)
        self.dim = self.image.get_dimensions()

    def get_width(self):
        return self.dim.width * SVG_PX_PER_MM

    def get_height(self):
        return self.dim.height * SVG_PX_PER_MM

    def render(self, cr, x_pos, y_pos):
        cr.save()
        # Scale to mm
        cr.scale(1.0 * SVG_PX_PER_MM, 1.0 * SVG_PX_PER_MM)
        p = cr.get_current_point()
        cr.translate(x_pos / SVG_PX_PER_MM, y_pos / SVG_PX_PER_MM)
        self.image.render_cairo(cr)
        cr.restore()

def replace_include(md):
    with open(md.group(1)) as f:
        return f.read()

def buf_to_text(buf):
    return re.sub(r'^#include\s+([^\s]+)\s*$',
                  replace_include,
                  "".join(buf).strip(),
                  flags=re.MULTILINE)

def get_slides(f):
    buf = []
    sep = re.compile(r'^---\s*$')
    for line in f:
        if sep.match(line):
            yield buf_to_text(buf)
            buf.clear()
        else:
            buf.append(line)
    yield buf_to_text(buf)

def line_to_render_object(line, in_code):
    md = re.match(r'^SVG: +([^\s]+)\s*$', line)
    if md:
        return ImageRenderObject(md.group(1))

    if in_code:
        font = "Mono"
        font_size = 10
    else:
        font = "Sans"
        font_size = 16

    layout = PangoCairo.create_layout(cr)

    if not in_code:
        md = re.match(r'(#+) +(.*)', line)
        if md:
            font_size *= 1.1 * len(md.group(1))
            line = md.group(2)
        else:
            md = re.match(r'((?:  )*)\* +(.*)', line)
            if md:
                spaces = len(md.group(1)) // 2
                line = "\u2022\t" + md.group(2)
                tab_stop = 10 * POINTS_PER_MM * Pango.SCALE
                if spaces > 0:
                    n_tabs = 2
                else:
                    n_tabs = 1
                tab_array = Pango.TabArray(n_tabs, False)
                if spaces > 0:
                    line = "\t" + line
                    tab_array.set_tab(0, Pango.TabAlign.LEFT, tab_stop * spaces)
                tab_array.set_tab(n_tabs - 1,
                                  Pango.TabAlign.LEFT,
                                  tab_stop * (spaces + 1))
                layout.set_tabs(tab_array)
                layout.set_indent(-tab_stop * (spaces + 1))

    fd = Pango.FontDescription.from_string("{} {}".format(font, font_size))
    layout.set_font_description(fd)
    layout.set_width(PAGE_WIDTH * 0.7 * POINTS_PER_MM * Pango.SCALE)
    layout.set_text(line, -1)

    return LayoutRenderObject(layout)

def render_slide(cr, text):
    cr.save()
    # Scale to mm
    cr.scale(1.0 * SVG_PX_PER_MM, 1.0 * SVG_PX_PER_MM)
    background.render_cairo(cr)
    cr.restore()

    objects = []
    in_code = False

    for line in text.split('\n'):
        if re.match(r'^```\s*$', line):
            in_code = not in_code
        else:
            objects.append(line_to_render_object(line, in_code))

    total_height = sum(obj.get_height() for obj in objects)
    max_width = max(obj.get_width() for obj in objects)

    x_pos = PAGE_WIDTH / 2.0 - max_width / 2.0
    y_pos = PAGE_HEIGHT / 2.0 - total_height / 2.0

    for obj in objects:
        cr.move_to(x_pos, y_pos)
        obj.render(cr, x_pos, y_pos)
        y_pos += obj.get_height()

surface = cairo.PDFSurface("mediump-slides.pdf",
                           PAGE_WIDTH * POINTS_PER_MM,
                           PAGE_HEIGHT * POINTS_PER_MM)

cr = cairo.Context(surface)

# Use mm for the units from now on
cr.scale(POINTS_PER_MM, POINTS_PER_MM)

# Use ½mm line width
cr.set_line_width(0.5)

with open('slides.txt', 'rt', encoding='UTF-8') as f:
    for slide_num, slide in enumerate(get_slides(f)):
        if slide_num > 0:
            cr.show_page()
        render_slide(cr, slide)
