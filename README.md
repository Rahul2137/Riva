# RIVA - AI Personal Assistant

RIVA is a voice-enabled AI personal assistant designed to automate everyday tasks such as scheduling, reminders, and basic financial tracking.  
The project focuses on building a scalable backend system that can support real-time interactions and intelligent decision-making.

---

## 🚀 Overview

RIVA aims to act as a proactive personal assistant that understands user intent, manages tasks, and integrates with external services.

The current implementation focuses on:
- Core interaction flow
- Backend architecture
- Task execution pipelines

---

## ✨ Features

- Voice/text-based interaction (basic implementation)
- Task automation (e.g., scheduling, reminders)
- Backend-driven workflow execution
- Modular architecture for future extensibility

---

## 🏗️ Architecture

The system is designed with a modular and extensible architecture to support future scale and feature expansion.

### High-Level Flow

User → Frontend App → Backend API → AI Processing → Task Execution → External Integrations

### Components

- **Frontend**  
  Mobile interface for user interaction (voice/text input)

- **Backend API**  
  Handles request processing, routing, and task orchestration

- **AI Layer**  
  Processes user intent and generates structured actions

- **Task Execution Layer**  
  Executes actions such as scheduling or reminders

- **External Integrations**  
  Services like Google Calendar for real-world task execution

---

### Architecture Diagram

![Architecture](./assets/architecture.png)

---

## 🛠️ Tech Stack

- **Backend:** Java / FastAPI (depending on module)
- **Frontend:** React Native / Flutter
- **AI Integration:** OpenAI APIs
- **Data & Storage:** (Add what you're using, e.g., local storage / DB)
- **Other Tools:** REST APIs, modular service design

---

## 📸 Demo / Screenshots
<img width="624" height="1280" alt="image" src="https://github.com/user-attachments/assets/20c8e2bd-1942-4795-91c4-d0237546b245" />

<img width="624" height="1280" alt="image" src="https://github.com/user-attachments/assets/23de34c3-cc22-497f-9d5d-4cd10e197db4" />

<img width="624" height="1280" alt="image" src="https://github.com/user-attachments/assets/ab8ac342-6635-4266-9665-647b2e1d16bc" />

<img width="624" height="1280" alt="image" src="https://github.com/user-attachments/assets/6cb9eb88-9aa3-4556-ad4d-fc14f619db84" />


## ⚙️ Setup Instructions

```bash
# Clone the repository
git clone https://github.com/Pranav915/Riva.git

# Navigate to project directory
cd Riva

# Install dependencies (example)
pip install -r requirements.txt

# Run the backend
python app.py
