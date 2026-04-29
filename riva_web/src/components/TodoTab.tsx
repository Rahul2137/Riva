import { useState, useEffect, useCallback } from 'react';
import { CheckSquare, Plus, Calendar, AlertTriangle, Loader2, Check, Trash2, Clock, ChevronDown, ChevronRight, Eye, EyeOff, RotateCcw } from 'lucide-react';
import { type User } from 'firebase/auth';

interface Todo {
  _id: string;
  title: string;
  description: string;
  due_date: string;
  due_time: string | null;
  priority: 'high' | 'medium' | 'low';
  category: string;
  status: 'pending' | 'completed';
}

interface Stats {
  pending: number;
  completed_today: number;
  overdue: number;
}

interface TodoTabProps {
  user: User;
  apiUrl: string;
}

const PRIORITY_CONFIG = {
  high:   { color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)', label: '🔴 High', border: 'rgba(239, 68, 68, 0.4)' },
  medium: { color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)', label: '🟡 Medium', border: 'rgba(245, 158, 11, 0.4)' },
  low:    { color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)', label: '🟢 Low', border: 'rgba(16, 185, 129, 0.4)' },
};

const CATEGORY_ICONS: Record<string, string> = {
  work: '💼', personal: '🏠', health: '💪', study: '📚', other: '📌',
};

