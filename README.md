# Decentralized-and-multi-agent-control-of-Franka-Emika-Panda-robot-in-continuous-task-execution
This Repository contains the Python and Mujoco interactive code and simulation for Ubuntu Linux on Decentralized and multi agent control of Franka Emika Panda robot in continuous task execution

Intelligent Task Learning code contains a http://www.mujoco.org/ MUJOCO multiphysics operated simulated environment , where Soft Actor Critic https://arxiv.org/abs/1812.05905 and Proximal Policy Optimization (PPO) algorithms https://arxiv.org/abs/1707.06347 can be used as neural network reinforcement learning methods to perform grasping and lifting cube tasks. Monitoring of the data obtained is done with the use of Weights and Biases software https://wandb.ai/site.

Installation
To use this toolkit, it is required to first install MuJoCo 200 https://www.roboti.us/index.html and then mujoco-py  https://github.com/openai/mujoco-py from Open AI. mujoco-py allows using MuJoCo from python interface. The installation requires python 3.6 or higher. It is recommended to install all the required packages under a conda virtual environment

References
This toolit is mainly developed based on Surreal Robotics Suite and the Reinforcement learning part is referenced from this repo  https://github.com/clvrai/furniture
