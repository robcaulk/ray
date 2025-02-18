from typing import Any, Dict, Union

import lightgbm

from ray.train import Checkpoint
from ray.train.gbdt_trainer import GBDTTrainer
from ray.train.lightgbm import RayTrainReportCallback
from ray.util.annotations import PublicAPI


@PublicAPI(stability="beta")
class LightGBMTrainer(GBDTTrainer):
    """A Trainer for data parallel LightGBM training.

    This Trainer runs the LightGBM training loop in a distributed manner
    using multiple Ray Actors.

    If you would like to take advantage of LightGBM's built-in handling
    for features with the categorical data type, consider applying the
    :class:`Categorizer` preprocessor to set the dtypes in the dataset.

    .. note::
        ``LightGBMTrainer`` does not modify or otherwise alter the working
        of the LightGBM distributed training algorithm.
        Ray only provides orchestration, data ingest and fault tolerance.
        For more information on LightGBM distributed training, refer to
        `LightGBM documentation <https://lightgbm.readthedocs.io/>`__.

    Example:
        .. testcode::

            import ray

            from ray.train.lightgbm import LightGBMTrainer
            from ray.train import ScalingConfig

            train_dataset = ray.data.from_items(
                [{"x": x, "y": x + 1} for x in range(32)]
            )
            trainer = LightGBMTrainer(
                label_column="y",
                params={"objective": "regression"},
                scaling_config=ScalingConfig(num_workers=3),
                datasets={"train": train_dataset},
            )
            result = trainer.fit()

        .. testoutput::
            :hide:

            ...

    Args:
        datasets: The Ray Datasets to use for training and validation. Must include a
            "train" key denoting the training dataset. All non-training datasets will
            be used as separate validation sets, each reporting a separate metric.
        label_column: Name of the label column. A column with this name
            must be present in the training dataset.
        params: LightGBM training parameters passed to ``lightgbm.train()``.
            Refer to `LightGBM documentation <https://lightgbm.readthedocs.io>`_
            for a list of possible parameters.
        dmatrix_params: Dict of ``dataset name:dict of kwargs`` passed to respective
            :class:`xgboost_ray.RayDMatrix` initializations, which in turn are passed
            to ``lightgbm.Dataset`` objects created on each worker. For example, this
            can be used to add sample weights with the ``weight`` parameter.
        num_boost_round: Target number of boosting iterations (trees in the model).
            Note that unlike in ``lightgbm.train``, this is the target number
            of trees, meaning that if you set ``num_boost_round=10`` and pass a model
            that has already been trained for 5 iterations, it will be trained for 5
            iterations more, instead of 10 more.
        scaling_config: Configuration for how to scale data parallel training.
        run_config: Configuration for the execution of the training run.
        resume_from_checkpoint: A checkpoint to resume training from.
        metadata: Dict that should be made available in `checkpoint.get_metadata()`
            for checkpoints saved from this Trainer. Must be JSON-serializable.
        **train_kwargs: Additional kwargs passed to ``lightgbm.train()`` function.
    """

    _default_ray_params: Dict[str, Any] = {
        "checkpoint_frequency": 1,
        "allow_less_than_two_cpus": True,
        "num_actors": 1,
        "cpus_per_actor": 2,
        "gpus_per_actor": 0,
    }
    _init_model_arg_name: str = "init_model"

    def __init__(self, *args, **kwargs):
        # TODO(justinvyu): Fix circular import by moving lightgbm_ray into ray
        import lightgbm_ray.tune

        # Currently, the RayDMatrix in lightgbm_ray is the same as in xgboost_ray
        # but it is explicitly set here for forward compatibility
        self._dmatrix_cls: type = lightgbm_ray.RayDMatrix
        self._ray_params_cls: type = lightgbm_ray.RayParams
        self._tune_callback_checkpoint_cls: type = (
            lightgbm_ray.tune.TuneReportCheckpointCallback
        )

        super().__init__(*args, **kwargs)

    @classmethod
    def get_model(
        cls,
        checkpoint: Checkpoint,
    ) -> lightgbm.Booster:
        """Retrieve the LightGBM model stored in this checkpoint."""
        return RayTrainReportCallback.get_model(checkpoint)

    def _train(self, **kwargs):
        import lightgbm_ray

        return lightgbm_ray.train(**kwargs)

    def _model_iteration(
        self, model: Union[lightgbm.LGBMModel, lightgbm.Booster]
    ) -> int:
        if isinstance(model, lightgbm.Booster):
            return model.current_iteration()
        return model.booster_.current_iteration()
