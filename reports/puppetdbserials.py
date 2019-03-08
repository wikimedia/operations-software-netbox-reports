"""
Report any device whose serial number does not match the serial number in PuppetDB
"""

import configparser
import requests

from dcim.constants import DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED
from dcim.models import Device
from extras.reports import Report

CONFIG_FILE = "/etc/netbox-reports.cfg"

INCLUDE_ROLES = ("server",)
EXCLUDE_DEV_TYPES = ("atlas-anchor-v1",)


class PuppetDBSerials(Report):
    description = __doc__

    def test_puppetdb_serials(self):
        # get puppetdb "serials" facts
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)

        puppetdb_url = config["puppetdb"]["url"]
        request = requests.get(puppetdb_url + "/v1/factcheck/serialnumber", verify=config["puppetdb"]["ca_cert"])
        if request.status_code != 200:
            self.log_failure(
                None, "cannot access puppetdb at {} - {} from microservice.".format(puppetdb_url, request.status_code)
            )
            return

        puppetdb_serials = {}
        for item in request.json():
            # item[0] is the certname from puppetdb, item[1] is the serial number string
            shortname = item[0].split(".")[0]
            puppetdb_serials[shortname] = item[1]

        hosts_set = set()
        success_count = 0
        for machine in (
            Device.objects.exclude(status__in=(DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED))
            .filter(device_role__slug__in=INCLUDE_ROLES)
            .exclude(device_type__slug__in=EXCLUDE_DEV_TYPES)
        ):
            hosts_set.add(machine.name)
            if machine.name not in puppetdb_serials:
                self.log_failure(machine, "machine does not exist in puppet")
            elif machine.serial != puppetdb_serials[machine.name] and puppetdb_serials[machine.name] is not None:
                self.log_failure(
                    machine,
                    "serial mismatch {}(netbox) != {}(puppetdb)".format(machine.serial, puppetdb_serials[machine.name]),
                )
            else:
                success_count += 1

        netbox_missing = set(puppetdb_serials.keys()) - hosts_set
        for missing in netbox_missing:
            self.log_failure(None, "{} MISSING from Netbox".format(missing))

        self.log("{} serials match.".format(success_count))
