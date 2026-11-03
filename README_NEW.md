# Byte & Bite

Byte & Bite is a web application for analysing vendor transactions, demand forecasts, and contextual events.

Technology stack that was used: React (Vite) frontend, FastAPI (Python) backend, and PostgreSQL database (hosted on Neon).

## 1. Requirements

Install:
- [Python](https://www.python.org/downloads/)
- [Node.js and npm](https://nodejs.org/)
- [Git](https://git-scm.com/)

The commands below are for Windows PowerShell.

## 2. Download the project

Clone the repository and open its folder:

```powershell
git clone <https://github.com/Vickarmstrongg/Developement-Project.git>
cd <Developement-Project>
```

The project has two main folders: `backend` and `frontend`.

## 3. Configure the database

1. Create a file called .env in the backend and add the following into the file. This connects to the existing neon database that has all the data necessary to run the system.

```env
DATABASE_URL=postgresql://neondb_owner:npg_w8igKHr2kjPS@ep-late-glade-b5mw39eo-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
JWT_SECRET=OBpbrJ7fEUriRLwIBGHtJC78eg03UEe33eQz9pTC_CBhGHEhrU9uHTajMBMuseZ_
FRONTEND_URL=http://localhost:5173
GMAIL_ADDRESS=coker199gk@gmail.com
GMAIL_APP_PASSWORD=lixggtnuxwlssajk
```


## 4. Start the backend

Open a terminal in the project folder:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend runs at http://127.0.0.1:8000.

API documentation: http://127.0.0.1:8000/docs

Keep the backend terminal open.

## 5. Start the frontend

Open a **second terminal** in the project folder:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (or the address displayed in the terminal).

The frontend connects to `http://127.0.0.1:8000` by default. If the backend uses a different address, create `frontend/.env` with:

```env
VITE_API_URL=http://127.0.0.1:8000
```

Restart the frontend after editing this file.

## 6. Log in

Use an existing account to log in. The application supports Admin, Manager, and Staff roles. An Admin can invite additional users and assign vendor access.

Existing Usernames and passwords for login

cokergk199@gmail.com 
byteandbite 
admin 

tm@exampl.com
testmanager1
manager

ts@example.com
teststaff1
staff

om@example.com
ochremanager
manager

nicole@example.com
nicolemanager1
Manager

tm3@example.com
testmanager3
manager (Currently Deactivated - Can be activated throught the Admin profile on the users page)

mattjoncoker@gmail.com
password
manager


> 
