import dataclasses
from typing import List

import numpy as np
import pytest

from .. import calculator

import matplotlib  # isort: skip  # noqa

matplotlib.use('Agg')

import matplotlib.pyplot as plt  # isort: skip  # noqa


@dataclasses.dataclass
class Filter:
    material: str
    thickness: float
    transmission: float = 0.0


@dataclasses.dataclass
class Blade:
    filters: List[Filter]


@pytest.fixture(params=[2000, 3000, 5000, 8000, 12_000, 20_000, 25_000])
def photon_energy(request) -> float:
    return float(request.param)


@pytest.fixture(params=range(500, 5_000, 500))
def soft_photon_energy(request) -> float:
    return float(request.param)


@pytest.fixture(params=[calculator.ConfigMode.Floor,
                        calculator.ConfigMode.Ceiling])
def mode(request) -> calculator.ConfigMode:
    return request.param


absorption_tables = {}
_subplots = {}


def get_transmission(material: str,
                     thickness: float,
                     photon_energy: float) -> np.ndarray:
    """Get the transmission for a given material at a specific energy."""
    try:
        table = absorption_tables[material]
    except KeyError:
        table = calculator.get_absorption_table(material)
        absorption_tables[material] = table
    return calculator.get_transmission(
        photon_energy, table=table, thickness=thickness * 1e-6
    )


@pytest.mark.parametrize(
    'diamond_thicknesses, si_thicknesses',
    [
        pytest.param(
            [1280, 640, 320, 160, 80, 40, 20, 10],
            [10240, 5120, 2560, 1280, 640, 320, 160, 80, 40, 20],
            id='all_working'
        ),
        pytest.param(
            [640, 320, 160, 80, 40, 20, 10],
            [10240, 5120, 2560, 1280, 640, 320, 160, 80, 40, 20],
            id='missing_C_1280'
        ),
        pytest.param(
            [640, 320, 160, 80, 40],
            [10240, 5120, 2560, 1280, 640, 320, 160, 80, 40, 20],
            id='missing_C_10_20'
        ),
    ]
)
def test_material_prioritization(request, diamond_thicknesses, si_thicknesses,
                                 mode,
                                 photon_energy):
    diamond_filters = [
        Filter('C', thickness, get_transmission('C', thickness, photon_energy))
        for thickness in diamond_thicknesses
    ]
    silicon_filters = [
        Filter('Si', thickness, get_transmission('Si', thickness,
                                                 photon_energy))
        for thickness in si_thicknesses
    ]
    filters = diamond_filters + silicon_filters

    t_all_diamond = np.product([flt.transmission for flt in diamond_filters])

    t_des_checks = (
        list(np.linspace(0.0, t_all_diamond, 1500)) +
        list(np.linspace(t_all_diamond, 1.0, 1500))
    )

    materials = [flt.material for flt in filters]
    transmissions = [flt.transmission for flt in filters]

    compared = []
    actual = []
    for t_des in t_des_checks:
        conf = calculator.get_best_config_with_material_priority(
            materials=materials,
            transmissions=transmissions,
            material_order=['C', 'Si'],
            t_des=t_des,
            mode=mode,
        )

        inserted_materials = [
            flt.material for state, flt in zip(conf.filter_states, filters)
            if state
        ]
        if 'Si' in inserted_materials:
            assert inserted_materials.count('C') == len(diamond_filters)

        actual.append(conf.transmission)
        if t_des > 0.0:
            compared.append(abs(t_des - conf.transmission) / t_des)
        else:
            compared.append(0.0)

    print()
    print('(t_des - t_act) / t_des:')
    print('    Standard deviation:', np.std(compared))
    print('    Average:', np.average(compared))

    # I'm sure there's a better way to do this:
    param_id = request.node.name.rsplit('-', 1)[1].strip(']')
    # -> param_id = 'all_working'
    param_id = f'{param_id}_{mode.name}'

    try:
        subplot = _subplots[param_id]
    except KeyError:
        fig = plt.figure(figsize=(12, 6), dpi=200)
        _subplots[param_id] = subplot = fig.subplots(1, 2)

        # fig.suptitle(param_id)
        subplot[0].set_title('Transmission Actual vs Desired')
        subplot[1].set_title('Error vs Desired')
        # fig.tight_layout()

    line, = subplot[0].plot(t_des_checks, actual,
                            alpha=0.5,
                            lw=1,
                            label=f'{photon_energy} eV')
    subplot[0].plot([t_all_diamond], [t_all_diamond],
                    marker='x',
                    markersize=3,
                    markerfacecolor=line.get_color(),
                    color=line.get_color(),
                    )
    subplot[0].annotate(
        f'{photon_energy:.0f} eV',
        (t_all_diamond, t_all_diamond),
        (t_all_diamond - 0.2, t_all_diamond),
        color=line.get_color(),
    )
    subplot[0].legend(loc='best')

    subplot[1].plot(t_des_checks,
                    np.asarray(actual) - np.asarray(t_des_checks),
                    label=f'{photon_energy} eV',
                    alpha=0.5, lw=1, color=line.get_color())
    subplot[0].set_xlabel("Desired transmission")
    subplot[0].set_ylabel("Actual transmission")
    subplot[1].set_xlabel("Desired transmission")
    subplot[1].set_ylabel("(Actual - desired) transmission")
    subplot[0].figure.savefig(f'{param_id}.pdf')
    subplot[0].figure.savefig(f'{param_id}.png', transparent=True,
                              bbox_inches='tight', pad_inches=0.2)


