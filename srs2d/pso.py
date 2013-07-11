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

__author__ = "Eduardo L. Buratti <eburatti09@gmail.com>"
__date__ = "04 Jul 2013"

import sys
import math
import random
import logging
import physics
import robot
import copy
import multiprocessing

__log__ = logging.getLogger(__name__)

INPUT_NEURONS = [
    'camera0',
    'camera1',
    'camera2',
    'camera3',
    'proximity3',
    'proximity2',
    'proximity1',
    'proximity0',
    'proximity7',
    'proximity6',
    'proximity5',
    'proximity4',
    'ground0'
]

HIDDEN_NEURONS = [
    'hidden0',
    'hidden1',
    'hidden2'
]

OUTPUT_NEURONS = [
    'wheels1',
    'wheels0',
    'rear_led0',
    'front_led0'
]

W = 0.9
ALFA = 2
BETA = 2

SIMULATION_DURATION = 600
NUM_ROBOTS = 30
D = [1.2, 1.5, 1.9, 2.3, 2.7]


class Simulation(object):
    def __init__(self, targets_distance=1.2):
        global NUM_ROBOTS

        self.world = physics.World()

        self.targets_distance = targets_distance

        H = 4.20
        W = random.uniform(4.20, 4.90)

        x = math.sqrt(((targets_distance / 2.0) ** 2) / 2.0)
        self.world.add(robot.ColorPadActuator(center=physics.Vector(-x, x), radius=0.27))
        self.world.add(robot.ColorPadActuator(center=physics.Vector(x, -x), radius=0.27))
        self.full_charge = targets_distance - 2 * 0.27

        VERTICAL_WALL_VERTICES = [ physics.Vector(-0.01, H/2.0),
                                   physics.Vector(0.01, H/2.0),
                                   physics.Vector(0.01, -H/2.0),
                                   physics.Vector(-0.01, -H/2.0) ]

        HORIZONTAL_WALL_VERTICES = [ physics.Vector(-W/2.0-0.01, 0.01),
                                     physics.Vector(W/2.0+0.01, 0.01),
                                     physics.Vector(W/2.0+0.01, -0.01),
                                     physics.Vector(-W/2.0-0.01, -0.01) ]

        wall = physics.StaticBody(position=physics.Vector(-W/2.0, 0))
        wall.add_shape(physics.PolygonShape(vertices=VERTICAL_WALL_VERTICES))
        self.world.add(wall)

        wall = physics.StaticBody(position=physics.Vector(0.0, -H/2.0))
        wall.add_shape(physics.PolygonShape(vertices=HORIZONTAL_WALL_VERTICES))
        self.world.add(wall)

        wall = physics.StaticBody(position=physics.Vector(W/2.0, 0))
        wall.add_shape(physics.PolygonShape(vertices=VERTICAL_WALL_VERTICES))
        self.world.add(wall)

        wall = physics.StaticBody(position=physics.Vector(0.0, H/2.0))
        wall.add_shape(physics.PolygonShape(vertices=HORIZONTAL_WALL_VERTICES))
        self.world.add(wall)

        self.robots = [robot.Robot(position=physics.Vector( random.uniform(-W/2.0+0.12,W/2.0-0.12), random.uniform(-H/2.0+0.12, H/2.0-0.12) )) for i in range(NUM_ROBOTS)]
        for rob in self.robots:
            rob.entered_new_target_area = False
            rob.last_color_pad = None
            rob.energy = 1.0 + self.full_charge
            rob.fitness = 0.0
            self.world.add(rob)

        self.world.connect('color-pad-notify', self.on_color_pad_notify)
        self.world.connect('prepare', self.on_prepare)
        self.world.connect('think', self.on_think)

    def run(self, seconds):
        start = cur = self.world.clock
        while (cur - start) < seconds:
            self.world.step()
            cur = self.world.clock

    def on_color_pad_notify(self, pad):
        global SIMULATION_DURATION

        if self.world.clock < (SIMULATION_DURATION / 2):
            return

        for rob in self.robots:
            x = rob.world_center.x
            y = rob.world_center.y

            if ((pad.center.x - x) ** 2 + (pad.center.y - y) ** 2) < (pad.radius ** 2):
                if rob.last_color_pad != pad:
                    rob.entered_new_target_area = True
                    rob.last_color_pad = pad

    def on_prepare(self):
        global SIMULATION_DURATION

        if self.world.clock < (SIMULATION_DURATION / 2):
            return

        for rob in self.robots:
            rob.entered_new_target_area = False

    def on_think(self):
        global SIMULATION_DURATION

        if self.world.clock < (SIMULATION_DURATION / 2):
            return

        for rob in self.robots:
            if rob.entered_new_target_area:
                rob.fitness += rob.energy
                rob.energy = 1 + self.full_charge
            else:
                rob.energy -= (abs(rob.wheels.values[0]) + abs(rob.wheels.values[0])) / (2.0 * 82)

