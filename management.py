"""
Check certain kinds of devices for the presence of a console port.
"""

from dcim.constants import (
    CONNECTION_STATUS_CONNECTED,
    DEVICE_STATUS_INVENTORY,
    DEVICE_STATUS_OFFLINE,
    DEVICE_STATUS_PLANNED,
)
from dcim.models import Device, DeviceRole, Site
from extras.reports import Report

# These are the device type slugs we care about.
# Currently we alert on Core Routers and Core/Access Switch
DEVICEROLES = ("cr", "asw", "mr", "pfw")

# These are points of presence slugs that we ignore for the purposes of this report.
EXCLUDED_SITES = ("eqord", "eqdfw", "knams")


class ManagementConsole(Report):
    description = __doc__

    def test_management_console(self):
        roles = DeviceRole.objects.filter(slug__in=DEVICEROLES).values_list("pk", flat=True)
        sites = Site.objects.exclude(slug__in=EXCLUDED_SITES).values_list("pk", flat=True)
        for machine in (
            Device.objects.exclude(status__in=(DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED))
            .filter(device_role__in=roles)
            .filter(site__in=sites)
        ):
            ports = machine.console_ports.all()

            if not ports:
                self.log_failure(machine, "no console ports present")
                continue

            for port in ports:
                if port.connection_status == CONNECTION_STATUS_CONNECTED and port.cs_port not in (None, ""):
                    self.log_success(machine, "at least one console connection is present")
                    break
            else:
                self.log_failure(machine, "only unconnected console ports are present")