@pytest.mark.parametrize(
    'blades',
    [
        pytest.param(
            [
                Blade([
                    Filter('C', 25),
                    Filter('C', 50),
                    Filter('C', 100),
                    Filter('Si', 320),
                    Filter('Si', 160),
                    Filter('Si', 80),
                    Filter('Si', 40),
                    Filter('Si', 20),
                ]),
                Blade([
                    Filter('C', 50),
                    Filter('C', 25),
                    Filter('C', 12),
                    Filter('C', 10),
                ]),
                Blade([
                    Filter('C', 25),
                    Filter('C', 12),
                    Filter('C', 6),
                ]),
                Blade([
                    Filter('C', 12),
                    Filter('C', 6),
                    Filter('C', 3),
                    Filter('C', 3),  # according to traveler
                    Filter('Al', 0.2),
                ]),
            ],
            id='at1k4'
        ),
    ]
)
def test_ladder(request, blades, mode, soft_photon_energy):
    photon_energy = soft_photon_energy

    # Update our test fixture here with the correct transmission
    for blade in blades:
        for flt in blade.filters:
            flt.transmission = get_transmission(
                flt.material, flt.thickness,
                soft_photon_energy
            )

    t_des_checks = np.linspace(0.0, 1.0, 2000)

    compared = []
    actual = []
    for t_des in t_des_checks:
        conf = calculator.get_ladder_config(
            [[flt.transmission for flt in blade.filters] for blade in blades],
            t_des=t_des,
            mode=mode,
        )

        # print(t_des, conf.transmission, conf.filter_states)
        actual.append(conf.transmission)
        if t_des > 0.0:
            compared.append(abs(t_des - conf.transmission) / t_des)
        else:
            compared.append(0.0)

    print()
    print('(t_des - t_act) / t_des:')
    print('    Standard deviation:', np.std(compared))
    print('    Average:', np.average(compared))

    # I'm sure there's a better way to do this:
    param_id = request.node.name.rsplit('-', 1)[1].strip(']')
    # -> param_id = 'all_working'
    param_id = f'{param_id}_{mode.name}'

    try:
        subplot = _subplots[param_id]
    except KeyError:
        fig = plt.figure(figsize=(12, 6), dpi=200)
        _subplots[param_id] = subplot = fig.subplots(1, 2)

        # fig.suptitle(param_id)
        subplot[0].set_title('Transmission Actual vs Desired')
        subplot[1].set_title('Error vs Desired')
        # fig.tight_layout()

    line, = subplot[0].plot(t_des_checks, actual,
                            alpha=0.5,
                            lw=1,
                            label=f'{photon_energy} eV')
    subplot[0].legend(loc='best')

    subplot[1].plot(t_des_checks,
                    np.asarray(actual) - np.asarray(t_des_checks),
                    label=f'{photon_energy} eV',
                    alpha=0.5, lw=1, color=line.get_color())
    subplot[0].set_xlabel("Desired transmission")
    subplot[0].set_ylabel("Actual transmission")
    subplot[1].set_xlabel("Desired transmission")
    subplot[1].set_ylabel("(Actual - desired) transmission")
    subplot[0].figure.savefig(f'{param_id}.pdf')
    subplot[0].figure.savefig(f'{param_id}.png', transparent=True,
                              bbox_inches='tight', pad_inches=0.2)
