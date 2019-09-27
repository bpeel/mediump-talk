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
import xml.etree.ElementTree as ET

POINTS_PER_MM = 2.8346457

PAGE_WIDTH = 297
PAGE_HEIGHT = PAGE_WIDTH * 768 // 1366

SVG_PX_PER_MM = 1.0 / 3.542087542087542

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

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
    def __init__(self, filename, max_layer = None, exact = False):
        self.image = Rsvg.Handle.new_from_file(filename)
        self.dim = self.image.get_dimensions()

        if max_layer is None:
            self.layers = None
        else:
            self.layers = [id for label, id in svg_layers(filename)
                           if not layer_filtered(label, max_layer, exact)]

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

        if self.layers is None:
            self.image.render_cairo(cr)
        else:
            for layer in self.layers:
                self.image.render_cairo_sub(cr, layer)

        cr.restore()

def svg_layers(filename):
    root = ET.parse(filename).getroot()

    for g in root.iter('{{{}}}g'.format(SVG_NS)):
        try:
            label = g.attrib['{{{}}}label'.format(INKSCAPE_NS)]
            id = g.attrib['id']
        except KeyError as e:
            continue

        yield label, "#{}".format(id)

def layer_filtered(layer, max_layer, exact):
    md = re.match(r'\s*Calque\s+([0-9]+)\s*$', layer)

    if md is None:
        return False

    layer_num = int(md.group(1))

    if exact:
        return max_layer != layer_num
    else:
        return max_layer < layer_num

def replace_include(md):
    with open(md.group(1)) as f:
        return f.read()

def buf_to_text(buf):
    buf = re.sub(r'^#include\s+([^\s]+)\s*$',
                 replace_include,
                 "".join(buf).strip(),
                 flags=re.MULTILINE)

    md = re.search(r'^SVG: +([^\s#*=]+)\*(=?)\s*$',
                   buf,
                   flags=re.MULTILINE)

    if md is None:
        yield buf
    else:
        layers = []
        for label, id in svg_layers(md.group(1)):
            lmd = re.match(r'^Calque ([0-9]+)$', label)
            if lmd:
                yield buf[0:md.end(1)] + "#" + lmd.group(1) + md.group(2)

def get_slides(f):
    buf = []
    sep = re.compile(r'^---\s*$')
    for line in f:
        if sep.match(line):
            for s in buf_to_text(buf):
                yield s
            buf.clear()
        else:
            buf.append(line)
    for s in buf_to_text(buf):
        yield s

class SlideRenderer:
    def __init__(self):
        self.surface = cairo.PDFSurface("mediump-slides.pdf",
                                        PAGE_WIDTH * POINTS_PER_MM,
                                        PAGE_HEIGHT * POINTS_PER_MM)

        self.cr = cairo.Context(self.surface)

        # Use mm for the units from now on
        self.cr.scale(POINTS_PER_MM, POINTS_PER_MM)

        # Use ½mm line width
        self.cr.set_line_width(0.5)

        self.slide_num = 0
        self.sections = []

        self.background = Rsvg.Handle.new_from_file('background.svg')

    def add_index_item(self, header_level, line):
        if len(self.sections) > header_level:
            del self.sections[header_level:]
        elif len(self.sections) < header_level:
            self.sections.extend([None] * header_level)

        parent = next((x for x in reversed(self.sections) if x is not None),
                      cairo.PDF_OUTLINE_ROOT)

        id = self.surface.add_outline(parent,
                                      line,
                                      "page={}".format(self.slide_num + 1),
                                      0)
        self.sections.append(id)

    def line_to_render_object(self, line, in_code):
        md = re.match(r'^SVG: +([^\s#*=]+)(?:#([0-9]+)(=)?)?\s*$', line)
        if md:
            max_layer = md.group(2)
            if max_layer is not None:
                max_layer = int(max_layer)
            exact = bool(md.group(3))
            return ImageRenderObject(md.group(1), max_layer, exact)

        if in_code:
            font = "Mono"
            font_size = 10
        else:
            font = "Sans"
            font_size = 16

        layout = PangoCairo.create_layout(self.cr)

        if not in_code:
            md = re.match(r'(#+) +(.*)', line)
            if md:
                header_level = len(md.group(1))
                font_size *= 1.2 ** (6 - header_level)
                line = md.group(2)
                self.add_index_item(header_level, line)
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
                        tab_array.set_tab(0,
                                          Pango.TabAlign.LEFT,
                                          tab_stop * spaces)
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

    def render_slide(self, text):
        if self.slide_num > 0:
            self.cr.show_page()

        self.cr.save()
        # Scale to mm
        self.cr.scale(1.0 * SVG_PX_PER_MM, 1.0 * SVG_PX_PER_MM)
        self.background.render_cairo(self.cr)
        self.cr.restore()

        objects = []
        in_code = False

        for line in text.split('\n'):
            if re.match(r'^```\s*$', line):
                in_code = not in_code
            else:
                objects.append(self.line_to_render_object(line, in_code))

        total_height = sum(obj.get_height() for obj in objects)
        max_width = max(obj.get_width() for obj in objects)

        x_pos = PAGE_WIDTH / 2.0 - max_width / 2.0
        y_pos = PAGE_HEIGHT / 2.0 - total_height / 2.0

        for obj in objects:
            self.cr.move_to(x_pos, y_pos)
            obj.render(self.cr, x_pos, y_pos)
            y_pos += obj.get_height()

        self.slide_num += 1

with open('slides.txt', 'rt', encoding='UTF-8') as f:
    renderer = SlideRenderer()

    for slide in get_slides(f):
        renderer.render_slide(slide)
