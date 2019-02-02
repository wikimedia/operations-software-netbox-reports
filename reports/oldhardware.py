"""
Report any hardware older than 5 years.
"""

import datetime

from dcim.constants import DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE
from dcim.models import Device
from extras.reports import Report


class OldHardwareReport(Report):
    description = __doc__

    def test_hardware_age(self):
        today = datetime.datetime.today()
        success_count = 0

        for machine in Device.objects.exclude(status__in=(DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE)):
            cfs = machine.cf()
            purchase_date = cfs["purchase_date"]
            if purchase_date is None:
                self.log_failure(machine, "null purchase date.")
                continue

            age = (today.date() - purchase_date).days / 365.25
            if age > 5:
                self.log_failure(
                    machine, "older than 5 years (purchase date: {} age: {:02.1f}y)".format(purchase_date, age)
                )
            elif age > 4.5:
                self.log_warning(
                    machine, "older than 4.5 years (purchase date: {} age: {:02.1f}y)".format(purchase_date, age)
                )
            else:
                success_count += 1

        self.log("{} good hardware ages.".format(success_count))
