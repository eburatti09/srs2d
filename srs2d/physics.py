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
__date__ = "13 Jul 2013"

import os
import logging
import random
import numpy as np
import pyopencl as cl

__log__ = logging.getLogger(__name__)

NUM_SENSORS = 13
NUM_ACTUATORS = 4
NUM_HIDDEN = 3

class World(object):
    """
    Creates a 2D top-down physics World.

    Usage:

        sim = World()

        while 1:
            sim.step()
            (step_count, clock, shapes) = sim.get_state()
            # draw_the_screen(shapes)
    """


    def __init__(self, context, queue, num_worlds=1, num_robots=9, time_step=1/30.0, dynamics_iterations=4):
        global NUM_INPUTS, NUM_OUTPUTS

        self.step_count = 0.0
        self.clock = 0.0

        self.context = context
        self.queue = queue

        self.num_worlds = num_worlds
        self.num_robots = num_robots
        self.time_step = time_step
        self.dynamics_iterations = dynamics_iterations

        options = '-DROBOTS_PER_WORLD=%d -DTIME_STEP=%f -DDYNAMICS_ITERATIONS=%d' % (num_robots, time_step, dynamics_iterations)

        src = open(os.path.join(os.path.dirname(__file__), 'kernels/physics.cl'), 'r')
        self.prg = cl.Program(context, src.read()).build(options=options)

        # query the structs sizes
        sizeof = np.zeros(1, dtype=np.int32)
        sizeof_buf = cl.Buffer(context, 0, 4)

        self.prg.size_of_world_t(queue, (1,), None, sizeof_buf).wait()
        cl.enqueue_copy(queue, sizeof, sizeof_buf)
        sizeof_world_t = int(sizeof[0])

        # create buffers
        self.worlds = cl.Buffer(context, 0, num_worlds * sizeof_world_t)

        # initialize random number generator
        self.ranluxcl = cl.Buffer(context, 0, num_worlds * num_robots * 112)
        kernel = self.prg.init_ranluxcl
        kernel.set_scalar_arg_dtypes((np.uint32, None))
        kernel(queue, (num_worlds,num_robots), None, random.randint(0, 4294967295), self.ranluxcl).wait()

        # initialize neural network
        self.weights = np.random.rand(num_worlds*NUM_ACTUATORS*(NUM_SENSORS+NUM_HIDDEN)).astype(np.float32) * 10 - 5
        self.weights_buf = cl.Buffer(context, cl.mem_flags.COPY_HOST_PTR, hostbuf=self.weights)
        self.bias = np.random.rand(num_worlds*NUM_ACTUATORS).astype(np.float32) * 10 - 5
        self.bias_buf = cl.Buffer(context, cl.mem_flags.COPY_HOST_PTR, hostbuf=self.bias)

        self.weights_hidden = np.random.rand(num_worlds*NUM_HIDDEN*NUM_SENSORS).astype(np.float32) * 10 - 5
        self.weights_hidden_buf = cl.Buffer(context, cl.mem_flags.COPY_HOST_PTR, hostbuf=self.weights_hidden)

        self.bias_hidden = np.random.rand(num_worlds*NUM_HIDDEN).astype(np.float32) * 10 - 5
        self.bias_hidden_buf = cl.Buffer(context, cl.mem_flags.COPY_HOST_PTR, hostbuf=self.bias_hidden)

        self.timec_hidden = np.random.rand(num_worlds*NUM_HIDDEN).astype(np.float32)
        self.timec_hidden_buf = cl.Buffer(context, cl.mem_flags.COPY_HOST_PTR, hostbuf=self.timec_hidden)

        self.prg.set_ann_parameters(queue, (num_worlds,), None,
            self.ranluxcl, self.worlds, self.weights_buf, self.bias_buf,
            self.weights_hidden_buf, self.bias_hidden_buf, self.timec_hidden_buf).wait()

    def init_worlds(self, target_areas_distance):
        init_worlds = self.prg.init_worlds
        init_worlds.set_scalar_arg_dtypes((None, None, np.float32))
        init_worlds(self.queue, (self.num_worlds,), None, self.ranluxcl, self.worlds, target_areas_distance).wait()
        self.prg.init_robots(self.queue, (self.num_worlds, self.num_robots), None, self.ranluxcl, self.worlds).wait()

    def step(self):
        self.prg.step_robots(self.queue, (self.num_worlds,self.num_robots), None, self.ranluxcl, self.worlds).wait()

        self.step_count += 1
        self.clock += self.time_step

    def simulate(self, seconds):
        kernel = self.prg.simulate
        kernel.set_scalar_arg_dtypes((None, None, np.float32))
        kernel(self.queue, (self.num_worlds,self.num_robots), None, self.ranluxcl, self.worlds, seconds).wait()

    def get_transforms(self):
        transforms = np.zeros(self.num_worlds * self.num_robots, dtype=np.dtype((np.float32, (4,))))
        trans_buf = cl.Buffer(self.context, cl.mem_flags.COPY_HOST_PTR, hostbuf=transforms)
        self.prg.get_transform_matrices(self.queue, (self.num_worlds, self.num_robots), None, self.worlds, trans_buf).wait()
        cl.enqueue_copy(self.queue, transforms, trans_buf)
        return transforms

    def set_ann_parameters(self, world, weights, bias, weights_hidden, bias_hidden, timec_hidden):
        self.weights[world*NUM_ACTUATORS*(NUM_SENSORS+NUM_HIDDEN):(world+1)*NUM_ACTUATORS*(NUM_SENSORS+NUM_HIDDEN)] = weights
        self.bias[world*NUM_ACTUATORS:(world+1)*NUM_ACTUATORS] = bias
        self.weights_hidden[world*NUM_HIDDEN*NUM_SENSORS:(world+1)*NUM_HIDDEN*NUM_SENSORS] = weights_hidden
        self.bias_hidden[world*NUM_HIDDEN:(world+1)*NUM_HIDDEN] = bias_hidden
        self.timec_hidden[world*NUM_HIDDEN:(world+1)*NUM_HIDDEN] = timec_hidden

    def commit_ann_parameters(self):
        cl.enqueue_copy(self.queue, self.weights_buf, self.weights)
        cl.enqueue_copy(self.queue, self.bias_buf, self.bias)
        cl.enqueue_copy(self.queue, self.weights_hidden_buf, self.weights_hidden)
        cl.enqueue_copy(self.queue, self.bias_hidden_buf, self.bias_hidden)
        cl.enqueue_copy(self.queue, self.timec_hidden_buf, self.timec_hidden)

        self.prg.set_ann_parameters(self.queue, (self.num_worlds,), None,
            self.ranluxcl, self.worlds, self.weights_buf, self.bias_buf,
            self.weights_hidden_buf, self.bias_hidden_buf, self.timec_hidden_buf).wait()

    def get_fitness(self):
        fitness = np.zeros(self.num_worlds, dtype=np.float32)
        fitness_buf = cl.Buffer(self.context, cl.mem_flags.COPY_HOST_PTR, hostbuf=fitness)
        self.prg.get_fitness(self.queue, (self.num_worlds,), None, self.worlds, fitness_buf).wait()
        cl.enqueue_copy(self.queue, fitness, fitness_buf)
        return fitness