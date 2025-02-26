#  Copyright (c) 2022.
#  ProrokLab (https://www.proroklab.org/)
#  All rights reserved.

from enum import Enum
from pathlib import Path
from typing import Set, Union, List

import matplotlib.patches as mpatches
import matplotlib.ticker as mtick
import numpy as np
import tikzplotlib
from matplotlib import pyplot as plt

from utils import EvaluationUtils, InjectMode, PathUtils


class ResilencePlottinMode(Enum):
    VIOLIN = 1
    PERFORMANCE_MAINTEINED = 2


def adjacent_values(vals, q1, q3):
    upper_adjacent_value = q3 + (q3 - q1) * 1.5
    upper_adjacent_value = np.clip(upper_adjacent_value, q3, vals[-1])

    lower_adjacent_value = q1 - (q3 - q1) * 1.5
    lower_adjacent_value = np.clip(lower_adjacent_value, vals[0], q1)
    return lower_adjacent_value, upper_adjacent_value


def evaluate_resilience(
    checkpoint_paths: List[Union[str, Path]],
    n_episodes_per_model: int,
    agents_to_inject: Set,
    inject_mode: InjectMode,
    noise_delta: float,
    plotting_mode: ResilencePlottinMode,
    compute_also_non_injected: bool = True,
):
    """
    Runs resilience evaluation

    :param checkpoint_paths: List of checkpoints of models to load
    :param n_episodes_per_model: Number of episodes to run each policy on
    :param agents_to_inject: A set of indices of the agents to inject
    :param inject_mode:
    :param noise_delta: In case of nosie injection, the action will be the normal action + Uniform(-noise_delta,  noise_delta)
    :param compute_also_non_injected: Wether to run evaluation of non-injected models as well for comparison
    """

    fig, ax = plt.subplots(figsize=(16, 9))
    rewards_to_plot = []
    labels = []
    x_tick_lkabels = []
    colors = plt.rcParams["axes.prop_cycle"]()
    c1 = next(colors)["color"]
    c2 = next(colors)["color"]
    figure_title = None
    figure_name = None

    inject_title, inject_name = EvaluationUtils.get_inject_name(
        agents_to_inject=agents_to_inject,
        noise_delta=noise_delta,
        inject_mode=inject_mode,
    )

    for model_num, checkpoint_path in enumerate(checkpoint_paths):

        (
            config,
            trainer,
            env,
        ) = EvaluationUtils.get_config_trainer_and_env_from_checkpoint(checkpoint_path)

        if figure_title is not None:
            assert (figure_title, figure_name) == EvaluationUtils.get_model_name(
                config
            )[2:]

        (
            model_title,
            model_name,
            env_title,
            env_name,
        ) = EvaluationUtils.get_model_name(config)

        figure_title = env_title
        figure_name = env_name

        rewards_bef_and_after = []

        for inject in [False, True] if compute_also_non_injected else [True]:

            rewards, _, _, _ = EvaluationUtils.rollout_episodes(
                n_episodes=n_episodes_per_model,
                render=False,
                get_obs=False,
                get_actions=False,
                trainer=trainer,
                env=env,
                inject=inject,
                inject_mode=inject_mode,
                agents_to_inject=agents_to_inject,
                noise_delta=noise_delta,
            )
            rewards_bef_and_after.append(rewards)

            if plotting_mode is ResilencePlottinMode.VIOLIN:
                rewards = sorted(rewards)

                rewards_violin = ax.violinplot(
                    rewards,
                    [model_num],
                    showmeans=False,
                    showmedians=False,
                    showextrema=False,
                )

                for pc in rewards_violin["bodies"]:
                    pc.set_facecolor(c1 if not inject else c2)
                    # pc.set_edgecolor("black")
                    pc.set_alpha(0.65)

                quartile1, medians, quartile3 = np.percentile(rewards, [25, 50, 75])
                whiskers = np.array([adjacent_values(rewards, quartile1, quartile3)])
                whiskers_min, whiskers_max = whiskers[:, 0], whiskers[:, 1]

                inds = model_num
                ax.scatter(
                    inds,
                    medians,
                    marker="o",
                    color="white",
                    s=30,
                    zorder=3,
                    edgecolors="black",
                )
                ax.vlines(inds, quartile1, quartile3, color="k", linestyle="-", lw=5)
                ax.vlines(
                    inds, whiskers_min, whiskers_max, color="k", linestyle="-", lw=1
                )

                rewards_to_plot.append(rewards)
                labels.append(
                    (
                        mpatches.Patch(
                            color=rewards_violin["bodies"][0].get_facecolor().flatten()
                        ),
                        f"{'Injected' if inject else 'Normal'}",
                    )
                )

        if plotting_mode is ResilencePlottinMode.PERFORMANCE_MAINTEINED:
            mean_before = np.array(rewards_bef_and_after[0]).mean()
            mean_after = np.array(rewards_bef_and_after[1]).mean()
            median_before = np.median(np.array(rewards_bef_and_after[0]))
            median_after = np.median(np.array(rewards_bef_and_after[1]))

            mean_perf_after = (mean_after / mean_before) * 100
            median_perf_after = (median_after / median_before) * 100

            mean_point = ax.scatter(
                model_num, mean_perf_after, marker="o", color=c1, s=100
            )
            labels.append(
                (
                    mean_point,
                    f"Mean",
                )
            )
            median_point = ax.scatter(
                model_num, median_perf_after, marker="x", color=c2, s=100
            )
            labels.append(
                (
                    median_point,
                    f"Median",
                )
            )
            ax.yaxis.set_major_formatter(mtick.PercentFormatter())

        x_tick_lkabels.append(model_title)

    ax.yaxis.grid(True)
    ax.set_ylabel(
        f"Reward violin with median for {n_episodes_per_model} episodes"
        if plotting_mode is ResilencePlottinMode.VIOLIN
        else f"Performance maintained after injection for {n_episodes_per_model} episodes",
        fontsize=14,
    )
    ax.set_xticks(
        np.arange(len(x_tick_lkabels)), labels=x_tick_lkabels, rotation=0, fontsize=14
    )

    plt.legend(
        *zip(*(labels[:2])),
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        fancybox=True,
        shadow=True,
        fontsize=14,
        ncol=2,
    )

    fig.suptitle(figure_title, fontsize=16)
    ax.set_title(inject_title, fontsize=14)

    save_dir = PathUtils.result_dir / f"{figure_title}/resilience evaluation"
    name = inject_name
    plt.savefig(str(save_dir / f"eval_resilience_{name}_{plotting_mode}.pdf"))