class Worker(multiprocessing.Process):
    def __init__(self, socket):
        super(Worker, self).__init__()
        self.socket = socket
        self.start()

    def run(self):
        global SIMULATION_DURATION, D, NUM_ROBOTS

        while True:
            position = self.socket.recv()

            fit = 0.0

            for d in D:
                for i in range(3):
                    sim = Simulation(d)

                    for rob in sim.robots:
                        rob.controller.load(position)

                    sim.run(SIMULATION_DURATION)

                    for rob in sim.robots:
                        # A robot takes 2.733333 seconds to move one meter at full speed, so
                        # ((SIMULATION_DURATION / 2.733333) / d) = maximum number of trips a
                        # robot can do in SIMULATION_DURATION seconds.
                        # print rob.fitness
                        fit += rob.fitness / ((SIMULATION_DURATION / 2.733333) / d)

            self.socket.send(fit / (len(D) * 3 * NUM_ROBOTS))

class PSO(object):
    def __init__(self):
        self.gbest = None
        self.gbest_fitness = None
        self.particles = []

    def run(self, population_size=16, num_workers=8):
        print 'PSO Starting...'
        print '==============='

        self.particles = [ Particle() for i in range(population_size) ]
        for p in self.particles:
            socketA, socketB = multiprocessing.Pipe()
            p.socket = socketA
            w = Worker(socketB)

        while True:
            print 'Calculating fitness for each particle...'
            for p in self.particles:
                p.socket.send(p.position.export())
            for p in self.particles:
                p.fitness = p.socket.recv()

            print 'Updating pbest for each particle...'
            for p in self.particles:
                p.update_pbest()

            print 'Updating gbest...'
            for p in self.particles:
                if (self.gbest is None) or (p.pbest.fitness > self.gbest.fitness):
                    self.gbest = p.pbest.copy()

                    print 'Found new gbest: ', str(self.gbest)

            print '-' * 80
            print 'CURRENT GBEST IS: ', str(self.gbest)
            print str(self.gbest.position)
            print '-' * 80

            print 'Calculating new position and velocity for each particle...'
            for p in self.particles:
                p.gbest = self.gbest
                p.update_pos_vel()

class Particle(object):
    def __init__(self):
        self.id = id(self)

        self.position = PVector(True)
        self.velocity = PVector(True)
        self.fitness = 0.0

        self.pbest = None
        self.gbest = None

    def __str__(self):
        return 'Particle(%d, fitness=%.5f)' % (self.id, self.fitness)

    def copy(self):
        p = Particle()
        p.position = self.position.copy()
        p.velocity = self.velocity.copy()
        p.fitness = self.fitness
        p.pbest = self.pbest
        p.gbest = self.gbest
        return p

    def update_pbest(self):
        if (self.pbest is None) or (self.fitness > self.pbest.fitness):
            self.pbest = self.copy()

            print '[Particle %d] Found new pbest: %s' % (self.id, str(self.pbest))

    def update_pos_vel(self):
        global W, ALFA, BETA

        self.velocity = W * self.velocity + \
                        ALFA * random.uniform(0, 1.0) * (self.pbest.position - self.position) + \
                        BETA * random.uniform(0, 1.0) * (self.gbest.position - self.position)

        self.position = self.position + self.velocity

