// CalendarMath — TypeScript parity port of backend/app/modules/time/calendar.py.
// The campaign clock is in *seconds*. Lets the UI format campaign dates and preview
// advancements without a round-trip. Kept in lockstep with Python via shared golden
// fixtures (vitest).

export interface CalendarDef {
  epoch_label?: string
  start_year?: number
  seconds_per_minute?: number
  minutes_per_hour: number
  hours_per_day: number
  weekdays: string[]
  months: { name: string; days: number; festival?: boolean }[]
  leap?: { every_years: number; month_index: number; extra_days: number }
  seasons?: { name: string; start_month_index: number }[]
  name?: string
}

export interface DateParts {
  total_days: number
  year: number
  month_index: number
  day_of_month: number
  day_of_year: number
  weekday_index: number
  hour: number
  minute: number
  second: number
  is_festival: boolean
  season: string | null
}

export interface FormattedDate {
  label: string
  weekday: string
  month: string
  day: number
  year: number
  time: string
  season: string | null
  seconds: number
}

const floorDiv = (a: number, b: number) => Math.floor(a / b)
const floorMod = (a: number, b: number) => ((a % b) + b) % b
const pad = (n: number) => String(n).padStart(2, '0')

export class CalendarMath {
  constructor(private cal: CalendarDef) {}

  get secondsPerMinute() {
    return this.cal.seconds_per_minute ?? 60
  }
  get minutesPerHour() {
    return this.cal.minutes_per_hour
  }
  get secondsPerHour() {
    return this.minutesPerHour * this.secondsPerMinute
  }
  get secondsPerDay() {
    return this.cal.hours_per_day * this.secondsPerHour
  }
  get startYear() {
    return this.cal.start_year ?? 1
  }

  private isLeap(year: number): boolean {
    const leap = this.cal.leap
    if (!leap || !leap.every_years) return false
    return floorMod(year, leap.every_years) === 0
  }

  private monthDays(monthIndex: number, year: number): number {
    let base = this.cal.months[monthIndex].days
    const leap = this.cal.leap
    if (leap && this.isLeap(year) && leap.month_index === monthIndex) base += leap.extra_days
    return base
  }

  private daysInYear(year: number): number {
    let total = 0
    for (let i = 0; i < this.cal.months.length; i++) total += this.monthDays(i, year)
    return total
  }

  toParts(seconds: number): DateParts {
    const spd = this.secondsPerDay
    const dayIndex = floorDiv(seconds, spd)
    const tod = seconds - dayIndex * spd
    const hour = Math.floor(tod / this.secondsPerHour)
    const rem = tod - hour * this.secondsPerHour
    const minute = Math.floor(rem / this.secondsPerMinute)
    const second = rem - minute * this.secondsPerMinute

    let year = this.startYear
    let remaining = dayIndex
    if (remaining >= 0) {
      while (remaining >= this.daysInYear(year)) {
        remaining -= this.daysInYear(year)
        year += 1
      }
    } else {
      while (remaining < 0) {
        year -= 1
        remaining += this.daysInYear(year)
      }
    }
    const dayOfYear = remaining

    let monthIndex = 0
    while (remaining >= this.monthDays(monthIndex, year)) {
      remaining -= this.monthDays(monthIndex, year)
      monthIndex += 1
    }

    return {
      total_days: dayIndex,
      year,
      month_index: monthIndex,
      day_of_month: remaining,
      day_of_year: dayOfYear,
      weekday_index: floorMod(dayIndex, this.cal.weekdays.length),
      hour,
      minute,
      second,
      is_festival: Boolean(this.cal.months[monthIndex].festival),
      season: this.seasonFor(monthIndex),
    }
  }

  private seasonFor(monthIndex: number): string | null {
    const seasons = this.cal.seasons
    if (!seasons || seasons.length === 0) return null
    let best: string | null = null
    let bestStart = -1
    let wrap: string | null = null
    let wrapStart = -1
    for (const s of seasons) {
      if (s.start_month_index <= monthIndex && s.start_month_index > bestStart) {
        best = s.name
        bestStart = s.start_month_index
      }
      if (s.start_month_index > wrapStart) {
        wrap = s.name
        wrapStart = s.start_month_index
      }
    }
    return best ?? wrap
  }

  format(seconds: number): FormattedDate {
    const p = this.toParts(seconds)
    const month = this.cal.months[p.month_index].name
    const day = p.day_of_month + 1
    const time = `${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}`
    const label = `${month} ${day}, ${p.year} ${this.cal.epoch_label ?? ''}`.trim()
    return {
      label,
      weekday: this.cal.weekdays[p.weekday_index],
      month,
      day,
      year: p.year,
      time,
      season: p.season,
      seconds,
    }
  }

  // Inverse of toParts: absolute date components → seconds since the epoch.
  // dayOfMonth is 0-based (like toParts). Years below startYear map to negative seconds.
  fromParts(
    year: number,
    monthIndex: number,
    dayOfMonth: number,
    hour = 0,
    minute = 0,
    second = 0,
  ): number {
    let days = 0
    if (year >= this.startYear) {
      for (let y = this.startYear; y < year; y++) days += this.daysInYear(y)
    } else {
      for (let y = year; y < this.startYear; y++) days -= this.daysInYear(y)
    }
    for (let m = 0; m < monthIndex; m++) days += this.monthDays(m, year)
    days += dayOfMonth
    return (
      days * this.secondsPerDay +
      hour * this.secondsPerHour +
      minute * this.secondsPerMinute +
      second
    )
  }

  toSeconds(days = 0, hours = 0, minutes = 0, seconds = 0): number {
    return (
      days * this.secondsPerDay +
      hours * this.secondsPerHour +
      minutes * this.secondsPerMinute +
      seconds
    )
  }
}
