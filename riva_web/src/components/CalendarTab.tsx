import { useState, useEffect } from 'react';
import { Calendar as CalendarIcon, ExternalLink, Loader2, AlertCircle } from 'lucide-react';
import { type User } from 'firebase/auth';

interface CalendarTabProps {
  user: User;
  apiUrl: string;
}

export function CalendarTab({ user, apiUrl }: CalendarTabProps) {
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    checkStatus();
  }, [user]);

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
      const res = await fetch(`${apiUrl}/calendar/events?user_id=${user.uid}&days=7`);
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
        // Open Google OAuth in same window or new tab
        window.location.href = data.oauth_url;
      }
    } catch (err) {
      setError('Failed to initiate calendar connection');
    }
  };

  if (loading) {
    return (
      <div className="glass-panel text-center py-10" style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <Loader2 size={36} style={{ animation: 'spin-pulse 2s linear infinite', color: 'var(--primary)' }} />
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      <h2 style={{ fontSize: '1.5rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <CalendarIcon /> Productivity
      </h2>

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
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '1.1rem', color: 'var(--text-muted)' }}>Upcoming Events (Next 7 Days)</h3>
            <span style={{ fontSize: '0.8rem', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', padding: '0.25rem 0.75rem', borderRadius: '9999px' }}>Connected</span>
          </div>

          {events.length === 0 ? (
            <p style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '2rem' }}>No upcoming events.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {events.map((event, idx) => {
                const startDate = new Date(event.start_time || event.start?.dateTime || event.start?.date);
                const title = event.title || event.summary;
                return (
                  <div key={idx} style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '12px', borderLeft: '4px solid var(--primary)' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1.1rem' }}>{title}</h4>
                    <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                      {startDate.toLocaleDateString()} at {startDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
