// Holiday and working-day calculations — pure functions, no DOM access.

export function getNthWeekdayOfMonth(year, month, weekday, n) {
  const first = new Date(year, month, 1);
  const firstWeekday = first.getDay();
  const day = 1 + ((weekday - firstWeekday + 7) % 7) + (n - 1) * 7;
  return new Date(year, month, day);
}

export function getLastWeekdayOfMonth(year, month, weekday) {
  const last = new Date(year, month + 1, 0);
  const lastDay = last.getDate();
  const lastWeekday = last.getDay();
  const diff = (lastWeekday - weekday + 7) % 7;
  return new Date(year, month, lastDay - diff);
}

export function getUSFederalHolidays(year) {
  const holidays = [];

  holidays.push(new Date(year, 0, 1));                         // New Year's Day
  holidays.push(getNthWeekdayOfMonth(year, 0, 1, 3));          // MLK Day
  holidays.push(getNthWeekdayOfMonth(year, 1, 1, 3));          // Presidents' Day
  holidays.push(getLastWeekdayOfMonth(year, 4, 1));            // Memorial Day
  holidays.push(new Date(year, 5, 19));                        // Juneteenth
  holidays.push(new Date(year, 6, 4));                         // Independence Day
  holidays.push(getNthWeekdayOfMonth(year, 8, 1, 1));          // Labor Day
  holidays.push(getNthWeekdayOfMonth(year, 9, 1, 2));          // Columbus Day
  holidays.push(new Date(year, 10, 11));                       // Veterans Day
  holidays.push(getNthWeekdayOfMonth(year, 10, 4, 4));         // Thanksgiving
  holidays.push(new Date(year, 11, 25));                       // Christmas

  // Observed dates: Sunday → Monday, Saturday → Friday
  return holidays.map(h => {
    const day = h.getDay();
    if (day === 0) return new Date(h.getTime() + 86400000);
    if (day === 6) return new Date(h.getTime() - 86400000);
    return h;
  });
}

export function isWorkingDay(dateStr) {
  const date = new Date(dateStr + 'T00:00:00');
  const day = date.getDay();
  if (day === 0 || day === 6) return false;

  const year = date.getFullYear();
  const holidays = getUSFederalHolidays(year);
  const dateTime = date.getTime();

  return !holidays.some(h => {
    const hTime = new Date(h.getFullYear(), h.getMonth(), h.getDate()).getTime();
    return hTime === dateTime;
  });
}

export function generateDateRange(startDate, endDate) {
  const dates = [];
  const start = new Date(startDate + 'T00:00:00');
  const end = new Date(endDate + 'T00:00:00');
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    dates.push(d.toISOString().slice(0, 10));
  }
  return dates;
}
