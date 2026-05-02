import { useState, useEffect, useMemo } from 'react';
import { Calendar as CalendarIcon, ExternalLink, Loader2, AlertCircle, ChevronLeft, ChevronRight, Clock, MapPin } from 'lucide-react';
import { type User } from 'firebase/auth';

interface CalendarEvent {
  id?: string;
  title?: string;
  summary?: string;
  start_time?: string;
  end_time?: string;
  start?: { dateTime?: string; date?: string };
  end?: { dateTime?: string; date?: string };
  description?: string;
  location?: string;
}

interface CalendarTabProps {
  user: User;
  apiUrl: string;
}

// Predefined event colors for visual variety
const EVENT_COLORS = [
  { bg: 'rgba(99, 102, 241, 0.18)', border: '#6366f1', text: '#a5b4fc' },
  { bg: 'rgba(236, 72, 153, 0.18)', border: '#ec4899', text: '#f9a8d4' },
  { bg: 'rgba(16, 185, 129, 0.18)', border: '#10b981', text: '#6ee7b7' },
  { bg: 'rgba(245, 158, 11, 0.18)', border: '#f59e0b', text: '#fcd34d' },
  { bg: 'rgba(139, 92, 246, 0.18)', border: '#8b5cf6', text: '#c4b5fd' },
  { bg: 'rgba(59, 130, 246, 0.18)', border: '#3b82f6', text: '#93c5fd' },
  { bg: 'rgba(244, 63, 94, 0.18)', border: '#f43f5e', text: '#fda4af' },
  { bg: 'rgba(20, 184, 166, 0.18)', border: '#14b8a6', text: '#5eead4' },
];

const HOURS = Array.from({ length: 24 }, (_, i) => i);

function getEventDateTime(event: CalendarEvent, which: 'start' | 'end'): Date | null {
  const raw = which === 'start'
    ? (event.start_time || event.start?.dateTime || event.start?.date)
    : (event.end_time || event.end?.dateTime || event.end?.date);
  if (!raw) return null;
  return new Date(raw);
}

function formatHour(hour: number): string {
  if (hour === 0) return '12 AM';
  if (hour === 12) return '12 PM';
  if (hour < 12) return `${hour} AM`;
  return `${hour - 12} PM`;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
}

function isSameDay(d1: Date, d2: Date): boolean {
  return d1.getFullYear() === d2.getFullYear()
    && d1.getMonth() === d2.getMonth()
    && d1.getDate() === d2.getDate();
}

