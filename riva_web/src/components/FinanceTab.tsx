import { useState, useEffect } from 'react';
import { Wallet, TrendingUp, TrendingDown, Loader2, AlertCircle } from 'lucide-react';
import { type User } from 'firebase/auth';

interface FinanceTabProps {
  user: User;
  apiUrl: string;
}

export function FinanceTab({ user, apiUrl }: FinanceTabProps) {
  const [summary, setSummary] = useState<any>(null);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchData();
  }, [user]);

  const fetchData = async () => {
    try {
      setLoading(true);
      // Fetch summary
      const sumRes = await fetch(`${apiUrl}/finance/summary?user_id=${user.uid}&days=30`);
      const sumData = await sumRes.json();
      setSummary(sumData);

      // Fetch transactions
      const transRes = await fetch(`${apiUrl}/finance/transactions?user_id=${user.uid}&days=30`);
      const transData = await transRes.json();
      setTransactions(transData.transactions || []);
    } catch (err) {
      setError('Failed to fetch financial data');
    } finally {
      setLoading(false);
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
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <h2 style={{ fontSize: '1.5rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <Wallet /> Finance
      </h2>

      {error && (
        <div className="error-banner">
          <AlertCircle size={20} />
          {error}
        </div>
      )}

      {!summary ? (
        <p style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No data available. Ask RIVA to add an expense!</p>
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1.5rem', overflowY: 'auto', paddingRight: '0.5rem' }}>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: '1.5rem', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <TrendingUp size={24} color="#10b981" style={{ marginBottom: '0.5rem' }} />
              <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Income (30d)</span>
              <span style={{ fontSize: '1.5rem', fontWeight: 600, color: '#10b981' }}>₹{summary.total_income?.toFixed(2) || '0.00'}</span>
            </div>
            <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '1.5rem', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <TrendingDown size={24} color="#ef4444" style={{ marginBottom: '0.5rem' }} />
              <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Expenses (30d)</span>
              <span style={{ fontSize: '1.5rem', fontWeight: 600, color: '#ef4444' }}>₹{summary.total_expense?.toFixed(2) || '0.00'}</span>
            </div>
          </div>

          <div>
            <h3 style={{ fontSize: '1.1rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>Recent Transactions</h3>
            {transactions.length === 0 ? (
              <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.9rem' }}>No recent transactions.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {transactions.map((t, idx) => {
                  const isIncome = t.type === 'income';
                  return (
                    <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: isIncome ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                           {isIncome ? <TrendingUp size={20} color="#10b981" /> : <TrendingDown size={20} color="#ef4444" />}
                        </div>
                        <div>
                          <h4 style={{ margin: '0 0 0.25rem 0', fontSize: '1rem', textTransform: 'capitalize' }}>{t.category}</h4>
                          <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                            {new Date(t.date).toLocaleDateString()} {t.description ? `• ${t.description}` : ''}
                          </p>
                        </div>
                      </div>
                      <span style={{ fontWeight: 600, color: isIncome ? '#10b981' : '#ef4444' }}>
                        {isIncome ? '+' : '-'}₹{t.amount?.toFixed(2)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
