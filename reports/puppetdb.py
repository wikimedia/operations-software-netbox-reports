"""
Report parity errors between PuppetDB and Netbox.
"""

import configparser
import requests

from dcim.constants import DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED
from dcim.models import Device
from extras.reports import Report
from virtualization.models import VirtualMachine

CONFIG_FILE = "/etc/netbox-reports.cfg"

# slugs for roles which we care about
INCLUDE_ROLES = ("server",)

# statuses that only warn for parity failures
EXCLUDE_STATUSES = (DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED)


class PuppetDB(Report):
    description = __doc__

    def __init__(self, *args, **kwargs):
        """Load the data from the endpoint as needed by the reports."""
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
        puppetdb_url = config["puppetdb"]["url"]

        request = requests.get(puppetdb_url + "/v1/facts/serialnumber", verify=config["puppetdb"]["ca_cert"])
        if request.status_code != 200:
            raise Exception(
                "Cannot connect to PuppetDB {} - {} {}".format(puppetdb_url, request.status_code, request.text)
            )

        self.puppetdb_serials = request.json()
        self.device_query = Device.objects.filter(device_role__slug__in=INCLUDE_ROLES, tenant__isnull=True)

        super().__init__(*args, **kwargs)

    def test_puppetdb_in_netbox(self):
        """Check that all PuppetDB physical hosts are in Netbox."""
        valid_netbox_hosts = self.device_query.exclude(status__in=EXCLUDE_STATUSES).values_list("name", flat=True)
        invalid_netbox_hosts = self.device_query.filter(status__in=EXCLUDE_STATUSES).values_list("name", flat=True)

        success = 0
        for host, serial in self.puppetdb_serials.items():
            if serial is None:
                # Virtual machines have a None fact for their serial
                continue

            if host in valid_netbox_hosts:
                success += 1
            elif host in invalid_netbox_hosts:
                invalid_host = Device.objects.get(name=host)
                self.log_failure(
                    invalid_host,
                    "PuppetDB physical host {host} has unexpected state {state} in Netbox".format(
                        host=host, state=invalid_host.get_status_display()
                    ),
                )
            else:
                self.log_failure(None, "PuppetDB physical host {} not in Netbox".format(host))

        self.log_info(None, "{} physical hosts that are in PuppetDB are also in Netbox".format(success))

    def test_netbox_in_puppetdb(self):
        """Check that all Netbox physical hosts are in PuppetDB."""
        hosts = self.device_query.exclude(status__in=EXCLUDE_STATUSES)
        success = 0

        for host in hosts:
            if host.name in self.puppetdb_serials:
                success += 1
            else:
                self.log_failure(host, "Physical host {} not in PuppetDB".format(host.name))

        self.log_info(None, "{} physical hosts that are in Netbox are also in PuppetDB".format(success))

    def test_puppetdb_serials(self):
        """Check that hosts that exist in both PuppetDB and Netbox have matching serial numbers."""
        hosts = self.device_query
        success = 0

        for host in hosts:
            if host.name not in self.puppetdb_serials:
                continue
            if host.serial != self.puppetdb_serials[host.name]:
                self.log_failure(
                    host,
                    "Serials do not match: netbox:{} != puppetdb:{}".format(
                        host.serial, self.puppetdb_serials[host.name]
                    ),
                )
            else:
                success += 1

        self.log_info(None, "{} physical hosts have matching serial numbers".format(success))

    def test_puppetdb_vms_in_netbox(self):
        """Check that all PuppetDB VMs are in Netbox VMs."""
        vms = list(VirtualMachine.objects.all().values_list("name", flat=True))
        puppetdb_vms = [host for host, serial in self.puppetdb_serials.items() if serial is None]
        success = 0

        for vm in puppetdb_vms:
            if vm not in vms:
                self.log_failure(None, "PuppetDB VM {} not in Netbox VMs".format(vm))
            else:
                success += 1

        self.log_info(None, "{} VMs that are in PuppetDB are also in Netbox VMs".format(success))

    def test_netbox_vms_in_puppetdb(self):
        """Check that all Netbox VMs are in PuppetDB VMs."""
        vms = VirtualMachine.objects.all()
        puppetdb_vms = [host for host, serial in self.puppetdb_serials.items() if serial is None]

        success = 0
        for vm in vms:
            if vm.name in puppetdb_vms:
                success += 1
            else:
                self.log_failure(vm, "Netbox VM {} not in PuppetDB VMs".format(vm.name))

        self.log_info(None, "{} VMs that are in Netbox are also in PuppetDB VMs".format(success))
