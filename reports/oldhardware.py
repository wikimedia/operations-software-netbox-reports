"""
Report any hardware older than 5 years.
"""

import datetime


from dcim.constants import DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE
from dcim.models import Device
from extras.models import CustomFieldValue
from extras.reports import Report


EXCLUDE_ROLES = ("cablemgmt", "storagebin")


class OldHardwareReport(Report):
    description = __doc__

    def test_hardware_age(self):
        """Check hardware ages

        Determine the age of hardware, and alert if it is older than 5 years, or warn if it is older
        than 4.5 years.

        """
        today = datetime.datetime.today()
        success_count = 0
        # We have to sort the devices ourselves since the custom fields is not available from the Django ORM in any
        # normal way.
        results = []
        devquery = Device.objects.exclude(status__in=(DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE)).exclude(
            device_role__slug__in=EXCLUDE_ROLES
        )

        cf_ids = devquery.values_list('custom_field_values__pk', flat=True)
        cfs = {
            cf.pk: cf.value
            for cf in CustomFieldValue.objects.prefetch_related('field')
            .filter(field__name='purchase_date')
            .filter(pk__in=cf_ids)
        }

        for device in devquery:
            try:
                purchase_date = cfs[device.pk]
            except KeyError:
                self.log_failure(device, "null purchase date.")
                continue

            age = round(
                (today.date() - purchase_date).days / 365.25, 1
            )  # pre-round so the cut off will be consistent with display
            if age < 4.5:  # 4.5 years is the cut off between almost old and not old
                success_count += 1
            else:
                results.append((age, purchase_date, device))

        for res in sorted(results, reverse=True, key=lambda item: item[0]):
            if res[0] >= 5:
                self.log_failure(res[2], "old device with purchase date: {} (age: {:02.1f}y)".format(res[1], res[0]))
            else:
                self.log_warning(
                    res[2], "almost old device with purchase date: {} (age: {:02.1f}y)".format(res[1], res[0])
                )

        self.log_success(None, "{} devices with ages less than 4.5 years.".format(success_count))