export function CalendarTab({ user, apiUrl }: CalendarTabProps) {
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDate, setSelectedDate] = useState(new Date());

  useEffect(() => {
    checkStatus();
  }, [user]);

  useEffect(() => {
    if (isConnected) {
      fetchEvents();
    }
  }, [selectedDate, isConnected]);

  const checkStatus = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${apiUrl}/calendar/status?user_id=${user.uid}`);
      const data = await res.json();
      setIsConnected(data.connected);
      if (data.connected) {
        fetchEvents();
      } else {
        setLoading(false);
      }
    } catch (err) {
      setError('Failed to check calendar status');
      setLoading(false);
    }
  };

  const fetchEvents = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${apiUrl}/calendar/events?user_id=${user.uid}&days=14`);
      const data = await res.json();
      setEvents(data.events || []);
    } catch (err) {
      setError('Failed to fetch events');
    } finally {
      setLoading(false);
    }
  };

  const connectCalendar = async () => {
    try {
      const res = await fetch(`${apiUrl}/calendar/oauth/url?user_id=${user.uid}`);
      const data = await res.json();
      if (data.oauth_url) {
        window.location.href = data.oauth_url;
      }
    } catch (err) {
      setError('Failed to initiate calendar connection');
    }
  };

  // Filter events for selected day
  const dayEvents = useMemo(() => {
    return events
      .map((event, idx) => {
        const start = getEventDateTime(event, 'start');
        const end = getEventDateTime(event, 'end');
        if (!start) return null;
        if (!isSameDay(start, selectedDate)) return null;
        return { ...event, _start: start, _end: end, _colorIdx: idx % EVENT_COLORS.length };
      })
      .filter(Boolean) as (CalendarEvent & { _start: Date; _end: Date | null; _colorIdx: number })[];
  }, [events, selectedDate]);

  // Week navigation
  const weekDates = useMemo(() => {
    const start = new Date(selectedDate);
    start.setDate(start.getDate() - start.getDay()); // Sunday
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(start);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [selectedDate]);

  const goToPrevWeek = () => {
    setSelectedDate(prev => {
      const d = new Date(prev);
      d.setDate(d.getDate() - 7);
      return d;
    });
  };

  const goToNextWeek = () => {
    setSelectedDate(prev => {
      const d = new Date(prev);
      d.setDate(d.getDate() + 7);
      return d;
    });
  };

  const goToToday = () => setSelectedDate(new Date());

  const today = new Date();
  const nowHour = today.getHours() + today.getMinutes() / 60;

  if (loading && isConnected === null) {
    return (
      <div className="glass-panel text-center py-10" style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <Loader2 size={36} style={{ animation: 'spin-pulse 2s linear infinite', color: 'var(--primary)' }} />
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
          <CalendarIcon /> Calendar
        </h2>
        {isConnected && (
          <span className="cal-connected-badge">● Connected</span>
        )}
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={20} />
          {error}
        </div>
      )}

      {!isConnected ? (
        <div style={{ textAlign: 'center', padding: '3rem 0', flex: 1 }}>
          <div style={{ background: 'rgba(99, 102, 241, 0.1)', width: '80px', height: '80px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1.5rem', color: 'var(--primary)' }}>
            <CalendarIcon size={40} />
          </div>
          <h3 style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>Connect Google Calendar</h3>
          <p style={{ color: 'var(--text-muted)', marginBottom: '2rem', maxWidth: '400px', margin: '0 auto 2rem' }}>
            RIVA can manage your schedule, set reminders, and find available time slots if you connect your Google Calendar.
          </p>
          <button className="btn btn-primary" onClick={connectCalendar} style={{ margin: '0 auto' }}>
            Connect Calendar <ExternalLink size={18} />
          </button>
        </div>
      ) : (
        <>
          {/* Week Strip */}
          <div className="cal-week-strip">
            <button className="cal-nav-btn" onClick={goToPrevWeek}><ChevronLeft size={20} /></button>

            <div className="cal-week-days">
              {weekDates.map(d => {
                const isSelected = isSameDay(d, selectedDate);
                const isToday = isSameDay(d, today);
                const dayEventCount = events.filter(e => {
                  const s = getEventDateTime(e, 'start');
                  return s && isSameDay(s, d);
                }).length;

                return (
                  <button
                    key={d.toISOString()}
                    className={`cal-day-btn ${isSelected ? 'selected' : ''} ${isToday ? 'today' : ''}`}
                    onClick={() => setSelectedDate(new Date(d))}
                  >
                    <span className="cal-day-name">{d.toLocaleDateString('en-US', { weekday: 'short' })}</span>
                    <span className="cal-day-num">{d.getDate()}</span>
                    {dayEventCount > 0 && <span className="cal-day-dot" />}
                  </button>
                );
              })}
            </div>

            <button className="cal-nav-btn" onClick={goToNextWeek}><ChevronRight size={20} /></button>
          </div>

          {/* Month & Today button */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '0.75rem 0' }}>
            <span style={{ fontSize: '1.05rem', fontWeight: 600 }}>
              {selectedDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
            </span>
            {!isSameDay(selectedDate, today) && (
              <button className="btn" onClick={goToToday} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                Today
              </button>
            )}
          </div>

          {/* Day Timeline */}
          <div className="cal-timeline-container">
            <div className="cal-timeline">
              {HOURS.map(hour => (
                <div key={hour} className="cal-hour-row">
                  <div className="cal-hour-label">{formatHour(hour)}</div>
                  <div className="cal-hour-slot" />
                </div>
              ))}

              {/* Current time indicator */}
              {isSameDay(selectedDate, today) && (
                <div
                  className="cal-now-line"
                  style={{ top: `${(nowHour / 24) * 100}%` }}
                >
                  <div className="cal-now-dot" />
                  <div className="cal-now-rule" />
                </div>
              )}

              {/* Event blocks */}
              {dayEvents.map((event, idx) => {
                const startH = event._start.getHours() + event._start.getMinutes() / 60;
                const endH = event._end
                  ? event._end.getHours() + event._end.getMinutes() / 60
                  : startH + 1;
                const topPct = (startH / 24) * 100;
                const heightPct = Math.max(((endH - startH) / 24) * 100, 2.5);
                const color = EVENT_COLORS[event._colorIdx];
                const title = event.title || event.summary || 'Untitled';

                return (
                  <div
                    key={idx}
                    className="cal-event-block"
                    style={{
                      top: `${topPct}%`,
                      height: `${heightPct}%`,
                      background: color.bg,
                      borderLeft: `3px solid ${color.border}`,
                    }}
                  >
                    <div className="cal-event-title" style={{ color: color.text }}>
                      {title}
                    </div>
                    <div className="cal-event-time">
                      <Clock size={11} />
                      {formatTime(event._start)}
                      {event._end && ` – ${formatTime(event._end)}`}
                    </div>
                    {event.location && (
                      <div className="cal-event-location">
                        <MapPin size={11} /> {event.location}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Empty state for day */}
          {!loading && dayEvents.length === 0 && (
            <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-muted)', fontSize: '0.95rem' }}>
              No events scheduled for this day.
            </div>
          )}
        </>
      )}
    </div>
  );
}