def evaluate_increasing_noise(
    checkpoint_paths: List[Union[str, Path]],
    n_episodes_per_model: int,
    agents_to_inject: Set,
    inject_mode: InjectMode,
    plotting_mode: ResilencePlottinMode,
):
    noises = np.linspace(0, 2, 50)
    rewards = np.zeros(
        (
            len(checkpoint_paths),
            len(noises),
            n_episodes_per_model,
        )
    )
    done = np.zeros(
        (
            len(checkpoint_paths),
            len(noises),
            n_episodes_per_model,
        )
    )
    trainers = [
        EvaluationUtils.get_config_trainer_and_env_from_checkpoint(checkpoint_path)[1]
        for checkpoint_path in checkpoint_paths
    ]
    envs = [
        EvaluationUtils.get_config_trainer_and_env_from_checkpoint(checkpoint_path)[2]
        for checkpoint_path in checkpoint_paths
    ]
    for j, noise in enumerate(noises):
        for i, trainer in enumerate(trainers):
            rews, _, obs, _ = EvaluationUtils.rollout_episodes(
                n_episodes=n_episodes_per_model,
                render=False,
                get_obs=True,
                get_actions=False,
                trainer=trainer,
                env=envs[i],
                inject=True,
                inject_mode=inject_mode,
                agents_to_inject=agents_to_inject,
                noise_delta=noise,
            )

            len_obs = np.array([len(o) for o in obs])
            rewards[i, j] = rews
            done[i, j] = (len_obs < trainer.config["env_config"]["max_steps"]).astype(
                int
            )

    fig, ax = plt.subplots(figsize=(5, 5))
    CB_color_cycle = [
        "#377eb8",
        "#ff7f00",
        "#4daf4a",
        "#f781bf",
        "#a65628",
        "#984ea3",
        "#999999",
        "#e41a1c",
        "#dede00",
    ]
    ax.grid()
    for model_num, trainer in enumerate(trainers):
        (
            model_title,
            model_name,
            env_title,
            env_name,
        ) = EvaluationUtils.get_model_name(trainer.config)

        to_plot = (rewards + 10) / 60
        # to_plot = done

        mean = to_plot[model_num].mean(1)
        std = to_plot[model_num].std(1)
        model_title = "HetGPPO" if model_title == "HetGIPPO" else "GPPO"
        (mean_line,) = ax.plot(
            noises, mean, label=model_title, color=CB_color_cycle[model_num]
        )
        ax.fill_between(
            noises,
            mean + std,
            mean - std,
            color=mean_line.get_color(),
            alpha=0.3,
        )
    ax.set_xlabel("Uniform observation noise")
    ax.set_ylabel("Reward")
    ax.legend()

    tikzplotlib.save(
        f"trial.tex",
        textsize=18,
    )
    plt.savefig(f"trial.pdf", bbox_inches="tight", pad_inches=0)
    plt.show()


