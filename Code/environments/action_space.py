""" Define ActionSpace class to represent action space. """
import torch
import sys
#using sys.path.append insert the location of your folder in order for the program to run
from collections import OrderedDict
import numpy as np
from utils.logger import logger


class ActionSpace(object):
    """
    Base class for action space
    This action space is used in the provided RL training code.
    """

    def __init__(self, size, minimum=-1., maximum=1.):
        """
        Loads a mujoco xml from file.

        Args:
            size (int): action dimension.
            min: minimum values for action.
            max: maximum values for action.
        """


        #print('\n size=',size)

        #self.size = int(size/2)
        #self.shape = OrderedDict([('default', int(size/2))])
        self.size = size
        self.shape = OrderedDict([('default', size)])
        self.dtype = OrderedDict([('default', np.float)])                    
        self.shape = OrderedDict([("right_arm", 4), ("left_arm", 4)])   #dividing the action space in 2 parts for the 2 agents. it can be divided into multiple parts and we can use multiple agents

        self._minimum = np.array(minimum)
        self._minimum.setflags(write=False)

        self._maximum = np.array(maximum)
        self._maximum.setflags(write=False)

    @property
    def minimum(self):
        """
        Returns the minimum values of the action.
        """
        return self._minimum

    @property
    def maximum(self):
        """
        Returns the maximum values of the action.
        """
        return self._maximum

    def keys(self):
        """
        Returns the keys of the action space.
        """
        return self.shape.keys()

    def __repr__(self):
        template = ('ActionSpace(shape={},''minimum={}, maximum={})')
        return template.format(self.shape, self._minimum, self._maximum)
    
    def is_continuous(self, key):
        return self.dtype[key] == 'continuous'
    
    def __eq__(self, other):
        """
        Returns whether other action space is the same or not.
        """
        if not isinstance(other, ActionSpace):
            return False
        return (self.minimum == other.minimum).all() and (self.maximum == other.maximum).all()

    def sample(self):
        """
        Returns a sample from the action space.
        """
        return np.random.uniform(low=self.minimum, high=self.maximum, size=self.size)
        
    def decompose(self, shape):
        assert isinstance(shape, OrderedDict)
        #assert self.size == sum(shape.values())
        if self.size != sum(shape.values()):
            logger.error("Check the action space (urdf: %d, shape: %d (%s))",
                         self.size, sum(shape.values()), shape)
        self.size = sum(shape.values())
        self.shape = shape
        self.dtype = OrderedDict([(k, "continuous") for k in shape.keys()])

    def add(self, key, dtype, size, minimum, maxmimum):
        self.size += size
        self.shape[key] = size
        self.dtype[key] = dtype
