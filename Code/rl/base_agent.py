import collections
from collections import OrderedDict
from rl.normalizer import Normalizer
import numpy as np

class BaseAgent():
    def __init__(self, config, ob_space): # ob_space is an ordered dict where keys are ob names and values are dimensions
        self._config = config
        self._ob_norm = Normalizer(ob_space, default_clip_range=config.clip_range, clip_obs=config.clip_obs)

    def normalize(self, ob):
        if self._config.ob_norm:
            return self._ob_norm.normalize(ob)
        return ob

    def act(self, ob, is_train=True):
        """ Returns action and the actor's activation given an observation @ob. """
        ob = self.normalize(ob)
        if hasattr(self, '_actor'):
            ac, activation = self._actor.act(ob, is_train=is_train)

        else:
            ac, activation = self._actors[0][0].act(ob, is_train=is_train)
           

        return ac, activation
    
    
    def update_normalizer(self, obs):
        if self._config.ob_norm:
            self._ob_norm.update(obs)
            self._ob_norm.recompute_stats()

    def store_episode(self, rollouts):
        raise NotImplementedError()

    def replay_buffer(self):
        return self._buffer.state_dict() # gives episodes buffer; buffer is like a rollout but can store more values for multiple episodes

    def load_replay_buffer(self, state_dict):
        self._buffer.load_state_dict(state_dict)

    def sync_networks(self):
        raise NotImplementedError()

    def train(self):
        raise NotImplementedError()

    def _soft_update_target_network(self, target, source, tau):
        for target_param, source_param in zip(target.parameters(), source.parameters()):
            target_param.data.copy_((1 - tau) * source_param.data + tau * target_param.data)

    def _copy_target_network(self, target, source):
        for target_param, source_param in zip(target.parameters(), source.parameters()):
            target_param.data.copy_(source_param.data)
