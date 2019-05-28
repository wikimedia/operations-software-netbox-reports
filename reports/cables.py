"""
Check certain kinds of devices for the presence of a console port.
"""

import re

from dcim.constants import (
    DEVICE_STATUS_DECOMMISSIONING,
    DEVICE_STATUS_INVENTORY,
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_PLANNED,
)
from dcim.models import ConsolePort, ConsoleServerPort, Interface, PowerPort, PowerOutlet
from extras.reports import Report

# these are statuses for devices that we care about
EXCLUDE_STATUSES = (
    DEVICE_STATUS_DECOMMISSIONING,
    DEVICE_STATUS_INVENTORY,
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_PLANNED,
)

# For ergonomics the regexps that match interface names are placed in this
# tuple. This is later joined with | to make the final regexp.
INTERFACES_REGEXP = (
    r"^mgmt\d?$|^ILO$|^i?DRAC$",  # managment interfaces
    r"^fxp\d-re\d$",  # routing engine management interfaces
    r"^[a-z]+-\d+/\d+/\d+(\.\d+){0,1}$",  # Juniper interfaces eg et-0/0/0
    r"^[a-z]{1,4}(\d+){0,1}(\.\d+){0,1}$",  # typical device names (eg eth0) and vlan.900 etc.
    r"^enp\d+s\d+(f\d+)?((d|np)\d+)?$",  # systemd 'path' devices
    r"^\d+$",  # Netgear switch interfaces are just numbers.
)


class Cables(Report):
    description = __doc__

    def _port_names_test(self, queryset, regex, label):
        """Test and report each item in the query set (presumed to be a CableTermination) for its name matching the
        compiled regular expression passed as regex.

        Arguments:
            queryset: A pre-filtered queryset of a CableTermination child.
            regex: A pre-compiled regular expression object to match the cable names against.
            label: A label to identify the cables with in log messages.
        """
        successes = 0
        for cable in queryset:
            if regex.match(cable.name):
                successes += 1
            else:
                self.log_failure(cable.device, "incorrectly named {} cable termination: {}".format(label, cable.name))

        self.log_success(None, "{} correctly named {} cable terminations".format(successes, label))

    def test_console_port_termination_names(self):
        """Proxy to _port_names_test with values for checking console ports."""
        self._port_names_test(
            ConsolePort.objects.exclude(device__status__in=EXCLUDE_STATUSES),
            re.compile(r"console\d|console-re\d|serial\d"),
            "console port",
        )

    def test_console_server_port_termination_names(self):
        """Proxy to _port_names_test with values for checking console server ports."""
        self._port_names_test(
            ConsoleServerPort.objects.exclude(device__status__in=EXCLUDE_STATUSES),
            re.compile(r"port\d+"),
            "console server port",
        )

    def test_power_port_termination_names(self):
        """Proxy to _port_names_test with values for checking power ports."""
        self._port_names_test(
            PowerPort.objects.exclude(device__status__in=EXCLUDE_STATUSES),
            re.compile(r"PSU\d|PEM \d|Power Supply \d"),
            "power port",
        )

    def test_power_outlet_termination_names(self):
        """Proxy to _port_names_test with values for checking power outlets."""
        self._port_names_test(
            PowerOutlet.objects.exclude(device__status__in=EXCLUDE_STATUSES), re.compile(r"\d+"), "power outlet"
        )

    def test_interface_termination_names(self):
        """Proxy to _port_names_test with values for checking interfaces."""
        self._port_names_test(
            Interface.objects.exclude(device__status__in=EXCLUDE_STATUSES),
            re.compile((r"|".join(INTERFACES_REGEXP))),
            "interface",
        )
