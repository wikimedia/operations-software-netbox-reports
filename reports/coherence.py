"""
Several integrity/coherence checks against the data.
"""

import re

from django.db.models import Count

from dcim.models import Device
from extras.reports import Report


class Coherence(Report):
    description = __doc__
    asset_tag_re = re.compile(r"WMF\d{4}")
    ticket_re = [re.compile(r"RT #\d+"), re.compile(r"T\d+")]

    def test_asset_tags(self):
        """Test for missing asset tags, asset tag dupes and incorrectly formatted asset tags."""
        success_count = 0
        for machine in Device.objects.all():
            if machine.asset_tag is None:
                self.log_failure(machine, "missing asset tag")
            elif not self.asset_tag_re.fullmatch(machine.asset_tag):
                self.log_failure(machine, "incorrectly formatted asset tag {}".format(machine.asset_tag))
            else:
                success_count += 1
        self.log("{} ok asset tags.".format(success_count))

    def test_purchase_date(self):
        """Test that each machine has a purchase date."""
        success_count = 0
        for machine in Device.objects.all():
            purchase_date = machine.cf()["purchase_date"]
            if purchase_date is None:
                self.log_failure(machine, "missing purchase date.")
            else:
                success_count += 1
        self.log("{} ok purchase dates.".format(success_count))

    def test_duplicate_serials(self):
        """Test that all serial numbers are unique."""
        dups = (
            Device.objects.values("serial")
            .exclude(serial="")
            .exclude(serial__isnull=True)
            .annotate(count=Count("pk"))
            .values("serial")
            .order_by()
            .filter(count__gt=1)
        )
        if not dups:
            self.log("No duplicate serials found.")
            return
        for machine in Device.objects.filter(serial__in=[dup for dup in dups]).order_by("serial"):
            self.log_failure(machine, "duplicate serial found: {}".format(machine.serial))

    def test_serials(self):
        """Determine if all serials are non-null."""
        success_count = 0
        for machine in Device.objects.all():
            if machine.serial is None or machine.serial == "":
                self.log_failure(machine, "serial missing")
            else:
                success_count += 1
        self.log("{} ok serials.".format(success_count))

    def test_ticket(self):
        success_count = 0
        for machine in Device.objects.all():
            ticket = str(machine.cf()["ticket"])
            good_result = False
            for tre in self.ticket_re:
                if tre.fullmatch(ticket):
                    good_result = True
            if good_result:
                success_count += 1
            else:
                self.log_failure(machine, "bad procurement ticket: {}".format(ticket))
        self.log("{} ok tickets.".format(success_count))
