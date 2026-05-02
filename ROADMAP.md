# RIVA Project Tracker

## 🐛 Known Bugs
- [x] ~~**Login redirect not working**~~ - Fixed: call _onUserLoggedIn directly
- [ ] Google STT sometimes returns empty error, causing disconnect
- [ ] TTS occasionally fails on first speak after long idle

---

## 🚀 Features to Implement

### High Priority
- [ ] **Conversation Context Memory** - Remember previous statements in session
  - "I went to a movie" → "I spent 500 there" = movie expense
- [ ] **Push Notifications** - FCM integration for proactive reminders
- [ ] **Proactive Secretary** - AI initiates conversations, not just responds

### Medium Priority
- [ ] **Google Calendar Integration** - Fix OAuth flow for task scheduling
- [ ] **Budget Alerts** - Notify when spending exceeds category limits
- [ ] **Financial Goals** - Track savings goals with progress

### Low Priority
- [ ] **Voice Customization** - Different TTS voices/speeds
- [ ] **Dark/Light Theme Toggle** - User preference
- [ ] **Export Data** - Download transactions as CSV

---

## 📝 Tech Debt
- [ ] Clean up unused gcal.py file
- [ ] Add unit tests for finance_manager.py
- [ ] Add error handling for MongoDB connection failures
- [ ] Implement proper logging instead of print statements

---

## 💡 Ideas for Later
- Weekly spending summary notification
- AI-powered spending insights ("You spent 30% more on food this week")
- Voice-based budget setting
- Multi-language support
- Recurring transaction detection

---

## ✅ Completed
- [x] Finance feature - voice-based expense tracking
- [x] MongoDB integration for transactions
- [x] Deploy to Render
- [x] Fix TTS Samsung binding issue
- [x] Auto-refresh finance tab on switch
