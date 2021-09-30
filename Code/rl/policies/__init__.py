from .mlp_actor_critic import MlpActor, MlpCritic
#from .mlp1_actor_critic import MlpActor1, MlpCritic1
from .mlp_actor_critic import MlpActor, MlpCritic


def get_actor_critic_by_name(name):
    if name == 'mlp':
        return MlpActor, MlpCritic
    else:
        raise NotImplementedError()