def evaluate_het_test():
    # HetGIPPO
    checkpoint_paths.append(
        "/Users/Matteo/Downloads/het_test/hetgippo/MultiPPOTrainer_het_test_ecc9e_00000_0_2022-09-12_14-43-46/checkpoint_000093/checkpoint-93"
    )
    # Gippo
    checkpoint_paths.append(
        "/Users/Matteo/Downloads/het_test/gippo/MultiPPOTrainer_het_test_18f2c_00000_0_2022-09-12_14-45-00/checkpoint_000116/checkpoint-116"
    )

    tex_fonts = {
        # Use LaTeX to write all text
        "text.usetex": True,
        "text.latex.preamble": "\\usepackage{libertine}\n\\usepackage[libertine]{newtxmath}",
        "font.family": "Linux Libertine",
        # Use 10pt font in plots, to match 10pt font in document
        "axes.labelsize": 19,
        "font.size": 10,
        # Make the legend/label fonts a little smaller
        "legend.fontsize": 16,
        "legend.title_fontsize": 7,
        "xtick.labelsize": 16,
        "ytick.labelsize": 16,
    }

    plt.rcParams.update(tex_fonts)

    evaluate_increasing_noise(
        checkpoint_paths, 100, {0, 1}, InjectMode.OBS_NOISE, ResilencePlottinMode.VIOLIN
    )  # 50 datapoints


def evaluate_give_way():
    # Give way

    # HetGippo
    checkpoint_paths.append(
        "/Users/Matteo/Downloads/give_way/hetgippo/MultiPPOTrainer_give_way_553c5_00000_0_2022-09-12_23-00-37/checkpoint_000300/checkpoint-300"
    )
    # Gippo
    checkpoint_paths.append(
        "/Users/Matteo/Downloads/give_way/gippo/MultiPPOTrainer_give_way_5dee1_00000_0_2022-09-12_23-00-52/checkpoint_000300/checkpoint-300"
    )

    tex_fonts = {
        # Use LaTeX to write all text
        "text.usetex": True,
        "text.latex.preamble": "\\usepackage{libertine}\n\\usepackage[libertine]{newtxmath}",
        "font.family": "Linux Libertine",
        # Use 10pt font in plots, to match 10pt font in document
        "axes.labelsize": 19,
        "font.size": 10,
        # Make the legend/label fonts a little smaller
        "legend.fontsize": 16,
        "legend.title_fontsize": 7,
        "xtick.labelsize": 16,
        "ytick.labelsize": 16,
    }

    plt.rcParams.update(tex_fonts)

    evaluate_increasing_noise(
        checkpoint_paths, 100, {0, 1}, InjectMode.OBS_NOISE, ResilencePlottinMode.VIOLIN
    )  # 50 datapoints


if __name__ == "__main__":

    checkpoint_paths = []

    evaluate_het_test()
    # for noise_delta in [0.1]:
    #     for agents_to_inject in [{0, 1}]:
    #         evaluate_resilience(
    #             checkpoint_paths=checkpoint_paths,
    #             n_episodes_per_model=20,
    #             agents_to_inject=agents_to_inject,
    #             inject_mode=InjectMode.OBS_NOISE,
    #             noise_delta=noise_delta,
    #             compute_also_non_injected=True,
    #             plotting_mode=ResilencePlottinMode.PERFORMANCE_MAINTEINED,
    #         )
