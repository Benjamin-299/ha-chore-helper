from .chore import Chore
from .const import LOGGER
from . import helpers
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.util.dt import now as ha_now  # Import Home Assistant's timezone-aware `now`

class DailyChore(Chore):
    """Entity for a daily chore."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Read parameters specific for Daily Chore Frequency."""
        super().__init__(config_entry)
        config = config_entry.options
        self._period = config.get('period', 1)  # Default to 1 if not provided

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        if not await self._async_ready_for_update() or not self.hass.is_running:
            return

        if not self.entity_id:
            # Suppress warning if the entity is still initializing
            if not self.registry_entry:
                LOGGER.debug("Entity ID is not yet assigned for %s. Initialization in progress.", self._attr_name)
            else:
                LOGGER.warning("Entity ID is not assigned for %s. Skipping update.", self._attr_name)
            return

        LOGGER.debug("(%s) Calling update", self._attr_name)
        await self._async_load_due_dates()
        LOGGER.debug(
            "(%s) Dates loaded, firing a chore_helper_loaded event",
            self._attr_name,
        )
        event_data = {
            "entity_id": self.entity_id,
            "due_dates": helpers.dates_to_texts(self._due_dates),
        }
        self.hass.bus.async_fire("chore_helper_loaded", event_data)
        if not self._manual:
            self.update_state()

    def update_state(self) -> None:
        """Pick the first event from chore dates, update attributes."""
        if not self.entity_id:
            LOGGER.error("Entity ID is not assigned for %s. Skipping state update.", self._attr_name)
            return

        LOGGER.debug("(%s) Looking for next chore date", self._attr_name)
        self._last_updated = ha_now()  # Use timezone-aware `now`
        today = self._last_updated.date()
        self._next_due_date = self.get_next_due_date(self._calculate_start_date())
        if self._next_due_date is not None:
            LOGGER.debug(
                "(%s) next_due_date (%s), today (%s)",
                self._attr_name,
                self._next_due_date,
                today,
            )
            self._days = (self._next_due_date - today).days
            LOGGER.debug(
                "(%s) Found next chore date: %s, that is in %d days",
                self._attr_name,
                self._next_due_date,
                self._days,
            )
            self._attr_state = self._days
            if self._days > 1:
                self._attr_icon = self._icon_normal
            elif self._days < 0:
                self._attr_icon = self._icon_overdue
            elif self._days == 0:
                self._attr_icon = self._icon_today
            elif self._days == 1:
                self._attr_icon = self._icon_tomorrow
            self._overdue = self._days < 0
            self._overdue_days = 0 if self._days > -1 else abs(self._days)
        else:
            self._days = None
            self._attr_state = None
            self._attr_icon = self._icon_normal
            self._overdue = False
            self._overdue_days = None

        start_date = self._calculate_start_date()
        if self._add_dates is not None:
            self._add_dates = " ".join(
                [
                    x
                    for x in self._add_dates.split(" ")
                    if datetime.strptime(x, "%Y-%m-%d").date() >= start_date
                ]
            )
        if self._remove_dates is not None:
            self._remove_dates = " ".join(
                [
                    x
                    for x in self._remove_dates.split(" ")
                    if datetime.strptime(x, "%Y-%m-%d").date() >= start_date
                ]
            )
        if self._offset_dates is not None:
            self._offset_dates = " ".join(
                [
                    x
                    for x in self._offset_dates.split(" ")
                    if datetime.strptime(x.split(":")[0], "%Y-%m-%d").date()
                    >= start_date
                ]
            )
        self.async_write_ha_state()

    def _find_candidate_date(self, day1: date) -> date | None:
        """Calculate possible date, for every-n-days and after-n-days frequency."""
        schedule_start_date = self._calculate_schedule_start_date()
        day1 = self.calculate_day1(day1, schedule_start_date)

        if schedule_start_date is None or self._period is None:
            LOGGER.error(
                "(%s) Missing schedule_start_date or period configuration.",
                self._attr_name,
            )
            return None

        try:
            remainder = (day1 - schedule_start_date).days % self._period
            if remainder == 0:
                return day1
            offset = self._period - remainder
        except TypeError as error:
            raise ValueError(
                f"({self._attr_name}) Please configure start_date and period "
                "for every-n-days or after-n-days chore frequency."
            ) from error

        candidate_date = day1 + relativedelta(days=offset)
        LOGGER.debug(
            "(%s) Calculated candidate date: day1=%s, schedule_start_date=%s, candidate_date=%s",
            self._attr_name,
            day1,
            schedule_start_date,
            candidate_date,
        )
        return candidate_date

    async def complete(self, last_completed: datetime) -> None:
        """Mark the chore as completed and update the state."""
        self.last_completed = last_completed
        await self._async_load_due_dates()
        if not self._due_dates:
            LOGGER.warning(
                "(%s) No due dates calculated after completion. Check configuration.",
                self._attr_name,
            )
        self.update_state()
