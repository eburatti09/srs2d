# -*- coding: utf-8 -*-
#
# This file is part of srs2d.
#
# srs2d is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# trooper-simulator is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with srs2d. If not, see <http://www.gnu.org/licenses/>.

"""
Provides a viewer for the physics module.
"""

__author__ = "Eduardo L. Buratti <eburatti09@gmail.com>"
__date__ = "21 Jun 2013"

import os
import sys
import time
import logging
import threading
import pygame
import Box2D

import dropdown
from .. import physics

__log__ = logging.getLogger(__name__)

class Scene(object):
    background = (0, 0, 0)
    resolution = (1024, 768)

    _flipX = False
    _flipY = False

    do_exit = False
    exit_callback = None

    simulator = None
    running = False
    do_step = False

    target_fps = 30.0

    def __init__(self):
        pygame.init()

        try:
            self.font = pygame.font.Font(None, 15)
        except IOError:
            try:
                self.font = pygame.font.Font('freesansbold.ttf', 15)
            except IOError:
                log.warn("Unable to load default font or 'freesansbold.ttf', disabling text.")
                self.write = lambda *args: 0

        pygame.display.set_caption('SRS2d Viewer')

        self.screen = pygame.display.set_mode(self.resolution)
        self.surface = pygame.Surface(self.resolution, pygame.SRCALPHA)
        self.clock = pygame.time.Clock()
        self.dropdown = dropdown.DropDown(self.font)

        self.zoom = 180
        self.center = Box2D.b2Vec2(0, 0)
        self.offset = (-self.resolution[0]/2, -self.resolution[1]/2)

        self.simulator = physics.Simulator()

    def run(self):
        while not self.do_exit:
            self.draw()

        pygame.quit()

        if self.exit_callback is not None:
            self.exit_callback()

    def exit(self):
        self.do_exit = True

    def start(self):
        self.running = True
        print 'start'

    def stop(self):
        self.running = False

    def step(self):
        self.do_step = True

    def is_running(self):
        return self.running

    def draw(self):
        if self.running or self.do_step:
            self.simulator.time_step = 1.0 / self.target_fps
            self.simulator.step()
            self.do_step = False

        (step_count, real_clock, shapes) = self.simulator.get_state()

        self.screen.fill(self.background)
        self.surface.fill(self.background)
        self.__write_pos = 30
        self.check_events()

        self.draw_circle(self._to_screen(Box2D.b2Vec2(0,0)), 0.02 * self.zoom, fill=(255,255,255))

        self.dropdown.draw(self.surface)

        self.write(str(self.clock.get_fps()), (200,80,80))
        self.write("%02d:%02d:%02d" % (int(real_clock) / 3600,
                                      (int(real_clock) % 3600) / 60,
                                       int(real_clock) % 60), (80,80,200))

        self.screen.blit(self.surface, (0, 0))
        self.clock.tick(self.target_fps)
        pygame.display.flip()

    def check_events(self):
        keys = pygame.key.get_pressed()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.do_exit = True

            elif event.type == pygame.KEYDOWN:
                if (event.key == pygame.K_q) or (event.key == pygame.K_ESCAPE):
                    self.do_exit = True

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.dropdown.mouse_down(event)

            elif event.type == pygame.MOUSEBUTTONUP:
                self.dropdown.mouse_up(event)

    def _to_screen(self, point):
        """Transform a world point to screen point."""

        x = ((point.x + self.center.x) * self.zoom) - self.offset[0]
        y = ((point.y + self.center.y) * self.zoom) - self.offset[1]

        if self._flipX:
            x = self.resolution[0] - x

        if self._flipY:
            y = self.resolution[1] - y

        return (int(x), int(y))

    def _to_world(self, point):
        """Transform a screen point to world point."""

        (x, y) = point

        if self._flipX:
            x = self.resolution[0] - x

        if self._flipY:
            y = self.resolution[1] - y

        x = (float(x + self.offset[0]) / self.zoom) - self.center.x
        y = (float(y + self.offset[1]) / self.zoom) - self.center.y

        return Box2D.b2Vec2(x, y)

    def write(self, text, color):
        self.surface.blit(self.font.render(text, True, color), (5, self.__write_pos))
        self.__write_pos += 15

    def draw_shape(self, shape):
        if not 'type' in shape:
            __log__.warn('Shape without type: %s', str(shape))
            return

        if (not 'color' in shape) or (shape['color'] is None):
            color = (146, 229, 146)
        else:
            color = shape['color']

        fill = (color[0], color[1], color[2], 127)
        border = (color[0], color[1], color[2], 255)

        if (shape['type'] == 'point'):
            if not 'center' in shape:
                __log__.warn('Point without center: %s', str(shape))
                return

            center = self._to_screen(b2Vec2(shape['center']))
            radius = 0.01 * self.zoom
            self.draw_circle(center, radius, fill=shape['color'])

        elif (shape['type'] == 'segment'):
            if (not 'p1' in shape) or (not 'p2' in shape):
                __log__.warn('Segment without points (p1 or p2): %s', str(shape))
                return

            p1 = b2Vec2(shape['p1'])
            p2 = b2Vec2(shape['p2'])
            self.draw_segment(self._to_screen(p1), self._to_screen(p2), fill=fill)

        elif (shape['type'] == 'polygon'):
            if not 'vertices' in shape:
                __log__.warn('Polygon without vertices: %s', str(shape))
                return

            vertices = [ self._to_screen(b2Vec2(v)) for v in shape['vertices'] ]
            self.draw_polygon(vertices, fill=fill, border=border)

        elif (shape['type'] == 'circle'):
            if (not 'center' in shape) or (not 'radius' in shape):
                __log__.warn('Polygon without center or radius: %s', str(shape))
                return

            center = self._to_screen(b2Vec2(shape['center']))
            radius = shape['radius'] * self.zoom

            if 'orientation' in shape:
                orientation = b2Vec2(shape['orientation'])
            else:
                orientation = None

            self.draw_circle(center, radius, orientation=orientation, fill=fill, border=border)

        else:
            __log__.warn('Unknown shape type: %s', str(shape))

    def draw_segment(self, p1, p2, fill=None):
        if not fill:
            return

        pygame.draw.line(self.surface, fill, p1, p2)

    def draw_polygon(self, vertices, fill=None, border=None):
        if not vertices:
            return

        if not fill and not border:
            return

        if len(vertices) == 2:
            if border:
                pygame.draw.line(self.surface, border, vertices[0], vertices[1])
            else:
                pygame.draw.line(self.surface, fill, vertices[0], vertices[1])
        else:
            if fill:
                pygame.draw.polygon(self.surface, fill, vertices, 0)
            if border:
                pygame.draw.polygon(self.surface, border, vertices, 1)

    def draw_circle(self, center, radius, orientation=None, fill=None, border=None):
        if radius < 1: radius = 1
        else: radius = int(radius)

        if not fill and not border:
            return

        if fill:
            pygame.draw.circle(self.surface, fill, center, radius, 0)

        if border:
            pygame.draw.circle(self.surface, border, center, radius, 1)

            if orientation:
                pygame.draw.line(self.surface, border, center,
                        (center[0] + radius*orientation[0], center[1] - radius*orientation[1]))

    def draw_segment_shape(self, shape, transform, fill=None):
        v1 = self._to_screen(Box2D.b2Mul(transform, shape.vertex1))
        v2 = self._to_screen(Box2D.b2Mul(transform, shape.vertex2))

        self.draw_segment(v1, v2, fill=fill)

    def draw_polygon_shape(self, shape, transform, fill=None, border=None):
        vertices = [ self._to_screen(Box2D.b2Mul(transform, v)) for v in shape.vertices ]

        self.draw_polygon(vertices, fill=fill, border=border)

    def draw_circle_shape(self, shape, transform, fill=None, border=None):
        center = self._to_screen(Box2D.b2Mul(transform, shape.pos))
        radius = shape.radius * self.zoom
        orientation = transform.R.col2

        self.draw_circle(center, radius, orientation=orientation, fill=fill, border=border)