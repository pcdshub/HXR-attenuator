import numpy as np
from caproto.server import PVGroup

from .db.filters import FilterGroup
from .db.system import SystemGroup


class IOCMain(PVGroup):
    """
    """

    def __init__(self, prefix, *, filters, groups, abs_data, config_data,
                 eV, pmps_run, pmps_tdes, **kwargs):
        super().__init__(prefix, **kwargs)
        self.prefix = prefix
        self.filters = filters
        self.groups = groups
        self.config_data = config_data
        self.monitor_pvnames = dict(
            ev=eV,
            pmps_run=pmps_run,
            pmps_tdes=pmps_tdes,
        )

    @property
    def working_filters(self):
        """
        Returns a dictionary of all filters that are in working order

        That is to say, filters that are not stuck.
        """
        return {
            idx: filt for idx, filt in self.filters.items()
            if filt.is_stuck.value != "True"
        }

    def t_calc(self):
        """
        Total transmission through all filter blades.

        Stuck blades are assumed to be 'OUT' and thus the total transmission
        will be overestimated (in the case any blades are actually stuck 'IN').
        """
        t = 1.
        for filt in self.working_filters.values():
            t *= filt.transmission.value
        return t

    def t_calc_3omega(self):
        """
        Total 3rd harmonic transmission through all filter blades.

        Stuck blades are assumed to be 'OUT' and thus the total transmission
        will be overestimated (in the case any blades are actually stuck 'IN').
        """
        t = 1.
        for filt in self.working_filters.values():
            t *= filt.transmission_3omega.value
        return t

    def all_transmissions(self):
        """
        Return an array of the transmission values for each filter at the
        current photon energy.

        Stuck filters get a transmission of NaN, which omits them from
        calculations/considerations.
        """
        T_arr = np.zeros(len(self.filters)) * np.nan
        for idx, filt in self.working_filters.items():
            T_arr[idx - 1] = filt.transmission.value
        return T_arr

    def _find_configs(self, T_des=None):
        """
        Find the optimal configurations for attaining desired transmission
        ``T_des`` at the current photon energy.

        Returns configurations which yield closest highest and lowest
        transmissions and their filter configurations.
        """
        if not T_des:
            T_des = self.sys.t_desired.value

        # Basis vector of all filter transmission values.
        # Note: Stuck filters have transmission of `NaN`.
        T_basis = self.all_transmissions()

        # Table of transmissions for all configurations
        # is obtained by multiplying basis by
        # configurations in/out state matrix.
        T_table = np.nanprod(T_basis*self.config_table,
                             axis=1)

        # Create a table of configurations and their associated
        # beam transmission values, sorted by transmission value.
        configs = np.asarray([T_table, np.arange(len(self.config_table))])

        # Sort based on transmission value, retaining index order:
        sort_indices = configs[0, :].argsort()
        T_config_table = configs.T[sort_indices]

        # Find the index of the filter configuration which
        # minimizes the differences between the desired
        # and closest achievable transmissions.
        i = np.argmin(np.abs(T_config_table[:, 0]-T_des))

        # Obtain the optimal filter configuration and its transmission.
        closest = self.config_table[int(T_config_table[i, 1])]
        T_closest = np.nanprod(T_basis*closest)

        # Determine the optimal configurations for "best highest"
        # and "best lowest" achievable transmissions.
        if T_closest == T_des:
            # The optimal configuration achieves the desired
            # transmission exactly.
            config_bestHigh = config_bestLow = closest
            T_bestHigh = T_bestLow = T_closest
        elif T_closest < T_des:
            idx = min((i + 1, len(T_config_table) - 1))
            config_bestHigh = self.config_table[int(T_config_table[idx, 1])]
            config_bestLow = closest
            T_bestHigh = np.nanprod(T_basis*config_bestHigh)
            T_bestLow = T_closest
        elif T_closest > T_des:
            idx = max((i - 1, 0))
            config_bestHigh = closest.astype(np.int)
            config_bestLow = self.config_table[int(T_config_table[idx, 1])]
            T_bestHigh = T_closest
            T_bestLow = np.nanprod(T_basis*config_bestLow)

        return (np.nan_to_num(config_bestLow).astype(np.int),
                np.nan_to_num(config_bestHigh).astype(np.int),
                T_bestLow,
                T_bestHigh)

    def _get_config(self, T_des=None):
        """
        Return the optimal floor (lower than desired transmission) or ceiling
        (higher than desired transmission) configuration based on the current
        mode setting.
        """
        if not T_des:
            T_des = self.sys.t_desired.value
        mode = self.sys.mode.value

        conf = self.find_configs()
        config_bestLow, config_bestHigh, T_bestLow, T_bestHigh = conf

        if mode == "Floor":
            return config_bestLow, T_bestLow, T_des
        return config_bestHigh, T_bestHigh, T_des

    def _print_config(self, w=80):
        """Format and print the optimal configuration."""
        config, T_best, T_des = self.get_config()
        print("="*w)
        print("Desired transmission value: {}".format(T_des))
        print("-"*w)
        print("Best possible transmission value: {}".format(T_best))
        print("-"*w)
        print(config.astype(np.int))
        print("="*w)


def create_ioc(prefix,
               *,
               eV_pv,
               pmps_run_pv,
               pmps_tdes_pv,
               filter_group,
               absorption_data,
               config_data,
               **ioc_options):
    """IOC Setup."""
    groups = {}
    filters = {}
    ioc = IOCMain(prefix=prefix,
                  filters=filters,
                  groups=groups,
                  abs_data=absorption_data,
                  config_data=config_data,
                  eV=eV_pv,
                  pmps_run=pmps_run_pv,
                  pmps_tdes=pmps_tdes_pv,
                  **ioc_options)

    for index, group_prefix in filter_group.items():
        filt = FilterGroup(f'{prefix}:FILTER:{group_prefix}:',
                           abs_data=absorption_data, ioc=ioc, index=index)
        ioc.filters[index] = filt
        ioc.groups[group_prefix] = filt

    ioc.groups['SYS'] = SystemGroup(f'{prefix}:SYS:', ioc=ioc)
    ioc.sys = ioc.groups['SYS']

    for group in ioc.groups.values():
        ioc.pvdb.update(**group.pvdb)

    return ioc
