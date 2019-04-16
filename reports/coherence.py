"""
Several integrity/coherence checks against the data.
"""

import datetime
import re

from dcim.constants import DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED, DEVICE_STATUS_INVENTORY
from dcim.models import Device
from extras.reports import Report

from django.db.models import Count


SITE_BLACKLIST = ("esams", "knams")
DEVICE_ROLE_BLACKLIST = ("cablemgmt", "storagebin", "optical-device")
ASSET_TAG_RE = re.compile(r"WMF\d{4}")
TICKET_RE = re.compile(r"RT #\d{2,}|T\d{5,}")


def _get_devices_query():
    return Device.objects.exclude(site__slug__in=SITE_BLACKLIST)


class Coherence(Report):
    description = __doc__

    def test_malformed_asset_tags(self):
        """Test for missing asset tags and incorrectly formatted asset tags."""
        success_count = 0
        for device in _get_devices_query():
            if device.asset_tag is None:
                self.log_failure(device, "missing asset tag")
            elif not ASSET_TAG_RE.fullmatch(device.asset_tag):
                self.log_failure(device, "malformed asset tag: {}".format(device.asset_tag))
            else:
                success_count += 1
        self.log_success(None, "{} correctly formatted asset tags".format(success_count))

    def test_purchase_date(self):
        """Test that each device has a purchase date."""
        success_count = 0
        for device in _get_devices_query():
            purchase_date = device.cf()["purchase_date"]
            if purchase_date is None:
                self.log_failure(device, "missing purchase date")
            elif purchase_date > datetime.datetime.today():
                self.log_failure(device, "purchase date is in the future")
            else:
                success_count += 1
        self.log_success(None, "{} present purchase dates".format(success_count))

    def test_duplicate_serials(self):
        """Test that all serial numbers are unique."""
        dups = (
            _get_devices_query()
            .values("serial")
            .exclude(status__in=(DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE))
            .exclude(serial="")
            .exclude(serial__isnull=True)
            .annotate(count=Count("pk"))
            .values_list("serial", flat=True)
            .order_by()
            .filter(count__gt=1)
        )

        if dups:
            for device in (
                _get_devices_query()
                .exclude(status__in=(DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE))
                .filter(serial__in=list(dups))
                .order_by("serial")
            ):
                self.log_failure(device, "duplicate serial: {}".format(device.serial))
        else:
            self.log_success(None, "No duplicate serials found")

    def test_serials(self):
        """Determine if all serials are non-null."""
        success_count = 0
        for device in _get_devices_query().exclude(status__in=(DEVICE_STATUS_INVENTORY, DEVICE_STATUS_OFFLINE)):
            if device.serial is None or device.serial == "":
                self.log_failure(device, "missing serial")
            else:
                success_count += 1
        self.log_success(None, "{} present serials".format(success_count))

    def test_ticket(self):
        """Determine if the procurement ticket matches the expected format."""
        success_count = 0
        for device in _get_devices_query():
            ticket = str(device.cf()["ticket"])
            if TICKET_RE.fullmatch(ticket):
                success_count += 1
            else:
                self.log_failure(device, "malformed procurement ticket: {}".format(ticket))
        self.log_success(None, "{} correctly formatted procurement tickets".format(success_count))

    def test_offline_rack(self):
        """Determine if offline boxes are (erroneously) assigned a rack."""
        warnings = []
        message = "rack defined for status {status} device: {site}-{rack}"
        for device in (
            _get_devices_query().filter(status__in=(DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED)).exclude(rack=None)
        ):
            if device.status == DEVICE_STATUS_PLANNED:
                warnings.append(device)
            else:
                self.log_failure(device, message.format(status="Offline", site=device.site.slug, rack=device.rack.name))
        for warning in warnings:
            self.log_warning(device, message.format(status="Planned", site=device.site.slug, rack=device.rack.name))

    def test_online_rack(self):
        """Determine if online boxes are (erroneously) lacking a rack assignment."""
        for device in (
            _get_devices_query().exclude(status__in=(DEVICE_STATUS_OFFLINE, DEVICE_STATUS_PLANNED)).filter(rack=None)
        ):
            self.log_failure(device, "no rack defined for status {} device".format(device.get_status_display()))
