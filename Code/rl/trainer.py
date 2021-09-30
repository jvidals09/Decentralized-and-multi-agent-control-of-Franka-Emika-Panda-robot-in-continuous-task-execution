""" Base code for RL training. Collects rollouts and updates policy networks. """
import sys
import os
from time import time
from collections import defaultdict, OrderedDict
import gzip
import pickle
#using sys.path.append insert the location of your folder in order for the program to run
import h5py
import torch
import wandb
import numpy as np
#import moviepy.editor as mpy
from tqdm import tqdm, trange

#from rl.policies import get_actor_critic_by_name
from rl.meta_ppo_agent import MetaPPOAgent
from rl.rollouts import RolloutRunner
from utils.logger import logger
from utils.pytorch import get_ckpt_path, count_parameters
from utils.mpi import mpi_sum
from environments import make
from rl.policies import MlpActor, MlpCritic
from environments.action_space import ActionSpace
from rl.sac_agent import SACAgent
from rl.ppo_agent import PPOAgent


def get_subdiv_space(env, subdiv):
    """
    Returns observation and action space splited by agents.
    """
    ob_space = env.observation_space
    print('\n this is in traintr we print observatiron space',ob_space)
    ac_space = env.action_space
    assert isinstance(ob_space, OrderedDict)

    if subdiv:
        clusters = subdiv.split('/')
        clusters = [
            (cluster.split('-')[0].split(','), cluster.split('-')[1].split(',')) for cluster in clusters
        ]
    else:
        clusters = [(ob_space.keys(), ac_space.shape.keys())]

    ob_clusters = [cluster[0] for cluster in clusters]
    ob_keys = [item for sublist in ob_clusters for item in sublist]
    ob_space = OrderedDict([
        (k, ob_space[k]) for k in ob_space.keys() if k in ob_keys])

    ac_clusters = [cluster[1] for cluster in clusters]
    ac_keys = [item for sublist in ac_clusters for item in sublist]
    ac_decomposition = OrderedDict([(k, ac_space.shape[k]) for k in ac_keys])
    ac_size = sum(ac_space.shape[k] for k in ac_keys)
    ac_space = ActionSpace(ac_size, -1, 1)
    ac_space.decompose(ac_decomposition)

    return ob_space, ac_space, clusters


