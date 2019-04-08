"""
Report parity errors between PuppetDB and Netbox.
"""

import configparser
import requests

from dcim.constants import DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED, DEVICE_STATUS_CHOICES
from dcim.models import Device
from extras.reports import Report
from virtualization.models import VirtualMachine

CONFIG_FILE = "/etc/netbox-reports.cfg"

# slugs for roles which we care about
INCLUDE_ROLES = ("server",)

# slugs for tenants that we don't care about
EXCLUDE_TENANTS = ("fundraising-tech", "ripe")

# statuses that only warn for parity failures
SOFT_CHECK_STATUS = (DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED)


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
        self.device_query = Device.objects.filter(device_role__slug__in=INCLUDE_ROLES).exclude(
            tenant__slug__in=EXCLUDE_TENANTS
        )

        super().__init__(*args, **kwargs)

    def test_puppetdb_in_netbox(self):
        """Check the devices we expect to be in Netbox which are in PuppetDB are indeed in Netbox."""
        hostnames = list(self.device_query.values_list("name", flat=True))
        success = 0
        for host, serial in self.puppetdb_serials.items():
            if serial is None:
                # Virtual machines have a None fact for their serial
                continue
            if host not in hostnames:
                self.log_failure(None, "{} device missing from Netbox".format(host))
            else:
                success += 1

        self.log_info(None, "{} physical devices that are in PuppetDB are also in Netbox.".format(success))

    def test_netbox_in_puppetdb(self):
        """Check the devices we expect to be in PuppetDB which are in Netbox are indeed in PuppetDB."""
        hosts = self.device_query
        success = 0
        softfail = set()
        status_labels = {x[0]: x[1] for x in DEVICE_STATUS_CHOICES}

        for host in hosts:
            if host.name not in self.puppetdb_serials:
                if host.status in SOFT_CHECK_STATUS:
                    softfail.add(host)
                else:
                    self.log_failure(host, "device missing from PuppetDB")
            else:
                success += 1
        for host in softfail:
            self.log_warning(
                host, "(soft) device missing from PuppetDB (with status {})".format(status_labels[host.status])
            )

        self.log_info(None, "{} devices that are in Netbox are also in PuppetDB".format(success))

    def test_puppetdb_serials(self):
        """Check that devices that exist in both PuppetDB and Netbox have matching serial numbers."""
        hosts = self.device_query
        success = 0

        for host in hosts:
            if host.name not in self.puppetdb_serials:
                continue
            if host.serial != self.puppetdb_serials[host.name]:
                self.log_failure(
                    host,
                    "serials do not match: netbox:{} != puppetdb:{}".format(
                        host.serial, self.puppetdb_serials[host.name]
                    ),
                )
            else:
                success += 1

        self.log_info(None, "{} devices have matching serial numbers.".format(success))

    def test_puppetdb_vms_in_netbox(self):
        """Test if all None serials are Ganeti VMs in netbox."""
        hosts = list(VirtualMachine.objects.all().values_list("name", flat=True))
        puppetnulls = [host for host, serial in self.puppetdb_serials.items() if serial is None]
        success = 0

        for host in puppetnulls:
            if host not in hosts:
                self.log_failure(None, "{} not in Netbox VMs.".format(host))
            else:
                success += 1

        self.log_info(None, "{} VMs from PuppetDB in Netbox.".format(success))