class PVector(object):
    def __init__(self, randomize=False, weights_boundary=(-5.0, 5.0), bias_boundary=(-5.0, 5.0), timec_boundary=(0, 1.0)):
        global INPUT_NEURONS, HIDDEN_NEURONS, OUTPUT_NEURONS

        self.weights_boundary = weights_boundary
        self.bias_boundary = bias_boundary
        self.timec_boundary = timec_boundary

        if randomize:
            self.weights = { o: { ih: random.uniform(weights_boundary[0], weights_boundary[1]) for ih in INPUT_NEURONS + HIDDEN_NEURONS } for o in OUTPUT_NEURONS }
            self.bias = { o: random.uniform(bias_boundary[0], bias_boundary[1]) for o in OUTPUT_NEURONS }
            self.weights_hidden = { h: { i: random.uniform(weights_boundary[0], weights_boundary[1]) for i in INPUT_NEURONS } for h in HIDDEN_NEURONS }
            self.bias_hidden = { h: random.uniform(bias_boundary[0], bias_boundary[1]) for h in HIDDEN_NEURONS }
            self.timec_hidden = { h: random.uniform(timec_boundary[0], timec_boundary[1]) for h in HIDDEN_NEURONS }

        else:
            self.weights = { o: { ih: 0.0 for ih in INPUT_NEURONS + HIDDEN_NEURONS } for o in OUTPUT_NEURONS }
            self.bias = { o: 0.0 for o in OUTPUT_NEURONS }
            self.weights_hidden = { h: { i: 0.0 for i in INPUT_NEURONS } for h in HIDDEN_NEURONS }
            self.bias_hidden = { h: 0.0 for h in HIDDEN_NEURONS }
            self.timec_hidden = { h: 0.0 for h in HIDDEN_NEURONS }

    def __str__(self):
        return str({
            'weights': self.weights,
            'bias': self.bias,
            'weights_hidden': self.weights_hidden,
            'bias_hidden': self.bias_hidden,
            'timec_hidden': self.timec_hidden
        })

    def copy(self):
        pv = PVector()
        pv.weights_boundary = copy.deepcopy(self.weights_boundary)
        pv.bias_boundary = copy.deepcopy(self.bias_boundary)
        pv.timec_boundary = copy.deepcopy(self.timec_boundary)
        pv.weights = copy.deepcopy(self.weights)
        pv.bias = copy.deepcopy(self.bias)
        pv.weights_hidden = copy.deepcopy(self.weights_hidden)
        pv.bias_hidden = copy.deepcopy(self.bias_hidden)
        pv.timec_hidden = copy.deepcopy(self.timec_hidden)
        return pv

    def __add__(self, other):
        if isinstance(other, PVector):
            ret = PVector()
            ret.weights_boundary = self.weights_boundary
            ret.bias_boundary = self.bias_boundary
            ret.timec_boundary = self.timec_boundary
            ret.weights = { o: { ih: self.check_boundary(self.weights_boundary, self.weights[o][ih]+other.weights[o][ih]) for ih in INPUT_NEURONS + HIDDEN_NEURONS } for o in OUTPUT_NEURONS }
            ret.bias = { o: self.check_boundary(self.bias_boundary, self.bias[o]+other.bias[o]) for o in OUTPUT_NEURONS }
            ret.weights_hidden = { h: { i: self.check_boundary(self.weights_boundary, self.weights_hidden[h][i]+other.weights_hidden[h][i]) for i in INPUT_NEURONS } for h in HIDDEN_NEURONS }
            ret.bias_hidden = { h: self.check_boundary(self.bias_boundary, self.bias_hidden[h]+other.bias_hidden[h]) for h in HIDDEN_NEURONS }
            ret.timec_hidden = { h: self.check_boundary(self.timec_boundary, self.timec_hidden[h]+other.timec_hidden[h]) for h in HIDDEN_NEURONS }
            return ret
        else:
            raise NotImplemented

    def __sub__(self, other):
        if isinstance(other, PVector):
            ret = PVector()
            ret.weights_boundary = self.weights_boundary
            ret.bias_boundary = self.bias_boundary
            ret.timec_boundary = self.timec_boundary
            ret.weights = { o: { ih: self.check_boundary(self.weights_boundary, self.weights[o][ih]-other.weights[o][ih]) for ih in INPUT_NEURONS + HIDDEN_NEURONS } for o in OUTPUT_NEURONS }
            ret.bias = { o: self.check_boundary(self.bias_boundary, self.bias[o]-other.bias[o]) for o in OUTPUT_NEURONS }
            ret.weights_hidden = { h: { i: self.check_boundary(self.weights_boundary, self.weights_hidden[h][i]-other.weights_hidden[h][i]) for i in INPUT_NEURONS } for h in HIDDEN_NEURONS }
            ret.bias_hidden = { h: self.check_boundary(self.bias_boundary, self.bias_hidden[h]-other.bias_hidden[h]) for h in HIDDEN_NEURONS }
            ret.timec_hidden = { h: self.check_boundary(self.timec_boundary, self.timec_hidden[h]-other.timec_hidden[h]) for h in HIDDEN_NEURONS }
            return ret
        else:
            raise NotImplemented

    def __mul__(self, other):
        if isinstance(other, int) or isinstance(other, float) or isinstance(other, long):
            ret = PVector()
            ret.weights_boundary = self.weights_boundary
            ret.bias_boundary = self.bias_boundary
            ret.timec_boundary = self.timec_boundary
            ret.weights = { o: { ih: self.check_boundary(self.weights_boundary, self.weights[o][ih]*other) for ih in INPUT_NEURONS + HIDDEN_NEURONS } for o in OUTPUT_NEURONS }
            ret.bias = { o: self.check_boundary(self.bias_boundary, self.bias[o]*other) for o in OUTPUT_NEURONS }
            ret.weights_hidden = { h: { i: self.check_boundary(self.weights_boundary, self.weights_hidden[h][i]*other) for i in INPUT_NEURONS } for h in HIDDEN_NEURONS }
            ret.bias_hidden = { h: self.check_boundary(self.bias_boundary, self.bias_hidden[h]*other) for h in HIDDEN_NEURONS }
            ret.timec_hidden = { h: self.check_boundary(self.timec_boundary, self.timec_hidden[h]*other) for h in HIDDEN_NEURONS }
            return ret
        else:
            raise NotImplemented

    def __rmul__(self, other):
        if isinstance(other, int) or isinstance(other, float) or isinstance(other, long):
            return self.__mul__(other)
        else:
            raise NotImplemented

    @staticmethod
    def check_boundary(boundary, value):
        if value < boundary[0]:
            return boundary[0]
        elif value > boundary[1]:
            return boundary[1]
        else:
            return value

    def export(self):
        return {
            'weights': self.weights,
            'bias': self.bias,
            'weights_hidden': self.weights_hidden,
            'bias_hidden': self.bias_hidden,
            'timec_hidden': self.timec_hidden
        }

if __name__=="__main__":
    PSO().run()