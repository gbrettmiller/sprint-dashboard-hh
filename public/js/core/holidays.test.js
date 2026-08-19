import { describe, it, expect } from 'vitest';
import {
  getNthWeekdayOfMonth,
  getLastWeekdayOfMonth,
  getUSFederalHolidays,
  isWorkingDay,
  generateDateRange,
} from './holidays.js';

describe('getNthWeekdayOfMonth', () => {
  it('returns the 3rd Monday of January 2026 (MLK Day — Jan 19)', () => {
    const d = getNthWeekdayOfMonth(2026, 0, 1, 3);
    expect(d.getDate()).toBe(19);
    expect(d.getDay()).toBe(1); // Monday
  });
  it('returns the 1st Monday of September 2026 (Labor Day — Sep 7)', () => {
    const d = getNthWeekdayOfMonth(2026, 8, 1, 1);
    expect(d.getDate()).toBe(7);
  });
  it('returns the 4th Thursday of November 2026 (Thanksgiving — Nov 26)', () => {
    const d = getNthWeekdayOfMonth(2026, 10, 4, 4);
    expect(d.getDate()).toBe(26);
    expect(d.getDay()).toBe(4); // Thursday
  });
});

describe('getLastWeekdayOfMonth', () => {
  it('returns the last Monday of May 2026 (Memorial Day — May 25)', () => {
    const d = getLastWeekdayOfMonth(2026, 4, 1);
    expect(d.getDate()).toBe(25);
    expect(d.getDay()).toBe(1); // Monday
  });
  it('returns the last Monday of May 2025 (Memorial Day — May 26)', () => {
    const d = getLastWeekdayOfMonth(2025, 4, 1);
    expect(d.getDate()).toBe(26);
  });
});

describe('getUSFederalHolidays', () => {
  it('returns 11 holidays per year', () => {
    expect(getUSFederalHolidays(2026)).toHaveLength(11);
  });
  it('includes New Year\'s Day on Jan 1 when it falls on a weekday', () => {
    // Jan 1, 2026 is a Thursday
    const holidays = getUSFederalHolidays(2026);
    const newYears = holidays.find(h => h.getMonth() === 0 && h.getDate() === 1);
    expect(newYears).toBeDefined();
  });
  it('shifts a Sunday holiday to the following Monday', () => {
    // Jul 4, 2021 is a Sunday — observed Monday Jul 5
    const holidays = getUSFederalHolidays(2021);
    const july4Observed = holidays.find(h => h.getMonth() === 6);
    expect(july4Observed.getDate()).toBe(5);
    expect(july4Observed.getDay()).toBe(1); // Monday
  });
  it('shifts a Saturday holiday to the preceding Friday', () => {
    // Jul 4, 2020 is a Saturday — observed Friday Jul 3
    const holidays = getUSFederalHolidays(2020);
    const july4Observed = holidays.find(h => h.getMonth() === 6);
    expect(july4Observed.getDate()).toBe(3);
    expect(july4Observed.getDay()).toBe(5); // Friday
  });
  it('includes Juneteenth (Jun 19)', () => {
    const holidays = getUSFederalHolidays(2026);
    const juneteenth = holidays.find(h => h.getMonth() === 5);
    expect(juneteenth.getDate()).toBe(19);
  });
});

describe('isWorkingDay', () => {
  it('returns false for a Saturday', () => {
    expect(isWorkingDay('2026-04-18')).toBe(false);
  });
  it('returns false for a Sunday', () => {
    expect(isWorkingDay('2026-04-19')).toBe(false);
  });
  it('returns false for New Year\'s Day (Jan 1, 2026 — Thursday)', () => {
    expect(isWorkingDay('2026-01-01')).toBe(false);
  });
  it('returns false for Thanksgiving (Nov 26, 2026 — Thursday)', () => {
    expect(isWorkingDay('2026-11-26')).toBe(false);
  });
  it('returns false for an observed holiday (Jul 4, 2020 falls on Saturday — observed Jul 3)', () => {
    expect(isWorkingDay('2020-07-03')).toBe(false);
  });
  it('returns true for a regular Monday', () => {
    expect(isWorkingDay('2026-04-20')).toBe(true);
  });
  it('returns true for the day after a holiday', () => {
    expect(isWorkingDay('2026-01-02')).toBe(true);
  });
  it('returns true for Christmas Eve when Christmas falls on a Friday', () => {
    // Dec 25, 2026 is a Friday (actual holiday), Dec 24 is a regular Thursday
    expect(isWorkingDay('2026-12-24')).toBe(true);
  });
});

describe('generateDateRange', () => {
  it('returns all dates inclusive of start and end', () => {
    expect(generateDateRange('2026-04-20', '2026-04-24')).toEqual([
      '2026-04-20', '2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24',
    ]);
  });
  it('returns a single-element array when start equals end', () => {
    expect(generateDateRange('2026-04-20', '2026-04-20')).toEqual(['2026-04-20']);
  });
  it('returns YYYY-MM-DD formatted strings', () => {
    const range = generateDateRange('2026-04-20', '2026-04-22');
    range.forEach(d => expect(d).toMatch(/^\d{4}-\d{2}-\d{2}$/));
  });
  it('handles month boundaries correctly', () => {
    const range = generateDateRange('2026-04-29', '2026-05-02');
    expect(range).toEqual(['2026-04-29', '2026-04-30', '2026-05-01', '2026-05-02']);
  });
});