export function TodoTab({ user, apiUrl }: TodoTabProps) {
  const [groupedTodos, setGroupedTodos] = useState<Record<string, Todo[]>>({});
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [showCompleted, setShowCompleted] = useState(false);
  const [expandedDates, setExpandedDates] = useState<Set<string>>(new Set());

  // Add form
  const [newTitle, setNewTitle] = useState('');
  const [newDate, setNewDate] = useState(new Date().toISOString().split('T')[0]);
  const [newPriority, setNewPriority] = useState<'high' | 'medium' | 'low'>('medium');
  const [newCategory, setNewCategory] = useState('other');
  const [addLoading, setAddLoading] = useState(false);

  const fetchTodos = useCallback(async () => {
    try {
      setLoading(true);
      // When showCompleted, don't pass status filter so we get all; otherwise only pending
      const statusParam = showCompleted ? '' : '&status=pending';
      const res = await fetch(`${apiUrl}/todos?user_id=${user.uid}&days=14&grouped=true${statusParam}`);
      const data = await res.json();
      setGroupedTodos(data.todos || {});
      // Auto-expand all dates
      setExpandedDates(new Set(Object.keys(data.todos || {})));
    } catch (err) {
      console.error('Failed to fetch todos', err);
    } finally {
      setLoading(false);
    }
  }, [apiUrl, user.uid, showCompleted]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${apiUrl}/todos/stats?user_id=${user.uid}`);
      const data = await res.json();
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch stats', err);
    }
  }, [apiUrl, user.uid]);

  useEffect(() => {
    fetchTodos();
    fetchStats();
  }, [fetchTodos, fetchStats]);

  const addTodo = async () => {
    if (!newTitle.trim()) return;
    setAddLoading(true);
    try {
      await fetch(`${apiUrl}/todos?user_id=${user.uid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTitle.trim(),
          due_date: newDate,
          priority: newPriority,
          category: newCategory,
        }),
      });
      setNewTitle('');
      setShowAdd(false);
      fetchTodos();
      fetchStats();
    } catch (err) {
      console.error('Failed to add todo', err);
    } finally {
      setAddLoading(false);
    }
  };

  const completeTodo = async (todoId: string) => {
    try {
      await fetch(`${apiUrl}/todos/${todoId}/complete?user_id=${user.uid}`, { method: 'POST' });
      fetchTodos();
      fetchStats();
    } catch (err) {
      console.error('Failed to complete todo', err);
    }
  };

  const uncompleteTodo = async (todoId: string) => {
    try {
      await fetch(`${apiUrl}/todos/${todoId}/uncomplete?user_id=${user.uid}`, { method: 'POST' });
      fetchTodos();
      fetchStats();
    } catch (err) {
      console.error('Failed to uncomplete todo', err);
    }
  };

  const deleteTodo = async (todoId: string) => {
    try {
      await fetch(`${apiUrl}/todos/${todoId}?user_id=${user.uid}`, { method: 'DELETE' });
      fetchTodos();
      fetchStats();
    } catch (err) {
      console.error('Failed to delete todo', err);
    }
  };

  const toggleDate = (date: string) => {
    setExpandedDates(prev => {
      const next = new Set(prev);
      next.has(date) ? next.delete(date) : next.add(date);
      return next;
    });
  };

  const formatDate = (dateStr: string) => {
    const today = new Date().toISOString().split('T')[0];
    const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];
    const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];

    if (dateStr === today) return 'Today';
    if (dateStr === tomorrow) return 'Tomorrow';
    if (dateStr === yesterday) return 'Yesterday';
    return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-IN', {
      weekday: 'long', month: 'short', day: 'numeric',
    });
  };

  const isOverdue = (dateStr: string) => {
    return dateStr < new Date().toISOString().split('T')[0];
  };

  const sortedDates = Object.keys(groupedTodos).sort();

  if (loading) {
    return (
      <div className="glass-panel text-center py-10" style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <Loader2 size={36} style={{ animation: 'spin-pulse 2s linear infinite', color: 'var(--primary)' }} />
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
          <CheckSquare /> Tasks
        </h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            className={`btn ${showCompleted ? 'btn-primary' : ''}`}
            onClick={() => setShowCompleted(!showCompleted)}
            style={{ padding: '0.5rem 0.85rem', fontSize: '0.85rem' }}
            title={showCompleted ? 'Hide completed' : 'Show completed'}
          >
            {showCompleted ? <EyeOff size={16} /> : <Eye size={16} />}
            {showCompleted ? 'Hide Done' : 'Show Done'}
          </button>
          <button
            className="btn btn-primary"
            onClick={() => setShowAdd(!showAdd)}
            style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
          >
            <Plus size={18} /> Add Task
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      {stats && (
        <div className="todo-stats-bar">
          <div className="todo-stat">
            <span className="todo-stat-value">{stats.pending}</span>
            <span className="todo-stat-label">Pending</span>
          </div>
          <div className="todo-stat-divider" />
          <div className="todo-stat">
            <span className="todo-stat-value" style={{ color: '#10b981' }}>{stats.completed_today}</span>
            <span className="todo-stat-label">Done Today</span>
          </div>
          <div className="todo-stat-divider" />
          <div className="todo-stat">
            <span className="todo-stat-value" style={{ color: stats.overdue > 0 ? '#ef4444' : 'var(--text-muted)' }}>
              {stats.overdue}
            </span>
            <span className="todo-stat-label">Overdue</span>
          </div>
        </div>
      )}

      {/* Add Form */}
      {showAdd && (
        <div className="todo-add-form">
          <input
            type="text"
            placeholder="What needs to be done?"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addTodo()}
            className="todo-input"
            autoFocus
          />
          <div className="todo-form-row">
            <div className="todo-form-field">
              <label><Calendar size={14} /> Due Date</label>
              <input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} className="todo-date-input" />
            </div>
            <div className="todo-form-field">
              <label>Priority</label>
              <select value={newPriority} onChange={(e) => setNewPriority(e.target.value as any)} className="todo-select">
                <option value="high">🔴 High</option>
                <option value="medium">🟡 Medium</option>
                <option value="low">🟢 Low</option>
              </select>
            </div>
            <div className="todo-form-field">
              <label>Category</label>
              <select value={newCategory} onChange={(e) => setNewCategory(e.target.value)} className="todo-select">
                <option value="work">💼 Work</option>
                <option value="personal">🏠 Personal</option>
                <option value="health">💪 Health</option>
                <option value="study">📚 Study</option>
                <option value="other">📌 Other</option>
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
            <button className="btn" onClick={() => setShowAdd(false)} style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              onClick={addTodo}
              disabled={!newTitle.trim() || addLoading}
              style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}
            >
              {addLoading ? <Loader2 size={16} style={{ animation: 'spin-pulse 1s linear infinite' }} /> : 'Add'}
            </button>
          </div>
        </div>
      )}

      {/* Task List grouped by date */}
      <div style={{ flex: 1, overflowY: 'auto', marginTop: '0.5rem' }}>
        {sortedDates.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-muted)' }}>
            <CheckSquare size={48} style={{ marginBottom: '1rem', opacity: 0.3 }} />
            <p style={{ fontSize: '1.1rem' }}>
              {showCompleted ? 'No tasks in this period.' : 'No pending tasks. You\'re all caught up! 🎉'}
            </p>
          </div>
        ) : (
          sortedDates.map(date => {
            const todos = groupedTodos[date];
            const isExpanded = expandedDates.has(date);
            const overdue = isOverdue(date);
            const pendingCount = todos.filter(t => t.status === 'pending').length;
            const doneCount = todos.filter(t => t.status === 'completed').length;

            return (
              <div key={date} className="todo-date-group">
                <button
                  className="todo-date-header"
                  onClick={() => toggleDate(date)}
                  style={{ borderLeft: overdue ? '3px solid #ef4444' : '3px solid var(--primary)' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    <span className="todo-date-label">
                      {overdue && <AlertTriangle size={14} style={{ color: '#ef4444', marginRight: '0.25rem' }} />}
                      {formatDate(date)}
                    </span>
                  </div>
                  <span className="todo-date-count">
                    {pendingCount > 0 && `${pendingCount} pending`}
                    {pendingCount > 0 && doneCount > 0 && ' · '}
                    {doneCount > 0 && <span style={{ color: '#10b981' }}>{doneCount} done</span>}
                  </span>
                </button>

                {isExpanded && (
                  <div className="todo-items">
                    {todos.map(todo => {
                      const pConfig = PRIORITY_CONFIG[todo.priority] || PRIORITY_CONFIG.medium;
                      const isDone = todo.status === 'completed';
                      return (
                        <div
                          key={todo._id}
                          className={`todo-item ${isDone ? 'completed' : ''}`}
                          style={{ borderLeft: `3px solid ${isDone ? 'rgba(16, 185, 129, 0.4)' : pConfig.border}` }}
                        >
                          <button
                            className="todo-check-btn"
                            onClick={() => isDone ? uncompleteTodo(todo._id) : completeTodo(todo._id)}
                            title={isDone ? 'Mark as pending' : 'Mark as done'}
                            style={{
                              background: isDone ? '#10b981' : 'transparent',
                              borderColor: isDone ? '#10b981' : pConfig.color,
                            }}
                          >
                            {isDone ? <Check size={14} color="white" /> : null}
                          </button>

                          <div className="todo-content">
                            <div className="todo-title">
                              {todo.title}
                            </div>
                            <div className="todo-meta">
                              {!isDone && (
                                <span className="todo-priority-badge" style={{ background: pConfig.bg, color: pConfig.color }}>
                                  {pConfig.label}
                                </span>
                              )}
                              {isDone && (
                                <span className="todo-priority-badge" style={{ background: 'rgba(16, 185, 129, 0.12)', color: '#10b981' }}>
                                  ✓ Completed
                                </span>
                              )}
                              <span className="todo-category-badge">
                                {CATEGORY_ICONS[todo.category] || '📌'} {todo.category}
                              </span>
                              {todo.due_time && (
                                <span className="todo-time">
                                  <Clock size={12} /> {todo.due_time}
                                </span>
                              )}
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: '0.25rem' }}>
                            {isDone && (
                              <button
                                className="todo-action-btn"
                                onClick={() => uncompleteTodo(todo._id)}
                                title="Reopen task"
                              >
                                <RotateCcw size={15} />
                              </button>
                            )}
                            <button
                              className="todo-delete-btn"
                              onClick={() => deleteTodo(todo._id)}
                              title="Delete"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