class Trainer(object):
    """
    Trainer class for SAC and PPO in PyTorch.
    """

    def __init__(self, config):
        """
        Initializes class with the configuration.
        """
        self._config = config
        self._is_chef = config.is_chef

        # create a new environment
        self._env = make("PandaGrasp", config)
        ob_space, ac_space, clusters = get_subdiv_space(self._env, config.subdiv)

        # get actor and critic networks
        actor, critic = MlpActor, MlpCritic

        # build up networks
        self._meta_agent = MetaPPOAgent(config, ob_space)
  #      self._meta_agent = SACAgent(config, ob_space, ac_space, actor, critic) #using 2 agents where 1 is SAC
 #       self._meta_agent = PPOAgent(config, ob_space, ac_space, actor, critic) #using 2 agents where 1 is PPO
        if config.meta:
            #from rl.low_level_agent import LowLevelAgent
            self._agent = PPOAgent(
                config, ob_space, ac_space, actor, critic
            )
        else:
            if config.diayn:
                for cluster in clusters:
                    ob_space[','.join(cluster[0]) + '_diayn'] = config.z_dim

            self._agent = SACAgent(
                config, ob_space, ac_space, actor, critic
            )

        # build rollout runner
        self._runner = RolloutRunner(
            config, self._env, self._meta_agent, self._agent
        )

        # setup log
        if self._is_chef and self._config.is_train:
            exclude = ['device']
            if not self._config.wandb:
                os.environ['WANDB_MODE'] = 'dryrun'

            # WANDB user or team name
            entity = "damjan1"
            # WANDB project name
            project = "subdiv"

            wandb.init(
                resume=config.run_name,
                project=project,
                config={k: v for k, v in config.__dict__.items() if k not in exclude},
                dir=config.log_dir,
                entity=entity,
                notes=config.notes
            )

    def _save_ckpt(self, ckpt_num, update_iter):
        """
        Save checkpoint to log directory.

        Args:
            ckpt_num: number appended to checkpoint name. The number of
                environment step is used in this code.
            update_iter: number of policy update. It will be used for resuming training.
        """
        ckpt_path = os.path.join(self._config.log_dir, 'ckpt_%08d.pt' % ckpt_num)
        state_dict = {'step': ckpt_num, 'update_iter': update_iter}
        state_dict['meta_agent'] = self._meta_agent.state_dict()
        state_dict['agent'] = self._agent.state_dict()
        torch.save(state_dict, ckpt_path)
        logger.warn('Save checkpoint: %s', ckpt_path)

        replay_path = os.path.join(self._config.log_dir, 'replay_%08d.pkl' % ckpt_num)
        with gzip.open(replay_path, 'wb') as f:
            if self._config.meta:
                if self._config.meta_update_target == 'HL':
                    replay_buffers = {'replay': self._meta_agent.replay_buffer()}
                elif self._config.meta_update_target == 'LL':
                    replay_buffers = {'replay': self._agent.replay_buffer()}
                else: # both
                    replay_buffers = {'hl_replay': self._meta_agent.replay_buffer(),
                                      'll_replay': self._agent.replay_buffer()}
            else:
                replay_buffers = {'replay': self._agent.replay_buffer()}
            pickle.dump(replay_buffers, f)

    def _load_ckpt(self, ckpt_num=None):
        """
        Loads checkpoint with index number @ckpt_num. If @ckpt_num is None,
        it loads and returns the checkpoint with the largest index number.
        """
        ckpt_path, ckpt_num = get_ckpt_path(self._config.log_dir, ckpt_num)

        if ckpt_path is not None:
            logger.warn('Load checkpoint %s', ckpt_path)
            ckpt = torch.load(ckpt_path)
            self._meta_agent.load_state_dict(ckpt['meta_agent'])
            self._agent.load_state_dict(ckpt['agent'])

            if self._config.is_train:
                replay_path = os.path.join(self._config.log_dir, 'replay_%08d.pkl' % ckpt_num)
                logger.warn('Load replay_buffer %s', replay_path)
                with gzip.open(replay_path, 'rb') as f:
                    replay_buffers = pickle.load(f)
                    if self._config.meta:
                        if self._config.meta_update_target == 'HL':
                            self._meta_agent.load_replay_buffer(replay_buffers['replay'])
                        elif self._config.meta_update_target == 'LL':
                            self._agent.load_replay_buffer(replay_buffers['replay'])
                        else: # both
                            self._meta_agent.load_replay_buffer(replay_buffers['hl_replay'])
                            self._agent.load_replay_buffer(replay_buffers['ll_replay'])
                    else:
                        self._agent.load_replay_buffer(replay_buffers['replay'])

            return ckpt['step'], ckpt['update_iter']
        else:
            logger.warn('Randomly initialize models')
            return 0, 0

    def _log_train(self, step, train_info, ep_info):
        """
        Logs training and episode information to wandb.
        Args:
            step: the number of environment steps.
            train_info: training information to log, such as loss, gradient.
            ep_info: episode information to log, such as reward, episode time.
        """
        for k, v in train_info.items():
            if np.isscalar(v) or (hasattr(v, 'shape') and np.prod(v.shape) == 1):
                wandb.log({'train_rl/%s' % k: v}, step=step)
            else:
                wandb.log({'train_rl/%s' % k: [wandb.Image(v)]}, step=step)

        for k, v in ep_info.items():
            wandb.log({'train_ep/%s' % k: np.mean(v)}, step=step)
            wandb.log({'train_ep_max/%s' % k: np.max(v)}, step=step)

    def _log_test(self, step, ep_info):
        """
        Logs episode information during testing to wandb.
        Args:
            step: the number of environment steps.
            ep_info: episode information to log, such as reward, episode time.
        """
        if self._config.is_train:
            for k, v in ep_info.items():
                wandb.log({'test_ep/%s' % k: np.mean(v)}, step=step)

    def train(self):
        """ Trains an agent. """
        config = self._config
        num_batches = config.num_batches

        # load checkpoint
        step, update_iter = self._load_ckpt()

        # sync the networks across the cpus
        self._agent.sync_networks()

        logger.info("Start training at step=%d", step)
        if self._is_chef:
            pbar = tqdm(initial=step, total=config.max_global_step, desc=config.run_name)
            ep_info = defaultdict(list)

        # decide how many episodes or how long rollout to collect
        run_ep_max = 1
        run_step_max = self._config.rollout_length
        if self._config.meta is not None:
            if (config.meta_update_target == 'LL' or \
                config.meta_update_target == 'both'):
                run_step_max = 600
            else:
                run_ep_max = 3
        elif self._config.algo == 'ppo':
            run_ep_max = 3
            run_step_max = 600
        elif self._config.algo == 'sac':
            run_step_max = 600

        # dummy run for preventing weird error in a cold run
        self._runner.run_episode()

        st_time = time()
        st_step = step
        while step < config.max_global_step:
            run_ep = 0
            run_step = 0
            while run_step < run_step_max and run_ep < run_ep_max:
                rollout, meta_rollout, info, _ = \
                    self._runner.run_episode()
                run_step += info['len']
                run_ep += 1
                self._save_success_qpos(info)
                logger.info('rollout: %s', {k: v for k, v in info.items() if not 'qpos' in k})
                if config.meta:
                    if (config.meta_update_target == 'HL' or \
                        config.meta_update_target == 'both'):
                        self._meta_agent.store_episode(meta_rollout)
                        print('\n the storing of episode self._meta_agent.store_episode',self._meta_agent.store_episode(meta_rollout))
                    if (config.meta_update_target == 'LL' or \
                        config.meta_update_target == 'both'):
                        self._agent.store_episode(rollout)
                        print('\n the storing of episode self._agent.store_episode',self._agent.store_episode(rollout))
                else:
                    self._agent.store_episode(rollout)

            step_per_batch = mpi_sum(run_step)

            logger.info('Update networks %d', update_iter)
            if config.meta:
                if (config.meta_update_target == 'HL' or \
                    config.meta_update_target == 'both'):
                    train_info = self._meta_agent.train()
                    hl_train_info = train_info
                else:
                    hl_train_info = None
                if (config.meta_update_target == 'LL' or \
                    config.meta_update_target == 'both'):
                    train_info = self._agent.train()
                    ll_train_info = train_info
                else:
                    ll_train_info = None
                if config.meta_update_target == 'both':
                    train_info = {}
                    train_info.update({k + '_hl': v for k, v in hl_train_info.items()})
                    train_info.update({k + '_ll': v for k, v in ll_train_info.items()})
            else:
                train_info = self._agent.train()

            logger.info('Update networks done')


            if step < config.max_ob_norm_step:
                self._update_normalizer(rollout)

            step += step_per_batch
            update_iter += 1

            if self._is_chef:
                pbar.update(step_per_batch)

                if update_iter % config.log_interval == 0:
                    for k, v in info.items():
                        if isinstance(v, list):
                            ep_info[k].extend(v)
                        else:
                            ep_info[k].append(v)
                    train_info.update({
                        'sec': (time() - st_time) / config.log_interval,
                        'steps_per_sec': (step - st_step) / (time() - st_time),
                        'update_iter': update_iter
                    })
                    st_time = time()
                    st_step = step
                    self._log_train(step, train_info, ep_info)
                    ep_info = defaultdict(list)

                if update_iter % config.evaluate_interval == 0:
                    logger.info('Evaluate at %d', update_iter)
                    rollout, info = self._evaluate(step=step, record=config.record)
                    self._log_test(step, info)

                if update_iter % config.ckpt_interval == 0:
                    self._save_ckpt(step, update_iter)

        logger.info('Reached %s steps. worker %d stopped.', step, config.rank)

    def _update_normalizer(self, rollout):
        """ Updates normalizer with @rollout. """
        if self._config.ob_norm:
            self._meta_agent.update_normalizer(rollout['ob'])
            self._agent.update_normalizer(rollout['ob'])

    def _save_success_qpos(self, info):
        """ Saves the final qpos of successful trajectory. """
        if self._config.save_qpos and info['episode_success']:
            path = os.path.join(self._config.record_dir, 'qpos.p')
            with h5py.File(path, 'a') as f:
                key_id = len(f.keys())
                num_qpos = len(info['saved_qpos'])
                for qpos_to_save in info['saved_qpos']:
                    f['{}'.format(key_id)] = qpos_to_save
                    key_id += 1
        if self._config.save_success_qpos and info['episode_success']:
            path = os.path.join(self._config.record_dir, 'success_qpos.p')
            with h5py.File(path, 'a') as f:
                key_id = len(f.keys())
                num_qpos = len(info['saved_qpos'])
                for qpos_to_save in info['saved_qpos'][int(num_qpos / 2):]:
                    f['{}'.format(key_id)] = qpos_to_save
                    key_id += 1

    def _evaluate(self, step=None, record=False, idx=None):
        """
        Runs one rollout if in eval mode (@idx is not None).
        Runs num_record_samples rollouts if in train mode (@idx is None).

        Args:
            step: the number of environment steps.
            record: whether to record video or not.
        """
        for i in range(self._config.num_record_samples):
            rollout, meta_rollout, info, frames = \
                self._runner.run_episode(is_train=False, record=record)

            if record:
                ep_rew = info['rew']
                ep_success = 's' if info['episode_success'] else 'f'
                fname = '{}_step_{:011d}_{}_r_{}_{}.mp4'.format(
                    self._env.name, step, idx if idx is not None else i,
                    ep_rew, ep_success)
                self._save_video(fname, frames)

            if idx is not None:
                break

        logger.info('rollout: %s', {k: v for k, v in info.items() if not 'qpos' in k})
        self._save_success_qpos(info)
        return rollout, info

    def evaluate(self):
        """ Evaluates an agent stored in chekpoint with @self._config.ckpt_num. """
        step, update_iter = self._load_ckpt(ckpt_num=self._config.ckpt_num)

        logger.info('Run %d evaluations at step=%d, update_iter=%d',
                    self._config.num_eval, step, update_iter)
        info_history = defaultdict(list)
        rollouts = []
        for i in trange(self._config.num_eval):
            logger.warn("Evalute run %d", i+1)
            rollout, info = \
                self._evaluate(step=step, record=self._config.record, idx=i)
            for k, v in info.items():
                info_history[k].append(v)
            if self._config.save_rollout:
                rollouts.append(rollout)

        keys = ['episode_success', 'reward_goal_dist']
        os.makedirs('result', exist_ok=True)
        with h5py.File('result/{}.hdf5'.format(self._config.run_name), 'w') as hf:
            for k in keys:
                hf.create_dataset(k, data=info_history[k])

            result = '{:.02f} $\\pm$ {:.02f}'.format(
                    np.mean(info_history['episode_success']),
                    np.std(info_history['episode_success'])
            )
            logger.warn(result)

        if self._config.save_rollout:
            os.makedirs('saved_rollouts', exist_ok=True)
            with open('saved_rollouts/{}.p'.format(self._config.run_name), 'wb') as f:
                pickle.dump(rollouts, f)


