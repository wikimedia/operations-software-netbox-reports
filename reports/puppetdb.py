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
        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_FILE)

        self.puppetdb_serials = self._get_puppetdb_fact("serialnumber")
        self.puppetdb_hosts = self._get_puppetdb_fact("is_virtual")
        self.device_query = Device.objects.filter(device_role__slug__in=INCLUDE_ROLES, tenant__isnull=True)

        super().__init__(*args, **kwargs)

    def _get_puppetdb_fact(self, fact):
        """Query the PuppetDB proxy for a specified fact.

        Arguments:
           fact (str): The fact name to query

        Returns:
            dict: Keyed by short hostname, with te value.

        Raises:
            Exception: on communication failure.

        """
        url = "/".join([self.config["puppetdb"]["url"], "/v1/facts", fact])
        response = requests.get(url, verify=self.config["puppetdb"]["ca_cert"])
        if response.status_code != 200:
            raise Exception("Cannot connect to PuppetDB {} - {} {}".format(url, response.status_code, response.text))

        return response.json()

    def test_puppetdb_in_netbox(self):
        """Check that all PuppetDB physical hosts are in Netbox."""
        valid_netbox_hosts = self.device_query.exclude(status__in=EXCLUDE_STATUSES).values_list("name", flat=True)
        invalid_netbox_hosts = self.device_query.filter(status__in=EXCLUDE_STATUSES).values_list("name", flat=True)

        success = 0
        for host, is_virtual in self.puppetdb_hosts.items():
            if is_virtual:
                continue

            if host in valid_netbox_hosts:
                success += 1
            elif host in invalid_netbox_hosts:
                invalid_host = Device.objects.get(name=host)
                self.log_failure(
                    invalid_host,
                    "unexpected state for physical host: {} in netbox".format(invalid_host.get_status_display()),
                )
            else:
                self.log_failure(None, "expected host missing from Netbox: {}".format(host))

        self.log_success(None, "{} physical hosts that are in PuppetDB are also in Netbox".format(success))

    def test_netbox_in_puppetdb(self):
        """Check that all Netbox physical hosts are in PuppetDB."""
        hosts = self.device_query.exclude(status__in=EXCLUDE_STATUSES)
        success = 0

        for host in hosts:
            if host.name not in self.puppetdb_hosts:
                self.log_failure(
                    host, "missing physical host in PuppetDB: state {} in Netbox".format(host.get_status_display())
                )
            elif self.puppetdb_hosts[host.name]:
                self.log_failure(host, "expected physical host marked as virtual in PuppetDB")
            else:
                success += 1

        self.log_success(None, "{} physical hosts that are in Netbox are also in PuppetDB".format(success))

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
                    "mismatched serials: {} (netbox) != {} (puppetdb)".format(
                        host.serial, self.puppetdb_serials[host.name]
                    ),
                )
            else:
                success += 1

        self.log_success(None, "{} physical hosts have matching serial numbers".format(success))

    def test_puppetdb_vms_in_netbox(self):
        """Check that all PuppetDB VMs are in Netbox VMs."""
        vms = list(VirtualMachine.objects.exclude(status=DEVICE_STATUS_OFFLINE).values_list("name", flat=True))
        success = 0

        for host, is_virtual in self.puppetdb_hosts.items():
            if not is_virtual:
                continue

            if host not in vms:
                self.log_failure(None, "missing VM from Netbox: {} ".format(host))
            else:
                success += 1

        self.log_success(None, "{} VMs that are in PuppetDB are also in Netbox VMs".format(success))

    def test_netbox_vms_in_puppetdb(self):
        """Check that all Netbox VMs are in PuppetDB VMs."""

        vms = VirtualMachine.objects.exclude(status=DEVICE_STATUS_OFFLINE)

        success = 0
        for vm in vms:
            if vm.name not in self.puppetdb_hosts:
                self.log_failure(vm, "missing VM from PuppetDB")
            elif not self.puppetdb_hosts[vm.name]:
                self.log_failure(vm, "expected VM marked as Physical in PuppetDB")
            else:
                success += 1

        self.log_success(None, "{} VMs that are in Netbox are also in PuppetDB VMs".format(success))
